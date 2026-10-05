"""Protocols for external dependencies used by application services."""

from datetime import datetime
from typing import Protocol

from antonie_books.application.commands import UpdateBookCommand
from antonie_books.application.filters import BookFilter, PageRequest
from antonie_books.application.results import AuthorResult, PageResult
from antonie_books.domain.models import Author, Book


class BookRepository(Protocol):
    async def add(self, book: Book) -> None: ...

    async def get_by_id(self, book_id: int) -> Book | None: ...

    async def list(self, filters: BookFilter) -> PageResult[Book]: ...

    async def update(
        self, book_id: int, changes: UpdateBookCommand, updated_at: datetime
    ) -> Book | None: ...

    async def delete(self, book_id: int) -> bool: ...

    async def list_for_author(self, author_id: int, page: PageRequest) -> PageResult[Book]: ...

    async def author_book_counts(self) -> dict[int, int]: ...

    async def publisher_average_pages(self, publisher: str) -> tuple[float, int] | None: ...


class AuthorRepository(Protocol):
    async def get_by_id(self, author_id: int) -> Author | None: ...

    async def get_many(self, author_ids: tuple[int, ...]) -> tuple[Author, ...]: ...

    async def list(self) -> tuple[Author, ...]: ...

    async def list_with_book_counts(self) -> tuple[AuthorResult, ...]: ...


class BookIdGenerator(Protocol):
    async def next_id(self) -> int: ...


class Clock(Protocol):
    def now(self) -> datetime: ...
