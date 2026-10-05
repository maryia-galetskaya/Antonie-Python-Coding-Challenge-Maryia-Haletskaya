"""Unit coverage for MongoDB mapping and ID allocation contracts."""

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, call

import pytest
from bson import Int64
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from antonie_books.application.commands import UpdateBookCommand
from antonie_books.application.filters import BookFilter
from antonie_books.application.results import AuthorResult
from antonie_books.domain.models import Author, Book
from antonie_books.infrastructure.mappers import (
    author_from_document,
    author_to_document,
    book_from_document,
    book_to_document,
)
from antonie_books.infrastructure.mongo import MongoDatabase, MongoInitializationError
from antonie_books.infrastructure.repositories import (
    MongoAuthorRepository,
    MongoBookIdGenerator,
    MongoBookRepository,
)

pytestmark = pytest.mark.unit


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
async def test_report_aggregations_await_async_aggregate_cursors() -> None:
    books = AsyncMock()
    book_cursor = AsyncMock()
    book_cursor.to_list.return_value = [{"_id": Int64(7), "count": 2}]
    average_cursor = AsyncMock()
    average_cursor.to_list.return_value = [{"average_pages": 150.5, "book_count": 2}]
    books.aggregate.side_effect = [book_cursor, average_cursor]
    author_collection = AsyncMock()
    author_cursor = AsyncMock()
    author_cursor.to_list.return_value = [
        {
            "id": Int64(7),
            "name": "Ada Lovelace",
            "birth_date": None,
            "book_count": 2,
        }
    ]
    author_collection.aggregate.return_value = author_cursor
    book_repository = MongoBookRepository(books, AsyncMock())
    author_repository = MongoAuthorRepository(author_collection, books)

    assert await book_repository.author_book_counts() == {7: 2}
    assert await book_repository.publisher_average_pages("Press") == (150.5, 2)
    assert await author_repository.list_with_book_counts() == (
        AuthorResult(
            author_from_document({"id": Int64(7), "name": "Ada Lovelace", "birth_date": None}),
            book_count=2,
        ),
    )
    assert books.aggregate.await_count == 2
    book_cursor.to_list.assert_awaited_once_with(length=None)
    average_cursor.to_list.assert_awaited_once_with(length=1)
    assert author_collection.aggregate.await_count == 1
    author_cursor.to_list.assert_awaited_once_with(length=None)


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
    counters.find_one.side_effect = [None, {"_id": "books", "seq": Int64(0)}]
    counters.insert_one.side_effect = DuplicateKeyError("counter was initialized concurrently")
    database = MongoDatabase({"books": books, "authors": authors, "counters": counters})

    await database._initialize_book_counter(books, authors, counters)

    counters.insert_one.assert_awaited_once_with({"_id": "books", "seq": Int64(0)})
    assert counters.find_one.await_args_list == [
        call({"_id": "books"}),
        call({"_id": "books"}),
    ]


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


@pytest.mark.asyncio
async def test_book_filter_query_escapes_regex_and_combines_all_filters_with_and() -> None:
    collection = AsyncMock()
    authors = AsyncMock()
    authors.distinct.return_value = [Int64(4), Int64(9)]
    repository = MongoBookRepository(collection, authors)

    query = await repository._filter_query(
        BookFilter(author="Ada.+", title="[Python]", tags=("Python", "Development"))
    )

    assert query == {
        "$and": [
            {"title": {"$regex": r"\[Python\]", "$options": "i"}},
            {"author_ids": {"$in": [Int64(4), Int64(9)]}},
            {"tags": {"$all": ["Python", "Development"]}},
        ]
    }
    authors.distinct.assert_awaited_once_with(
        "id", {"name": {"$regex": r"Ada\.\+", "$options": "i"}}
    )


@pytest.mark.asyncio
async def test_mongo_prepare_creates_filter_indexes_and_unique_public_id_indexes() -> None:
    books = AsyncMock()
    authors = AsyncMock()
    counters = AsyncMock()
    counters.find_one.return_value = {"_id": "books", "seq": Int64(0)}
    database = MongoDatabase({"books": books, "authors": authors, "counters": counters})

    await database.prepare()

    assert books.create_index.await_args_list == [
        call([("id", 1)], unique=True, name="books_public_id"),
        call([("author_ids", 1)], name="books_author_ids"),
        call([("publisher", 1)], name="books_publisher"),
        call([("tags", 1)], name="books_tags"),
    ]
    authors.create_index.assert_awaited_once_with(
        [("id", 1)], unique=True, name="authors_public_id"
    )
