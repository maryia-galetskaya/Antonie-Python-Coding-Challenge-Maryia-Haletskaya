"""Unit tests for repeatable MongoDB demo data initialization."""

from typing import Any

import pytest
from bson import Int64

from antonie_books.infrastructure.repositories import MongoBookIdGenerator
from antonie_books.infrastructure.seed import seed_database

pytestmark = pytest.mark.unit


class FakeCollection:
    def __init__(self) -> None:
        self.documents: dict[Any, dict[str, Any]] = {}

    async def create_index(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    async def find_one(self, query: dict[str, Any], **_kwargs: Any) -> dict[str, Any] | None:
        if not query:
            return next(iter(self.documents.values()), None)
        key, expected = next(iter(query.items()))
        return next((doc for doc in self.documents.values() if doc.get(key) == expected), None)

    async def insert_one(self, document: dict[str, Any]) -> None:
        key = document.get("_id", object())
        self.documents[key] = dict(document)

    async def update_one(
        self,
        query: dict[str, Any],
        update: dict[str, Any],
        *,
        upsert: bool = False,
    ) -> None:
        key_field, key_value = next(iter(query.items()))
        document = next(
            (doc for doc in self.documents.values() if doc.get(key_field) == key_value), None
        )
        if document is None:
            if not upsert:
                return
            document = dict(query)
            self.documents[key_value] = document
            for field, value in update.get("$setOnInsert", {}).items():
                document[field] = value
        for field, value in update.get("$max", {}).items():
            document[field] = max(document.get(field, value), value)

    async def find_one_and_update(
        self,
        query: dict[str, Any],
        update: dict[str, Any],
        **_kwargs: Any,
    ) -> dict[str, Any] | None:
        document = await self.find_one(query)
        if document is None:
            return None
        for field, increment in update.get("$inc", {}).items():
            document[field] = Int64(document[field] + increment)
        return document


class FakeDatabase:
    def __init__(self) -> None:
        self.collections = {
            "books": FakeCollection(),
            "authors": FakeCollection(),
            "counters": FakeCollection(),
        }

    def __getitem__(self, name: str) -> FakeCollection:
        return self.collections[name]


@pytest.mark.asyncio
async def test_seed_is_idempotent_and_creates_expected_demo_records() -> None:
    database = FakeDatabase()

    await seed_database(database)
    await seed_database(database)

    authors = database["authors"].documents
    books = database["books"].documents
    assert len(authors) == 3
    assert {author["name"] for author in authors.values()} == {
        "Mark Lutz",
        "Harry Percival",
        "Bob Gregory",
    }
    assert all(author["birth_date"] is None for author in authors.values())
    assert len(books) == 2
    assert books[Int64(2)]["author_ids"] == [Int64(2), Int64(3)]
    assert database["counters"].documents["books"]["seq"] == Int64(2)


@pytest.mark.asyncio
async def test_seed_does_not_overwrite_existing_author_or_book_changes() -> None:
    database = FakeDatabase()
    await seed_database(database)
    database["authors"].documents[Int64(1)]["name"] = "Edited author"
    database["books"].documents[Int64(1)]["title"] = "Edited title"

    await seed_database(database)

    assert database["authors"].documents[Int64(1)]["name"] == "Edited author"
    assert database["books"].documents[Int64(1)]["title"] == "Edited title"


@pytest.mark.asyncio
async def test_seed_advances_counter_without_decreasing_it() -> None:
    database = FakeDatabase()
    await seed_database(database)
    database["counters"].documents["books"]["seq"] = Int64(21)

    await seed_database(database)

    assert database["counters"].documents["books"]["seq"] == Int64(21)


@pytest.mark.asyncio
async def test_next_book_id_after_seed_is_three() -> None:
    database = FakeDatabase()
    await seed_database(database)

    next_id = await MongoBookIdGenerator(database["counters"]).next_id()

    assert next_id == 3
