"""MongoDB client lifecycle and collection initialization."""

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any

from bson import Int64
from pymongo import ASCENDING, AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import (
    ConnectionFailure,
    DuplicateKeyError,
    NetworkTimeout,
    PyMongoError,
    ServerSelectionTimeoutError,
)

from antonie_books.application.errors import DataIntegrityError

logger = logging.getLogger(__name__)
STARTUP_TIMEOUT_SECONDS = 30
OPERATION_TIMEOUT_MS = 5_000
MAX_INT64 = 2**63 - 1


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
        counter = await counters.find_one({"_id": "books"})
        if counter is not None:
            self._validate_counter(counter)
            return
        # Recheck after data inspection: a concurrent startup may have created the
        # counter and started writes after our first read.
        books_exist = await books.find_one({}, projection={"_id": 1}) is not None
        authors_exist = await authors.find_one({}, projection={"_id": 1}) is not None
        counter = await counters.find_one({"_id": "books"})
        if counter is not None:
            self._validate_counter(counter)
            return
        if books_exist or authors_exist:
            raise MongoInitializationError(
                "The books ID counter is missing while the database contains application data; "
                "restore the counter from a consistent database backup."
            )
        try:
            await counters.insert_one({"_id": "books", "seq": Int64(0)})
        except DuplicateKeyError:
            winner = await counters.find_one({"_id": "books"})
            if winner is None:
                raise
            self._validate_counter(winner)

    @staticmethod
    def _validate_counter(document: dict[str, Any]) -> int:
        sequence = document.get("seq")
        if (
            isinstance(sequence, bool)
            or not isinstance(sequence, int)
            or not 0 <= sequence <= MAX_INT64
        ):
            raise DataIntegrityError("The books ID counter contains an invalid sequence value")
        return sequence


async def connect_mongo(
    uri: str,
    database_name: str,
    *,
    timeout_seconds: float = STARTUP_TIMEOUT_SECONDS,
    retry_interval_seconds: float = 0.5,
    client_factory: Callable[..., Any] = AsyncMongoClient,
    sleep: Callable[[float], Any] = asyncio.sleep,
) -> tuple[Any, MongoDatabase]:
    """Connect and prepare MongoDB within one bounded startup deadline."""
    timeout_ms = max(1, min(int(timeout_seconds * 1000), OPERATION_TIMEOUT_MS))
    client = client_factory(
        uri,
        tz_aware=True,
        retryWrites=False,
        timeoutMS=timeout_ms,
        serverSelectionTimeoutMS=timeout_ms,
        connectTimeoutMS=timeout_ms,
    )
    deadline = time.monotonic() + timeout_seconds
    try:
        database = MongoDatabase(client[database_name])
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise MongoInitializationError(
                    f"MongoDB did not become available within {timeout_seconds:g} seconds"
                )
            try:
                await asyncio.wait_for(client.admin.command("ping"), timeout=remaining)
                break
            except PyMongoError as exc:
                if not (
                    isinstance(
                        exc, (ConnectionFailure, NetworkTimeout, ServerSelectionTimeoutError)
                    )
                    or exc.timeout
                ):
                    raise
                if time.monotonic() >= deadline:
                    raise MongoInitializationError(
                        f"MongoDB did not become available within {timeout_seconds:g} seconds"
                    ) from exc
                logger.info("MongoDB ping failed; retrying in %.1f seconds", retry_interval_seconds)
                await sleep(min(retry_interval_seconds, deadline - time.monotonic()))
            except TimeoutError as exc:
                if time.monotonic() >= deadline:
                    raise MongoInitializationError(
                        f"MongoDB did not become available within {timeout_seconds:g} seconds"
                    ) from exc
                await sleep(min(retry_interval_seconds, deadline - time.monotonic()))
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise MongoInitializationError("MongoDB startup deadline expired during initialization")
        await asyncio.wait_for(database.prepare(), timeout=remaining)
        return client, database
    except BaseException:
        await asyncio.shield(client.close())
        raise
