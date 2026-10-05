"""MongoDB client lifecycle and collection initialization."""

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any

from bson import Int64
from pymongo import ASCENDING, AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

logger = logging.getLogger(__name__)


class MongoInitializationError(RuntimeError):
    """Raised when MongoDB cannot be prepared safely for the application."""


class MongoDatabase:
    """Owns the selected database and prepares indexes and the books ID counter."""

    def __init__(self, database: AsyncDatabase[Any]) -> None:
        self.database = database

    async def prepare(self) -> None:
        books = self.database["books"]
        authors = self.database["authors"]
        counters = self.database["counters"]
        await books.create_index([("id", ASCENDING)], unique=True, name="books_public_id")
        await books.create_index([("author_ids", ASCENDING)], name="books_author_ids")
        await books.create_index([("publisher", ASCENDING)], name="books_publisher")
        await books.create_index([("tags", ASCENDING)], name="books_tags")
        await authors.create_index([("id", ASCENDING)], unique=True, name="authors_public_id")
        await self._initialize_book_counter(books, authors, counters)

    async def _initialize_book_counter(self, books: Any, authors: Any, counters: Any) -> None:
        if await counters.find_one({"_id": "books"}) is not None:
            return
        books_exist = await books.find_one({}, projection={"_id": 1}) is not None
        authors_exist = await authors.find_one({}, projection={"_id": 1}) is not None
        if books_exist or authors_exist:
            raise MongoInitializationError(
                "The books ID counter is missing while the database contains application data; "
                "restore the counter from a consistent database backup."
            )
        try:
            await counters.insert_one({"_id": "books", "seq": Int64(0)})
        except Exception:
            # Concurrent application starts may both observe an empty collection. The
            # unique _id makes insertion safe; accept a winner only if it initialized it.
            if await counters.find_one({"_id": "books"}) is None:
                raise


async def connect_mongo(
    uri: str,
    database_name: str,
    *,
    timeout_seconds: float = 30,
    retry_interval_seconds: float = 0.5,
    client_factory: Callable[..., Any] = AsyncMongoClient,
    sleep: Callable[[float], Any] = asyncio.sleep,
) -> tuple[Any, MongoDatabase]:
    """Connect and ping MongoDB with bounded retries, then prepare its schema."""

    client = client_factory(uri, tz_aware=True, retryWrites=False)
    database = MongoDatabase(client[database_name])
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while True:
        try:
            await client.admin.command("ping")
            break
        except Exception as exc:
            last_error = exc
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                await client.close()
                raise MongoInitializationError(
                    f"MongoDB did not become available within {timeout_seconds:g} seconds"
                ) from last_error
            logger.info("MongoDB ping failed; retrying in %.1f seconds", retry_interval_seconds)
            await sleep(min(retry_interval_seconds, remaining))
    try:
        await database.prepare()
    except Exception:
        await client.close()
        raise
    return client, database
