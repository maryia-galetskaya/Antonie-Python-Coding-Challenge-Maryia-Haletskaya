"""Conversions between domain entities and BSON documents."""

from datetime import UTC, date, datetime
from typing import Any

from bson import Int64

from antonie_books.domain.models import Author, Book


def author_to_document(author: Author) -> dict[str, Any]:
    return {
        "id": Int64(author.id),
        "name": author.name,
        "birth_date": datetime.combine(author.birth_date, datetime.min.time(), tzinfo=UTC)
        if author.birth_date is not None
        else None,
    }


def author_from_document(document: dict[str, Any]) -> Author:
    birth_date = document.get("birth_date")
    if isinstance(birth_date, datetime):
        birth_date = birth_date.date()
    if birth_date is not None and not isinstance(birth_date, date):
        raise ValueError("MongoDB author birth_date must be a date or datetime")
    return Author(id=int(document["id"]), name=document["name"], birth_date=birth_date)


def book_to_document(book: Book) -> dict[str, Any]:
    return {
        "id": Int64(book.id),
        "title": book.title,
        "publisher": book.publisher,
        "author_ids": [Int64(author_id) for author_id in book.author_ids],
        "pages": Int64(book.pages),
        "tags": list(book.tags),
        "created_at": book.created_at.astimezone(UTC),
        "updated_at": book.updated_at.astimezone(UTC),
    }


def book_from_document(document: dict[str, Any]) -> Book:
    def utc(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    return Book(
        id=int(document["id"]),
        title=document["title"],
        publisher=document["publisher"],
        author_ids=tuple(int(value) for value in document["author_ids"]),
        pages=int(document["pages"]),
        tags=tuple(document.get("tags", ())),
        created_at=utc(document["created_at"]),
        updated_at=utc(document["updated_at"]),
    )
