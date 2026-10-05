"""Explicit, repeatable initialization of the API's demonstration data."""

import asyncio
from datetime import UTC, datetime
from typing import Any

from bson import Int64
from pymongo import AsyncMongoClient

from antonie_books.api.config import Settings
from antonie_books.infrastructure.mongo import MongoDatabase

_AUTHORS = (
    {"id": Int64(1), "name": "Mark Lutz", "birth_date": None},
    {"id": Int64(2), "name": "Harry Percival", "birth_date": None},
    {"id": Int64(3), "name": "Bob Gregory", "birth_date": None},
)


async def seed_database(database: Any) -> None:
    """Insert demo authors/books when absent, preserving all existing records."""

    # Refuse to reconstruct a missing counter in a database containing data. This also
    # initializes it for a clean database before reserving the seed book IDs.
    await MongoDatabase(database).prepare()
    authors = database["authors"]
    books = database["books"]
    counters = database["counters"]

    for author in _AUTHORS:
        await authors.update_one({"id": author["id"]}, {"$setOnInsert": author}, upsert=True)

    # Reserve the demo ID range before inserting those books. $max never moves the
    # counter backwards when the seed is rerun against a used database.
    await counters.update_one({"_id": "books"}, {"$max": {"seq": Int64(2)}}, upsert=True)

    current_time = datetime.now(UTC)
    now = current_time.replace(microsecond=(current_time.microsecond // 1000) * 1000)
    demo_books = (
        {
            "id": Int64(1),
            "title": "Learning Python",
            "publisher": "O'Reilly Media",
            "author_ids": [Int64(1)],
            "pages": Int64(1648),
            "tags": ["Python", "Development", "Learning"],
            "created_at": now,
            "updated_at": now,
        },
        {
            "id": Int64(2),
            "title": "Architecture Patterns with Python",
            "publisher": "O'Reilly Media",
            "author_ids": [Int64(2), Int64(3)],
            "pages": Int64(238),
            "tags": ["Python", "Architecture", "Development"],
            "created_at": now,
            "updated_at": now,
        },
    )
    for book in demo_books:
        await books.update_one({"id": book["id"]}, {"$setOnInsert": book}, upsert=True)


async def _run_seed() -> None:
    settings = Settings()
    client = AsyncMongoClient(settings.mongo_uri, tz_aware=True, retryWrites=False)
    try:
        await client.admin.command("ping")
        await seed_database(client[settings.mongo_database])
    finally:
        await client.close()


def main() -> None:
    """Run the seed command using ``ANTONIE_BOOKS_*`` environment settings."""

    asyncio.run(_run_seed())


if __name__ == "__main__":
    main()
