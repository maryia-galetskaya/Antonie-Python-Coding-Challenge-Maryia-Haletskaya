"""Errors raised by application use cases and their external dependencies."""

from antonie_books.domain.errors import DomainError


class DatabaseUnavailableError(RuntimeError):
    """Raised when a request cannot use the configured database."""


class DataIntegrityError(RuntimeError):
    """Stored application data violates an invariant required to serve a request."""


class BookNotFoundError(DomainError):
    """A requested book does not exist."""

    code = "book_not_found"

    def __init__(self, book_id: int) -> None:
        super().__init__(f"Book {book_id} was not found")


class AuthorNotFoundError(DomainError):
    """One or more requested authors do not exist."""

    code = "author_not_found"

    def __init__(self, author_ids: tuple[int, ...]) -> None:
        self.author_ids = author_ids
        ids = ", ".join(str(author_id) for author_id in author_ids)
        super().__init__(f"Author(s) {ids} were not found")


class UnknownBookAuthorError(DomainError):
    """A book references one or more authors that do not exist."""

    code = "author_not_found"

    def __init__(self, author_ids: tuple[int, ...]) -> None:
        self.author_ids = author_ids
        ids = ", ".join(str(author_id) for author_id in author_ids)
        super().__init__(f"Author(s) {ids} were not found")


class PublisherNotFoundError(DomainError):
    """No books exist for a requested publisher name."""

    code = "publisher_not_found"

    def __init__(self, publisher: str) -> None:
        super().__init__(f"Publisher {publisher!r} was not found")
