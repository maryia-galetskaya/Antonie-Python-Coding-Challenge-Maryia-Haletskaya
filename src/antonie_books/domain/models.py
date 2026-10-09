"""Framework-independent domain entities."""

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True, slots=True)
class Author:
    """An author with a stable positive public ID."""

    id: int
    name: str
    birth_date: date | None = None


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
