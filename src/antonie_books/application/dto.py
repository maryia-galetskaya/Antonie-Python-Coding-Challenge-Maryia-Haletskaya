"""Simple data passed into and returned from application services."""

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True, slots=True)
class CreateBookInput:
    title: str
    publisher: str
    author_ids: tuple[int, ...]
    pages: int
    tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class UpdateBookInput:
    book_id: int
    title: str | None = None
    publisher: str | None = None
    author_ids: tuple[int, ...] | None = None
    pages: int | None = None
    tags: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class ListBooksInput:
    author: str | None = None
    title: str | None = None
    tags: tuple[str, ...] = ()
    page: int = 1
    limit: int = 20


@dataclass(frozen=True, slots=True)
class BookIdInput:
    book_id: int


@dataclass(frozen=True, slots=True)
class ListAuthorBooksInput:
    author_id: int
    page: int = 1
    limit: int = 20


@dataclass(frozen=True, slots=True)
class AuthorIdInput:
    author_id: int


@dataclass(frozen=True, slots=True)
class PublisherInput:
    publisher: str


@dataclass(frozen=True, slots=True)
class AuthorOutput:
    id: int
    name: str
    birth_date: date | None


@dataclass(frozen=True, slots=True)
class AuthorWithBookCountOutput:
    author: AuthorOutput
    book_count: int


@dataclass(frozen=True, slots=True)
class BookOutput:
    id: int
    title: str
    publisher: str
    author_ids: tuple[int, ...]
    authors: tuple[AuthorOutput, ...]
    pages: int
    tags: tuple[str, ...]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class BookPageOutput:
    items: tuple[BookOutput, ...]
    page: int
    limit: int
    total: int


@dataclass(frozen=True, slots=True)
class PublisherAverageOutput:
    publisher: str
    average_pages: float
    book_count: int
