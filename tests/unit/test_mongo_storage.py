"""Unit checks for persistent book ID allocation safety."""

from unittest.mock import AsyncMock, call

import pytest
from bson import Int64
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from antonie_books.infrastructure.mongo import MongoDatabase, MongoInitializationError
from antonie_books.infrastructure.repositories import MongoBookIdGenerator

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_id_generator_uses_one_atomic_update_without_upsert() -> None:
    counters = AsyncMock()
    counters.find_one_and_update.return_value = {"_id": "books", "seq": Int64(9)}
    generator = MongoBookIdGenerator(counters)

    assert await generator.next_id() == 9

    counters.find_one_and_update.assert_awaited_once_with(
        {
            "_id": "books",
            "seq": {"$type": ["int", "long"], "$gte": Int64(0), "$lt": Int64(2**63 - 1)},
        },
        {"$inc": {"seq": Int64(1)}},
        return_document=ReturnDocument.AFTER,
    )


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
async def test_counter_initialization_race_rereads_duplicate_insert_winner() -> None:
    books = AsyncMock()
    authors = AsyncMock()
    counters = AsyncMock()
    books.find_one.return_value = None
    authors.find_one.return_value = None
    counters.find_one.side_effect = [None, None, {"_id": "books", "seq": Int64(0)}]
    counters.insert_one.side_effect = DuplicateKeyError("counter was initialized concurrently")
    database = MongoDatabase({"books": books, "authors": authors, "counters": counters})

    await database._initialize_book_counter(books, authors, counters)

    counters.insert_one.assert_awaited_once_with({"_id": "books", "seq": Int64(0)})
    assert counters.find_one.await_args_list == [
        call({"_id": "books"}),
        call({"_id": "books"}),
        call({"_id": "books"}),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("books_exist,authors_exist", [(True, False), (False, True)])
async def test_missing_counter_with_application_data_fails_without_reconstruction(
    books_exist: bool, authors_exist: bool
) -> None:
    books = AsyncMock()
    authors = AsyncMock()
    counters = AsyncMock()
    counters.find_one.return_value = None
    books.find_one.return_value = {"_id": "book"} if books_exist else None
    authors.find_one.return_value = {"_id": "author"} if authors_exist else None
    database = MongoDatabase({"books": books, "authors": authors, "counters": counters})

    with pytest.raises(MongoInitializationError, match="counter is missing"):
        await database._initialize_book_counter(books, authors, counters)

    counters.insert_one.assert_not_awaited()
