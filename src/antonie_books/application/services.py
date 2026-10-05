"""Application use cases for books, authors, and publisher reports."""

from datetime import UTC, datetime

from antonie_books.application.commands import CreateBookCommand, UpdateBookCommand
from antonie_books.application.filters import BookFilter, PageRequest
from antonie_books.application.ports import AuthorRepository, BookIdGenerator, BookRepository, Clock
from antonie_books.application.results import (
    AuthorResult,
    BookResult,
    PageResult,
    PublisherAverageResult,
)
from antonie_books.application.service_errors import AuthorNotFoundError, BookNotFoundError
from antonie_books.domain.models import Author, Book


def _utc_millisecond_time(clock: Clock) -> datetime:
    """Read an aware clock value and normalize it to UTC millisecond precision."""

    value = clock.now()
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("clock must return a timezone-aware datetime")
    normalized = value.astimezone(UTC)
    return normalized.replace(microsecond=(normalized.microsecond // 1000) * 1000)


class BookService:
    """Coordinate book CRUD while keeping persistence and time replaceable."""

    def __init__(
        self,
        books: BookRepository,
        authors: AuthorRepository,
        id_generator: BookIdGenerator,
        clock: Clock,
    ) -> None:
        self._books = books
        self._authors = authors
        self._id_generator = id_generator
        self._clock = clock

    async def create(self, command: CreateBookCommand) -> BookResult:
        """Validate references, allocate an ID, and persist a new book.

        The ID is intentionally allocated only after reference validation. Once allocated, it is
        never rolled back if construction or repository insertion fails.
        """

        authors = await self._require_authors(command.author_ids)
        now = _utc_millisecond_time(self._clock)
        book_id = await self._id_generator.next_id()
        book = Book(
            id=book_id,
            title=command.title,
            publisher=command.publisher,
            author_ids=command.author_ids,
            pages=command.pages,
            tags=command.tags,
            created_at=now,
            updated_at=now,
        )
        await self._books.add(book)
        return BookResult(book=book, authors=authors)

    async def get(self, book_id: int) -> BookResult:
        """Return a book with its authors or raise ``BookNotFoundError``."""

        book = await self._books.get_by_id(book_id)
        if book is None:
            raise BookNotFoundError(book_id)
        return BookResult(book=book, authors=await self._require_authors(book.author_ids))

    async def list(self, filters: BookFilter | None = None) -> PageResult[BookResult]:
        """Return a page of books with author entities resolved in repository order."""

        page = await self._books.list(filters or BookFilter())
        all_author_ids = tuple(
            dict.fromkeys(author_id for book in page.items for author_id in book.author_ids)
        )
        authors = await self._authors.get_many(all_author_ids) if all_author_ids else ()
        authors_by_id = {author.id: author for author in authors}
        missing = tuple(author_id for author_id in all_author_ids if author_id not in authors_by_id)
        if missing:
            raise AuthorNotFoundError(missing)
        items = [
            BookResult(
                book=book,
                authors=tuple(authors_by_id[author_id] for author_id in book.author_ids),
            )
            for book in page.items
        ]
        return PageResult(items=tuple(items), page=page.page, limit=page.limit, total=page.total)

    async def update(self, book_id: int, changes: UpdateBookCommand) -> BookResult:
        """Apply only supplied fields and retain the repository's current book state."""

        if changes.author_ids is not None:
            await self._require_authors(changes.author_ids)
        updated_at = _utc_millisecond_time(self._clock)
        book = await self._books.update(book_id, changes, updated_at)
        if book is None:
            raise BookNotFoundError(book_id)
        return BookResult(book=book, authors=await self._require_authors(book.author_ids))

    async def delete(self, book_id: int) -> None:
        """Delete an existing book, raising when it is unknown."""

        if not await self._books.delete(book_id):
            raise BookNotFoundError(book_id)

    async def _require_authors(self, author_ids: tuple[int, ...]) -> tuple[Author, ...]:
        authors = await self._authors.get_many(author_ids)
        found_ids = {author.id for author in authors}
        missing = tuple(author_id for author_id in author_ids if author_id not in found_ids)
        if missing:
            raise AuthorNotFoundError(missing)
        return authors


class AuthorService:
    """Read author resources and their book counts."""

    def __init__(self, authors: AuthorRepository, books: BookRepository) -> None:
        self._authors = authors
        self._books = books

    async def get(self, author_id: int) -> Author:
        author = await self._authors.get_by_id(author_id)
        if author is None:
            raise AuthorNotFoundError((author_id,))
        return author

    async def list(self) -> tuple[Author, ...]:
        return await self._authors.list()

    async def list_with_book_counts(self) -> tuple[AuthorResult, ...]:
        return await self._authors.list_with_book_counts()

    async def list_books(self, author_id: int, page: PageRequest | None = None) -> PageResult[Book]:
        """List books by an author, including an empty page when none are found."""

        await self.get(author_id)
        return await self._books.list_for_author(author_id, page or PageRequest())


class PublisherService:
    """Expose publisher page-count aggregates backed by the book repository."""

    def __init__(self, books: BookRepository) -> None:
        self._books = books

    async def get_average(self, publisher: str) -> PublisherAverageResult | None:
        aggregate = await self._books.publisher_average_pages(publisher)
        if aggregate is None:
            return None
        average_pages, book_count = aggregate
        return PublisherAverageResult(publisher, average_pages, book_count)


__all__ = ["AuthorService", "BookService", "PublisherService"]
