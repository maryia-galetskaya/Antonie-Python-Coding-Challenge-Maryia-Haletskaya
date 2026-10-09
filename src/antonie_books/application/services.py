"""Application use cases for books, authors, and publisher reports."""

from datetime import UTC, datetime

from antonie_books.application.dto import (
    AuthorIdInput,
    AuthorOutput,
    AuthorWithBookCountOutput,
    BookIdInput,
    BookOutput,
    BookPageOutput,
    CreateBookInput,
    ListAuthorBooksInput,
    ListBooksInput,
    PublisherAverageOutput,
    PublisherInput,
    UpdateBookInput,
)
from antonie_books.application.errors import (
    AuthorNotFoundError,
    BookNotFoundError,
    UnknownBookAuthorError,
)
from antonie_books.domain.models import Author, Book


class BookService:
    """Coordinate book CRUD while keeping persistence and time replaceable."""

    def __init__(
        self,
        book_repository,
        author_repository,
        book_id_generator,
        clock,
    ) -> None:
        self._book_repository = book_repository
        self._author_repository = author_repository
        self._book_id_generator = book_id_generator
        self._clock = clock

    def _utc_millisecond_time(self) -> datetime:
        """Read an aware clock value and normalize it to UTC millisecond precision."""

        value = self._clock.now()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime")
        normalized = value.astimezone(UTC)
        return normalized.replace(microsecond=(normalized.microsecond // 1000) * 1000)

    @staticmethod
    def _book_output(book: Book, authors: tuple[Author, ...]) -> BookOutput:
        authors_by_id = {author.id: author for author in authors}
        return BookOutput(
            id=book.id,
            title=book.title,
            publisher=book.publisher,
            author_ids=book.author_ids,
            authors=tuple(
                AuthorOutput(author.id, author.name, author.birth_date)
                for author_id in book.author_ids
                if (author := authors_by_id.get(author_id)) is not None
            ),
            pages=book.pages,
            tags=book.tags,
            created_at=book.created_at,
            updated_at=book.updated_at,
        )

    @classmethod
    def _book_outputs(
        cls, books: tuple[Book, ...], authors: tuple[Author, ...]
    ) -> tuple[BookOutput, ...]:
        authors_by_id = {author.id: author for author in authors}
        return tuple(
            cls._book_output(
                book,
                tuple(authors_by_id[i] for i in book.author_ids if i in authors_by_id),
            )
            for book in books
        )

    async def create(self, data: CreateBookInput) -> BookOutput:
        """Validate references, allocate an ID, and persist a new book.

        The ID is intentionally allocated only after reference validation. Once allocated, it is
        never rolled back if construction or repository insertion fails.
        """

        authors = await self._require_authors(data.author_ids)
        now = self._utc_millisecond_time()
        book_id = await self._book_id_generator.next_id()
        book = Book(
            id=book_id,
            title=data.title,
            publisher=data.publisher,
            author_ids=data.author_ids,
            pages=data.pages,
            tags=data.tags,
            created_at=now,
            updated_at=now,
        )
        await self._book_repository.add(book)
        return self._book_output(book, authors)

    async def get(self, data: BookIdInput) -> BookOutput:
        """Return a book with its authors or raise ``BookNotFoundError``."""

        book = await self._book_repository.get_by_id(data.book_id)
        if book is None:
            raise BookNotFoundError(data.book_id)
        authors = await self._author_repository.get_many(book.author_ids)
        return self._book_output(book, authors)

    async def list(self, data: ListBooksInput) -> BookPageOutput:
        """Return a page of books with author entities resolved in repository order."""

        books, total = await self._book_repository.list(
            author=data.author, title=data.title, tags=data.tags, page=data.page, limit=data.limit
        )
        all_author_ids = tuple(dict.fromkeys(i for book in books for i in book.author_ids))
        authors = (
            await self._author_repository.get_many(all_author_ids) if all_author_ids else ()
        )
        return BookPageOutput(self._book_outputs(books, authors), data.page, data.limit, total)

    async def update(self, data: UpdateBookInput) -> BookOutput:
        """Apply only supplied fields and retain the repository's current book state."""

        if data.author_ids is not None:
            await self._require_authors(data.author_ids)
        updated_at = self._utc_millisecond_time()
        book = await self._book_repository.update(
            data.book_id,
            updated_at=updated_at,
            title=data.title,
            publisher=data.publisher,
            author_ids=data.author_ids,
            pages=data.pages,
            tags=data.tags,
        )
        if book is None:
            raise BookNotFoundError(data.book_id)
        authors = await self._author_repository.get_many(book.author_ids)
        return self._book_output(book, authors)

    async def delete(self, data: BookIdInput) -> None:
        """Delete an existing book, raising when it is unknown."""

        if not await self._book_repository.delete(data.book_id):
            raise BookNotFoundError(data.book_id)

    async def _require_authors(self, author_ids: tuple[int, ...]) -> tuple[Author, ...]:
        authors = await self._author_repository.get_many(author_ids)
        found_ids = {author.id for author in authors}
        missing = tuple(author_id for author_id in author_ids if author_id not in found_ids)
        if missing:
            raise UnknownBookAuthorError(missing)
        return authors


class AuthorService:
    """Read author resources and their book counts."""

    def __init__(self, author_repository, book_repository) -> None:
        self._author_repository = author_repository
        self._book_repository = book_repository

    async def get(self, data: AuthorIdInput) -> AuthorOutput:
        author = await self._author_repository.get_by_id(data.author_id)
        if author is None:
            raise AuthorNotFoundError((data.author_id,))
        return AuthorOutput(author.id, author.name, author.birth_date)

    async def list(self) -> tuple[AuthorOutput, ...]:
        return tuple(
            AuthorOutput(author.id, author.name, author.birth_date)
            for author in await self._author_repository.list()
        )

    async def list_with_book_counts(self) -> tuple[AuthorWithBookCountOutput, ...]:
        authors = await self._author_repository.list()
        counts = await self._book_repository.author_book_counts()
        return tuple(
            AuthorWithBookCountOutput(
                AuthorOutput(author.id, author.name, author.birth_date),
                counts.get(author.id, 0),
            )
            for author in authors
        )

    async def list_books(self, data: ListAuthorBooksInput) -> BookPageOutput:
        """List an author's books with batched author details, even when the page is empty."""

        await self.get(AuthorIdInput(data.author_id))
        books, total = await self._book_repository.list_for_author(
            data.author_id, page=data.page, limit=data.limit
        )
        author_ids = tuple(dict.fromkeys(i for book in books for i in book.author_ids))
        authors = (
            await self._author_repository.get_many(author_ids) if author_ids else ()
        )
        return BookPageOutput(
            BookService._book_outputs(books, authors), data.page, data.limit, total
        )


class PublisherService:
    """Expose publisher page-count aggregates backed by the book repository."""

    def __init__(self, book_repository) -> None:
        self._book_repository = book_repository

    async def get_average(self, data: PublisherInput) -> PublisherAverageOutput | None:
        aggregate = await self._book_repository.publisher_average_pages(data.publisher)
        if aggregate is None:
            return None
        average_pages, book_count = aggregate
        return PublisherAverageOutput(data.publisher, average_pages, book_count)
