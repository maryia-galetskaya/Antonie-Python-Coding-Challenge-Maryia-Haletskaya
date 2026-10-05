"""Unit coverage for MongoDB mapping and ID allocation contracts."""

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock

import pytest
from bson import Int64
from pymongo import ReturnDocument

from antonie_books.application.commands import UpdateBookCommand
from antonie_books.domain.models import Author, Book
from antonie_books.infrastructure.mappers import (
    author_from_document,
    author_to_document,
    book_from_document,
    book_to_document,
)
from antonie_books.infrastructure.mongo import MongoDatabase, MongoInitializationError
from antonie_books.infrastructure.repositories import MongoBookIdGenerator, MongoBookRepository


def test_author_mapping_stores_int64_and_round_trips_date() -> None:
    author = Author(id=2, name="Harry Percival", birth_date=date(1980, 1, 1))

    document = author_to_document(author)

    assert isinstance(document["id"], Int64)
    assert author_from_document(document) == author


def test_book_mapping_stores_numeric_fields_as_int64_and_normalizes_utc() -> None:
    now = datetime(2025, 1, 1, tzinfo=UTC)
    book = Book(7, "Title", "Publisher", (2,), 123, ("Python",), now, now)

    document = book_to_document(book)
    restored = book_from_document(document)

    assert isinstance(document["id"], Int64)
    assert isinstance(document["pages"], Int64)
    assert isinstance(document["author_ids"][0], Int64)
    assert restored == book


@pytest.mark.asyncio
async def test_id_generator_uses_one_atomic_update_without_upsert() -> None:
    counters = AsyncMock()
    counters.find_one_and_update.return_value = {"_id": "books", "seq": Int64(9)}
    generator = MongoBookIdGenerator(counters)

    assert await generator.next_id() == 9

    counters.find_one_and_update.assert_awaited_once_with(
        {"_id": "books"},
        {"$inc": {"seq": Int64(1)}},
        return_document=ReturnDocument.AFTER,
    )


@pytest.mark.asyncio
async def test_book_update_uses_atomic_monotonic_millisecond_timestamp() -> None:
    collection = AsyncMock()
    authors = AsyncMock()
    now = datetime(2025, 1, 1, tzinfo=UTC)
    collection.find_one_and_update.return_value = {
        "id": Int64(7),
        "title": "$publisher",
        "publisher": "Press",
        "author_ids": [Int64(2)],
        "pages": Int64(123),
        "tags": [],
        "created_at": now,
        "updated_at": now,
    }
    repository = MongoBookRepository(collection, authors)

    updated = await repository.update(7, UpdateBookCommand(title="$publisher"), now)

    assert updated is not None
    assert updated.title == "$publisher"
    filter_doc, pipeline = collection.find_one_and_update.await_args.args
    assert filter_doc == {"id": Int64(7)}
    assert pipeline[0]["$set"]["title"] == {"$literal": "$publisher"}
    assert pipeline[0]["$set"]["updated_at"]["$max"][0] == now
    assert pipeline[0]["$set"]["updated_at"]["$max"][1] == {
        "$dateAdd": {
            "startDate": "$updated_at",
            "unit": "millisecond",
            "amount": 1,
        }
    }


@pytest.mark.asyncio
async def test_counter_is_initialized_only_when_books_collection_is_empty() -> None:
    books = AsyncMock()
    authors = AsyncMock()
    counters = AsyncMock()
    counters.find_one.return_value = None
    books.find_one.return_value = None
    authors.find_one.return_value = None
    database = MongoDatabase({"books": books, "authors": authors, "counters": counters})

    await database._initialize_book_counter(books, authors, counters)

    counters.insert_one.assert_awaited_once_with({"_id": "books", "seq": Int64(0)})


@pytest.mark.asyncio
async def test_missing_counter_in_nonempty_database_fails_without_reconstruction() -> None:
    books = AsyncMock()
    authors = AsyncMock()
    counters = AsyncMock()
    counters.find_one.return_value = None
    books.find_one.return_value = {"_id": "book"}
    authors.find_one.return_value = None
    database = MongoDatabase({"books": books, "authors": authors, "counters": counters})

    with pytest.raises(MongoInitializationError, match="counter is missing"):
        await database._initialize_book_counter(books, authors, counters)

    counters.insert_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_counter_with_authors_but_no_books_fails_without_reconstruction() -> None:
    books = AsyncMock()
    authors = AsyncMock()
    counters = AsyncMock()
    counters.find_one.return_value = None
    books.find_one.return_value = None
    authors.find_one.return_value = {"_id": "author"}
    database = MongoDatabase({"books": books, "authors": authors, "counters": counters})

    with pytest.raises(MongoInitializationError, match="counter is missing"):
        await database._initialize_book_counter(books, authors, counters)

    counters.insert_one.assert_not_awaited()
