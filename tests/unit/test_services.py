from dataclasses import replace
from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from antonie_books.application.errors import (
    BookNotFoundError,
    UnknownBookAuthorError,
)
from antonie_books.application.dto import (
    AuthorOutput,
    BookIdInput,
    CreateBookInput,
    ListAuthorBooksInput,
    ListBooksInput,
    UpdateBookInput,
)
from antonie_books.application.services import AuthorService, BookService
from antonie_books.domain.models import Author, Book

pytestmark = pytest.mark.unit


class FakeClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value


class FakeIdGenerator:
    def __init__(self, value: int = 20) -> None:
        self.value = value
        self.calls = 0

    async def next_id(self) -> int:
        self.calls += 1
        allocated = self.value
        self.value += 1
        return allocated


class FakeAuthorRepository:
    def __init__(self, authors: tuple[Author, ...] = ()) -> None:
        self.authors = {author.id: author for author in authors}
        self.get_many_calls: list[tuple[int, ...]] = []

    async def get_by_id(self, author_id: int) -> Author | None:
        return self.authors.get(author_id)

    async def get_many(self, author_ids: tuple[int, ...]) -> tuple[Author, ...]:
        self.get_many_calls.append(author_ids)
        return tuple(self.authors[i] for i in author_ids if i in self.authors)

    async def list(self) -> tuple[Author, ...]:
        return tuple(self.authors.values())


class FakeBookRepository:
    def __init__(self) -> None:
        self.books: dict[int, Book] = {}
        self.add_error: Exception | None = None
        self.last_filter: tuple[str | None, str | None, tuple[str, ...], int, int] | None = None
        self.last_page: tuple[int, int] | None = None

    async def add(self, book: Book) -> None:
        if self.add_error is not None:
            raise self.add_error
        self.books[book.id] = book

    async def get_by_id(self, book_id: int) -> Book | None:
        return self.books.get(book_id)

    async def list(
        self,
        *,
        author: str | None,
        title: str | None,
        tags: tuple[str, ...],
        page: int,
        limit: int,
    ) -> tuple[tuple[Book, ...], int]:
        self.last_filter = (author, title, tags, page, limit)
        return tuple(self.books.values()), len(self.books)

    async def update(
        self,
        book_id: int,
        *,
        updated_at: datetime,
        title: str | None = None,
        publisher: str | None = None,
        author_ids: tuple[int, ...] | None = None,
        pages: int | None = None,
        tags: tuple[str, ...] | None = None,
    ) -> Book | None:
        current = self.books.get(book_id)
        if current is None:
            return None
        updated = replace(
            current,
            title=title if title is not None else current.title,
            publisher=publisher if publisher is not None else current.publisher,
            author_ids=author_ids if author_ids is not None else current.author_ids,
            pages=pages if pages is not None else current.pages,
            tags=tags if tags is not None else current.tags,
            updated_at=updated_at,
        )
        self.books[book_id] = updated
        return updated

    async def delete(self, book_id: int) -> bool:
        return self.books.pop(book_id, None) is not None

    async def list_for_author(
        self, author_id: int, *, page: int, limit: int
    ) -> tuple[tuple[Book, ...], int]:
        self.last_page = (page, limit)
        matching = tuple(book for book in self.books.values() if author_id in book.author_ids)
        start = (page - 1) * limit
        return matching[start : start + limit], len(matching)

    async def author_book_counts(self) -> dict[int, int]:
        return {}

    async def publisher_average_pages(self, publisher: str) -> tuple[float, int] | None:
        return None


def make_service(
    *,
    clock_value: datetime | None = None,
    author_ids: tuple[int, ...] = (1, 2),
    generated_id: int = 20,
) -> tuple[BookService, FakeBookRepository, FakeAuthorRepository, FakeIdGenerator]:
    authors = FakeAuthorRepository(
        tuple(Author(i, f"Author {i}", date(2000, 1, 1)) for i in author_ids)
    )
    books = FakeBookRepository()
    ids = FakeIdGenerator(generated_id)
    clock = FakeClock(clock_value or datetime(2025, 4, 3, 8, 9, 10, 123456, tzinfo=UTC))
    return BookService(books, authors, ids, clock), books, authors, ids


def book_fields(**overrides: object) -> CreateBookInput:
    fields: dict[str, object] = {
        "title": "The Pragmatic Programmer",
        "publisher": "Addison-Wesley",
        "author_ids": (1, 2),
        "pages": 352,
        "tags": ("Software", "Career"),
    }
    fields.update(overrides)
    return CreateBookInput(**fields)  # type: ignore[arg-type]


async def test_create_assigns_id_and_utc_millisecond_timestamps() -> None:
    service, books, _, ids = make_service(
        clock_value=datetime(2025, 4, 3, 10, 9, 10, 123999, tzinfo=timezone(timedelta(hours=2)))
    )

    result = await service.create(book_fields())

    expected = datetime(2025, 4, 3, 8, 9, 10, 123000, tzinfo=UTC)
    assert result.id == 20
    assert result.created_at == expected
    assert result.updated_at == expected
    assert result.authors == (
        AuthorOutput(1, "Author 1", date(2000, 1, 1)),
        AuthorOutput(2, "Author 2", date(2000, 1, 1)),
    )
    assert books.books[20].id == result.id
    assert ids.calls == 1


async def test_create_validates_all_authors_before_consuming_id() -> None:
    service, books, _, ids = make_service(author_ids=(1,))

    with pytest.raises(UnknownBookAuthorError) as error:
        await service.create(book_fields(author_ids=(1, 999)))

    assert error.value.author_ids == (999,)
    assert ids.calls == 0
    assert books.books == {}


async def test_failed_insert_keeps_allocated_id_consumed_and_next_create_skips_it() -> None:
    service, books, _, ids = make_service()
    books.add_error = OSError("storage failed")

    with pytest.raises(OSError, match="storage failed"):
        await service.create(book_fields())

    books.add_error = None
    created = await service.create(book_fields())

    assert ids.calls == 2
    assert created.id == 21


async def test_get_update_and_delete_book_lifecycle() -> None:
    clock = FakeClock(datetime(2025, 4, 3, 8, 9, 10, 123000, tzinfo=UTC))
    authors = FakeAuthorRepository((Author(1, "Author 1"), Author(2, "Author 2")))
    books = FakeBookRepository()
    service = BookService(books, authors, FakeIdGenerator(), clock)
    created = await service.create(book_fields())

    fetched = await service.get(BookIdInput(created.id))
    clock.value = datetime(2025, 4, 3, 8, 10, 11, 987654, tzinfo=UTC)
    updated = await service.update(UpdateBookInput(created.id, title="New title"))

    assert fetched == created
    assert updated.title == "New title"
    assert updated.publisher == created.publisher
    assert updated.author_ids == created.author_ids
    assert updated.pages == created.pages
    assert updated.tags == created.tags
    assert updated.created_at == created.created_at
    assert updated.updated_at == datetime(2025, 4, 3, 8, 10, 11, 987000, tzinfo=UTC)
    assert updated.updated_at > created.updated_at

    await service.delete(BookIdInput(created.id))
    assert books.books == {}


@pytest.mark.parametrize("operation", ["get", "update", "delete"])
async def test_unknown_book_raises_not_found(operation: str) -> None:
    service, _, _, _ = make_service()

    with pytest.raises(BookNotFoundError):
        if operation == "get":
            await service.get(BookIdInput(404))
        elif operation == "update":
            await service.update(UpdateBookInput(404, title="Title"))
        else:
            await service.delete(BookIdInput(404))


async def test_update_rejects_unknown_authors_without_changing_book() -> None:
    service, books, _, _ = make_service(author_ids=(1,))
    created = await service.create(book_fields(author_ids=(1,)))

    with pytest.raises(UnknownBookAuthorError):
        await service.update(UpdateBookInput(created.id, author_ids=(999,)))

    assert books.books[created.id].author_ids == created.author_ids


async def test_list_batches_author_lookups_and_preserves_pagination() -> None:
    service, books, authors, _ = make_service()
    await service.create(book_fields())
    await service.create(book_fields(title="A second book", author_ids=(2, 1)))
    authors.get_many_calls.clear()
    result = await service.list(ListBooksInput(title="Pragmatic", page=2, limit=7))

    assert result.total == 2
    assert result.items[0].authors[1].id == 2
    assert tuple(a.id for a in result.items[1].authors) == (2, 1)
    assert books.last_filter == (None, "Pragmatic", (), 2, 7)
    assert authors.get_many_calls == [(1, 2)]


async def test_author_book_results_batch_author_resolution_and_keep_page_metadata() -> None:
    service, books, authors, _ = make_service()
    await service.create(book_fields(author_ids=(1, 2)))
    await service.create(book_fields(title="Second", author_ids=(2, 1)))
    authors.get_many_calls.clear()

    result = await AuthorService(authors, books).list_books(ListAuthorBooksInput(1, 2, 1))

    assert books.last_page == (2, 1)
    assert result.total == 2
    assert len(result.items) == 1
    assert tuple(author.id for author in result.items[0].authors) == (2, 1)
    assert authors.get_many_calls == [(2, 1)]
