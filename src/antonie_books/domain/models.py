"""Framework-independent domain entities."""

from dataclasses import dataclass
from datetime import UTC, date, datetime

from antonie_books.domain.errors import InvalidDomainValue

MAX_INT64 = 2**63 - 1


def _positive_int64(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 < value <= MAX_INT64:
        raise InvalidDomainValue(f"{field_name} must be a positive int64")


def _non_empty_text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise InvalidDomainValue(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise InvalidDomainValue(f"{field_name} must not be empty")
    return normalized


def _utc_datetime(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise InvalidDomainValue(f"{field_name} must be a timezone-aware datetime")
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class Author:
    """An author with a stable positive public ID."""

    id: int
    name: str
    birth_date: date | None = None

    def __post_init__(self) -> None:
        _positive_int64(self.id, "id")
        object.__setattr__(self, "name", _non_empty_text(self.name, "name"))
        if self.birth_date is not None and (
            not isinstance(self.birth_date, date) or isinstance(self.birth_date, datetime)
        ):
            raise InvalidDomainValue("birth_date must be a date or None")


@dataclass(frozen=True, slots=True)
class Book:
    """A book entity; author relationships are represented by public author IDs."""

    id: int
    title: str
    publisher: str
    author_ids: tuple[int, ...]
    pages: int
    tags: tuple[str, ...]
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        _positive_int64(self.id, "id")
        object.__setattr__(self, "title", _non_empty_text(self.title, "title"))
        object.__setattr__(self, "publisher", _non_empty_text(self.publisher, "publisher"))
        _positive_int64(self.pages, "pages")

        author_ids = tuple(self.author_ids)
        if not author_ids:
            raise InvalidDomainValue("author_ids must contain at least one author")
        for author_id in author_ids:
            _positive_int64(author_id, "author_id")
        if len(set(author_ids)) != len(author_ids):
            raise InvalidDomainValue("author_ids must be unique")
        object.__setattr__(self, "author_ids", author_ids)

        tags = tuple(_non_empty_text(tag, "tag") for tag in self.tags)
        object.__setattr__(self, "tags", tuple(dict.fromkeys(tags)))

        created_at = _utc_datetime(self.created_at, "created_at")
        updated_at = _utc_datetime(self.updated_at, "updated_at")
        if updated_at < created_at:
            raise InvalidDomainValue("updated_at must not precede created_at")
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "updated_at", updated_at)
