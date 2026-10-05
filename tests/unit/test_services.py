from dataclasses import replace
from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from antonie_books.application.commands import CreateBookCommand, UpdateBookCommand
from antonie_books.application.filters import BookFilter, PageRequest
from antonie_books.application.results import PageResult
from antonie_books.application.service_errors import AuthorNotFoundError, BookNotFoundError
from antonie_books.application.services import AuthorService, BookService, PublisherService
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

    async def list_with_book_counts(self):
        return ()


class FakeBookRepository:
    def __init__(self) -> None:
        self.books: dict[int, Book] = {}
        self.add_error: Exception | None = None
        self.last_filter: BookFilter | None = None
        self.last_page: PageRequest | None = None

    async def add(self, book: Book) -> None:
        if self.add_error is not None:
            raise self.add_error
        self.books[book.id] = book

    async def get_by_id(self, book_id: int) -> Book | None:
        return self.books.get(book_id)

    async def list(self, filters: BookFilter) -> PageResult[Book]:
        self.last_filter = filters
        return PageResult(
            tuple(self.books.values()), filters.page.page, filters.page.limit, len(self.books)
        )

    async def update(
        self, book_id: int, changes: UpdateBookCommand, updated_at: datetime
    ) -> Book | None:
        current = self.books.get(book_id)
        if current is None:
            return None
        updated = replace(
            current,
            title=changes.title if changes.title is not None else current.title,
            publisher=changes.publisher if changes.publisher is not None else current.publisher,
            author_ids=changes.author_ids if changes.author_ids is not None else current.author_ids,
            pages=changes.pages if changes.pages is not None else current.pages,
            tags=changes.tags if changes.tags is not None else current.tags,
            updated_at=updated_at,
        )
        self.books[book_id] = updated
        return updated

    async def delete(self, book_id: int) -> bool:
        return self.books.pop(book_id, None) is not None

    async def list_for_author(self, author_id: int, page: PageRequest) -> PageResult[Book]:
        self.last_page = page
        items = tuple(book for book in self.books.values() if author_id in book.author_ids)
        return PageResult(items, page.page, page.limit, len(items))

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


def command(**overrides: object) -> CreateBookCommand:
    fields: dict[str, object] = {
        "title": "The Pragmatic Programmer",
        "publisher": "Addison-Wesley",
        "author_ids": (1, 2),
        "pages": 352,
        "tags": ("Software", "Career"),
    }
    fields.update(overrides)
    return CreateBookCommand(**fields)  # type: ignore[arg-type]


async def test_create_assigns_id_and_utc_millisecond_timestamps() -> None:
    service, books, _, ids = make_service(
        clock_value=datetime(2025, 4, 3, 10, 9, 10, 123999, tzinfo=timezone(timedelta(hours=2)))
    )

    result = await service.create(command())

    expected = datetime(2025, 4, 3, 8, 9, 10, 123000, tzinfo=UTC)
    assert result.book.id == 20
    assert result.book.created_at == expected
    assert result.book.updated_at == expected
    assert result.authors == (
        Author(1, "Author 1", date(2000, 1, 1)),
        Author(2, "Author 2", date(2000, 1, 1)),
    )
    assert books.books[20] == result.book
    assert ids.calls == 1


async def test_create_validates_all_authors_before_consuming_id() -> None:
    service, books, _, ids = make_service(author_ids=(1,))

    with pytest.raises(AuthorNotFoundError) as error:
        await service.create(command(author_ids=(1, 999)))

    assert error.value.author_ids == (999,)
    assert ids.calls == 0
    assert books.books == {}


async def test_failed_insert_keeps_allocated_id_consumed_and_next_create_skips_it() -> None:
    service, books, _, ids = make_service()
    books.add_error = OSError("storage failed")

    with pytest.raises(OSError, match="storage failed"):
        await service.create(command())

    books.add_error = None
    created = await service.create(command())

    assert ids.calls == 2
    assert created.book.id == 21


async def test_get_update_and_delete_book_lifecycle() -> None:
    clock = FakeClock(datetime(2025, 4, 3, 8, 9, 10, 123000, tzinfo=UTC))
    authors = FakeAuthorRepository((Author(1, "Author 1"), Author(2, "Author 2")))
    books = FakeBookRepository()
    service = BookService(books, authors, FakeIdGenerator(), clock)
    created = await service.create(command())

    fetched = await service.get(created.book.id)
    clock.value = datetime(2025, 4, 3, 8, 10, 11, 987654, tzinfo=UTC)
    updated = await service.update(created.book.id, UpdateBookCommand(title="New title"))

    assert fetched == created
    assert updated.book.title == "New title"
    assert updated.book.publisher == created.book.publisher
    assert updated.book.author_ids == created.book.author_ids
    assert updated.book.pages == created.book.pages
    assert updated.book.tags == created.book.tags
    assert updated.book.created_at == created.book.created_at
    assert updated.book.updated_at == datetime(2025, 4, 3, 8, 10, 11, 987000, tzinfo=UTC)
    assert updated.book.updated_at > created.book.updated_at

    await service.delete(created.book.id)
    assert books.books == {}


@pytest.mark.parametrize("operation", ["get", "update", "delete"])
async def test_unknown_book_raises_not_found(operation: str) -> None:
    service, _, _, _ = make_service()

    with pytest.raises(BookNotFoundError):
        if operation == "get":
            await service.get(404)
        elif operation == "update":
            await service.update(404, UpdateBookCommand(title="Title"))
        else:
            await service.delete(404)


async def test_update_rejects_unknown_authors_without_changing_book() -> None:
    service, books, _, _ = make_service(author_ids=(1,))
    created = await service.create(command(author_ids=(1,)))

    with pytest.raises(AuthorNotFoundError):
        await service.update(created.book.id, UpdateBookCommand(author_ids=(999,)))

    assert books.books[created.book.id] == created.book


async def test_list_resolves_authors_and_preserves_pagination() -> None:
    service, books, authors, _ = make_service()
    await service.create(command())
    authors.get_many_calls.clear()
    filters = BookFilter(title="Pragmatic", page=PageRequest(page=2, limit=7))

    result = await service.list(filters)

    assert result.page == 2
    assert result.limit == 7
    assert result.total == 1
    assert result.items[0].authors[1].id == 2
    assert books.last_filter is filters
    assert authors.get_many_calls == [(1, 2)]


async def test_list_batches_unique_author_lookups_across_multiple_books() -> None:
    service, books, authors, _ = make_service()
    await service.create(command())
    await service.create(command(title="A second book", author_ids=(2, 1)))
    books.last_filter = None
    authors.get_many_calls.clear()

    result = await service.list()

    assert len(result.items) == 2
    assert result.items[0].authors == (authors.authors[1], authors.authors[2])
    assert result.items[1].authors == (authors.authors[2], authors.authors[1])
    assert authors.get_many_calls == [(1, 2)]


async def test_author_and_publisher_services_delegate_to_repositories() -> None:
    service, books, authors, _ = make_service()
    publisher_service = PublisherService(books)
    author_service = AuthorService(authors, books)

    assert (await author_service.get(1)).name == "Author 1"
    assert (await author_service.list())[0].id == 1
    assert await author_service.list_books(1, PageRequest(page=2, limit=4)) == PageResult(
        (), 2, 4, 0
    )
    assert books.last_page == PageRequest(page=2, limit=4)
    assert await publisher_service.get_average("No publisher") is None
