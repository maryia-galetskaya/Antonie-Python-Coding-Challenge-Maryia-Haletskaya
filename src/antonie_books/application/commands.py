"""Typed inputs for application use cases."""

from dataclasses import dataclass

from antonie_books.domain.errors import InvalidDomainValue


def _text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise InvalidDomainValue(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise InvalidDomainValue(f"{field_name} must not be empty")
    return normalized


def _id(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0 or value > 2**63 - 1:
        raise InvalidDomainValue(f"{field_name} must be a positive int64")


@dataclass(frozen=True, slots=True)
class CreateBookCommand:
    """Validated user supplied fields for creating a book; it intentionally has no ID."""

    title: str
    publisher: str
    author_ids: tuple[int, ...]
    pages: int
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "title", _text(self.title, "title"))
        object.__setattr__(self, "publisher", _text(self.publisher, "publisher"))
        if isinstance(self.pages, bool) or not isinstance(self.pages, int) or self.pages <= 0:
            raise InvalidDomainValue("pages must be a positive integer")
        _id(self.pages, "pages")
        author_ids = tuple(self.author_ids)
        if not author_ids:
            raise InvalidDomainValue("author_ids must contain at least one author")
        for author_id in author_ids:
            _id(author_id, "author_id")
        if len(set(author_ids)) != len(author_ids):
            raise InvalidDomainValue("author_ids must be unique")
        object.__setattr__(self, "author_ids", author_ids)
        normalized_tags = tuple(_text(tag, "tag") for tag in self.tags)
        object.__setattr__(self, "tags", tuple(dict.fromkeys(normalized_tags)))


@dataclass(frozen=True, slots=True)
class UpdateBookCommand:
    """A partial book update; ``None`` means the field was not supplied."""

    title: str | None = None
    publisher: str | None = None
    author_ids: tuple[int, ...] | None = None
    pages: int | None = None
    tags: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        values = (self.title, self.publisher, self.author_ids, self.pages, self.tags)
        if all(value is None for value in values):
            raise InvalidDomainValue("at least one book field must be provided")
        if self.title is not None:
            object.__setattr__(self, "title", _text(self.title, "title"))
        if self.publisher is not None:
            object.__setattr__(self, "publisher", _text(self.publisher, "publisher"))
        if self.pages is not None:
            if isinstance(self.pages, bool) or not isinstance(self.pages, int) or self.pages <= 0:
                raise InvalidDomainValue("pages must be a positive integer")
            _id(self.pages, "pages")
        if self.author_ids is not None:
            author_ids = tuple(self.author_ids)
            if not author_ids:
                raise InvalidDomainValue("author_ids must contain at least one author")
            for author_id in author_ids:
                _id(author_id, "author_id")
            if len(set(author_ids)) != len(author_ids):
                raise InvalidDomainValue("author_ids must be unique")
            object.__setattr__(self, "author_ids", author_ids)
        if self.tags is not None:
            normalized_tags = tuple(_text(tag, "tag") for tag in self.tags)
            object.__setattr__(self, "tags", tuple(dict.fromkeys(normalized_tags)))
