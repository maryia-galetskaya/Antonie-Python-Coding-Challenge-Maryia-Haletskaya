"""Stable result shapes returned by application use cases."""

from dataclasses import dataclass

from antonie_books.domain.models import Author, Book


@dataclass(frozen=True, slots=True)
class PageResult[T]:
    items: tuple[T, ...]
    page: int
    limit: int
    total: int

    def __post_init__(self) -> None:
        for name, value in (("page", self.page), ("limit", self.limit), ("total", self.total)):
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{name} must be an integer")
        if self.page < 1 or self.limit < 1 or self.total < 0:
            raise ValueError("page and limit must be positive and total must be non-negative")


@dataclass(frozen=True, slots=True)
class BookResult:
    book: Book
    authors: tuple[Author, ...]


@dataclass(frozen=True, slots=True)
class AuthorResult:
    author: Author
    book_count: int

    def __post_init__(self) -> None:
        if isinstance(self.book_count, bool) or not isinstance(self.book_count, int):
            raise ValueError("book_count must be an integer")
        if self.book_count < 0:
            raise ValueError("book_count must be non-negative")


@dataclass(frozen=True, slots=True)
class PublisherAverageResult:
    publisher: str
    average_pages: float
    book_count: int
