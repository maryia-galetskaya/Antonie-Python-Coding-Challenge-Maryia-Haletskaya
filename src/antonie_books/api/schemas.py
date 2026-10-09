"""Strict HTTP request and response schemas for book resources."""

from datetime import date, datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from antonie_books.domain.errors import InvalidDomainValue

MAX_INT64 = 2**63 - 1
PositiveInt64 = Annotated[int, Field(strict=True, gt=0, le=MAX_INT64)]


def _trimmed_nonempty(value: str) -> str:
    if not value.strip():
        raise InvalidDomainValue("value must not be empty")
    return value.strip()


def _unique_ids(value: list[int]) -> list[int]:
    if not value:
        raise InvalidDomainValue("author_ids must contain at least one author")
    if len(set(value)) != len(value):
        raise InvalidDomainValue("author_ids must be unique")
    return value


def _normalized_tags(value: list[str]) -> list[str]:
    return list(dict.fromkeys(_trimmed_nonempty(tag) for tag in value))


class BookCreateRequest(BaseModel):
    """Fields clients may supply when creating a book."""

    model_config = ConfigDict(extra="forbid", strict=True)

    title: str
    publisher: str
    author_ids: list[PositiveInt64]
    pages: PositiveInt64
    tags: list[str] = Field(default_factory=list)

    @field_validator("title", "publisher", mode="after")
    @classmethod
    def validate_text(cls, value: str) -> str:
        return _trimmed_nonempty(value)

    @field_validator("author_ids", mode="after")
    @classmethod
    def validate_author_ids(cls, value: list[int]) -> list[int]:
        return _unique_ids(value)

    @field_validator("tags", mode="after")
    @classmethod
    def validate_tags(cls, value: list[str]) -> list[str]:
        return _normalized_tags(value)


class BookPatchRequest(BaseModel):
    """Only explicitly supplied editable fields are accepted for updates."""

    model_config = ConfigDict(extra="forbid", strict=True)

    title: str | None = None
    publisher: str | None = None
    author_ids: list[PositiveInt64] | None = None
    pages: PositiveInt64 | None = None
    tags: list[str] | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_null_and_empty_patch(cls, value: Any) -> Any:
        if isinstance(value, dict):
            if not value:
                raise ValueError("at least one book field must be provided")
            if any(item is None for item in value.values()):
                raise ValueError("editable fields must not be null")
        return value

    @field_validator("title", "publisher", mode="after")
    @classmethod
    def validate_text(cls, value: str | None) -> str | None:
        return _trimmed_nonempty(value) if value is not None else None

    @field_validator("author_ids", mode="after")
    @classmethod
    def validate_author_ids(cls, value: list[int] | None) -> list[int] | None:
        return _unique_ids(value) if value is not None else None

    @field_validator("tags", mode="after")
    @classmethod
    def validate_tags(cls, value: list[str] | None) -> list[str] | None:
        return _normalized_tags(value) if value is not None else None


class AuthorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    birth_date: date | None


class AuthorWithBookCountResponse(AuthorResponse):
    book_count: int


class PublisherAverageResponse(BaseModel):
    publisher: str
    average_pages: float
    book_count: int


class BookResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    publisher: str
    author_ids: list[int]
    authors: list[AuthorResponse]
    pages: int
    tags: list[str]
    created_at: datetime
    updated_at: datetime


class BookPageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[BookResponse]
    page: int
    limit: int
    total: int
