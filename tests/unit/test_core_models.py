from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from antonie_books.application.commands import CreateBookCommand, UpdateBookCommand
from antonie_books.application.filters import BookFilter, PageRequest
from antonie_books.application.results import AuthorResult, PageResult
from antonie_books.domain.errors import InvalidDomainValue
from antonie_books.domain.models import Author, Book

pytestmark = pytest.mark.unit


def make_book(**overrides: object) -> Book:
    fields: dict[str, object] = {
        "id": 1,
        "title": "A book",
        "publisher": "A publisher",
        "author_ids": (1,),
        "pages": 100,
        "tags": ("Python",),
        "created_at": datetime(2025, 1, 1, tzinfo=UTC),
        "updated_at": datetime(2025, 1, 1, tzinfo=UTC),
    }
    fields.update(overrides)
    return Book(**fields)  # type: ignore[arg-type]


def test_domain_models_normalize_text_and_datetime_to_utc() -> None:
    book = make_book(
        title="  A book  ",
        tags=(" Python ", "Python", " Learning "),
        created_at=datetime(2025, 1, 1, 1, tzinfo=timezone(timedelta(hours=1))),
    )

    assert book.title == "A book"
    assert book.tags == ("Python", "Learning")
    assert book.created_at == datetime(2025, 1, 1, tzinfo=UTC)


@pytest.mark.parametrize(
    "changes",
    [
        {"id": 0},
        {"id": True},
        {"id": 2**63},
        {"title": "   "},
        {"pages": False},
        {"author_ids": ()},
        {"author_ids": (1, 1)},
        {"tags": ("  ",)},
        {"created_at": datetime(2025, 1, 1)},
        {
            "created_at": datetime(2025, 1, 2, tzinfo=UTC),
            "updated_at": datetime(2025, 1, 1, tzinfo=UTC),
        },
    ],
)
def test_book_rejects_invalid_domain_values(changes: dict[str, object]) -> None:
    with pytest.raises(InvalidDomainValue):
        make_book(**changes)


def test_author_validates_id_name_and_birth_date() -> None:
    author = Author(id=4, name="  Ada Lovelace ", birth_date=date(1815, 12, 10))

    assert author.name == "Ada Lovelace"
    assert author.birth_date == date(1815, 12, 10)
    with pytest.raises(InvalidDomainValue):
        Author(id=1, name="  ")


def test_create_command_normalizes_and_deduplicates_tags() -> None:
    command = CreateBookCommand(
        title="  Learning Python ",
        publisher=" O'Reilly Media ",
        author_ids=(1,),
        pages=1648,
        tags=(" Python ", "Development", "Python"),
    )

    assert command.title == "Learning Python"
    assert command.publisher == "O'Reilly Media"
    assert command.tags == ("Python", "Development")


@pytest.mark.parametrize(
    "factory",
    [
        lambda: CreateBookCommand("Title", "Publisher", (1,), True),
        lambda: CreateBookCommand("Title", "Publisher", (1,), 2**63),
        lambda: CreateBookCommand("Title", "Publisher", (), 1),
        lambda: UpdateBookCommand(),
        lambda: UpdateBookCommand(tags=("  ",)),
        lambda: PageRequest(page=0),
        lambda: PageRequest(limit=101),
        lambda: BookFilter(author="  "),
    ],
)
def test_application_inputs_reject_invalid_values(factory: object) -> None:
    with pytest.raises(InvalidDomainValue):
        factory()  # type: ignore[operator]


def test_filter_and_page_result_keep_pagination_metadata() -> None:
    request = PageRequest(page=2, limit=10)
    filters = BookFilter(author=" Ada ", title="Python", tags=("Python",), page=request)
    result: PageResult[str] = PageResult(
        items=("book",), page=request.page, limit=request.limit, total=11
    )

    assert filters.author == "Ada"
    assert result.items == ("book",)
    assert result.total == 11


@pytest.mark.parametrize("page", [None, 1])
def test_book_filter_requires_page_request(page: object) -> None:
    with pytest.raises(InvalidDomainValue):
        BookFilter(page=page)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "metadata",
    [{"page": True}, {"limit": 1.5}, {"total": False}],
)
def test_page_result_rejects_non_integer_metadata(metadata: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="must be an integer"):
        fields: dict[str, object] = {"items": (), "page": 1, "limit": 20, "total": 0}
        fields.update(metadata)
        PageResult(**fields)  # type: ignore[arg-type]


@pytest.mark.parametrize("book_count", [True, 1.5, -1])
def test_author_result_rejects_invalid_book_count(book_count: object) -> None:
    author = Author(id=1, name="Ada")
    with pytest.raises(ValueError):
        AuthorResult(author=author, book_count=book_count)  # type: ignore[arg-type]
