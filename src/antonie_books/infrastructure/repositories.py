"""MongoDB implementations of the application repository ports."""

from datetime import datetime
import re
from functools import wraps
from typing import Any

from bson import Int64
from pymongo import ASCENDING, ReturnDocument
from pymongo.errors import (
    ConnectionFailure,
    NetworkTimeout,
    PyMongoError,
    ServerSelectionTimeoutError,
)

from antonie_books.application.errors import DatabaseUnavailableError, DataIntegrityError
from antonie_books.domain.models import Author, Book
from antonie_books.infrastructure.mappers import (
    author_from_document,
    author_to_document,
    book_from_document,
    book_to_document,
)

MAX_INT64 = 2**63 - 1


def _storage_boundary(method):
    """Translate driver connectivity and timeouts at the adapter edge."""

    @wraps(method)
    async def wrapped(*args, **kwargs):
        try:
            return await method(*args, **kwargs)
        except (ConnectionFailure, NetworkTimeout, ServerSelectionTimeoutError) as exc:
            raise DatabaseUnavailableError("MongoDB is unavailable") from exc
        except PyMongoError as exc:
            if exc.timeout:
                raise DatabaseUnavailableError("MongoDB operation timed out") from exc
            raise

    return wrapped


class MongoBookIdGenerator:
    """Allocate persistent sequential public IDs from the pre-initialized counter."""

    def __init__(self, counters: Any) -> None:
        self._counters = counters

    @_storage_boundary
    async def next_id(self) -> int:
        document = await self._counters.find_one_and_update(
            {
                "_id": "books",
                "seq": {"$type": ["int", "long"], "$gte": Int64(0), "$lt": Int64(MAX_INT64)},
            },
            {"$inc": {"seq": Int64(1)}},
            return_document=ReturnDocument.AFTER,
        )
        if document is None:
            current = await self._counters.find_one({"_id": "books"})
            if current is None:
                raise DataIntegrityError("The books ID counter is missing")
            sequence = current.get("seq")
            if (
                isinstance(sequence, bool)
                or not isinstance(sequence, int)
                or not 0 <= sequence <= MAX_INT64
            ):
                raise DataIntegrityError("The books ID counter contains an invalid sequence value")
            if sequence == MAX_INT64:
                raise DataIntegrityError("The books ID counter is exhausted")
            raise DataIntegrityError("The books ID counter could not allocate an ID")
        sequence = document.get("seq")
        if (
            isinstance(sequence, bool)
            or not isinstance(sequence, int)
            or not 1 <= sequence <= MAX_INT64
        ):
            raise DataIntegrityError("The books ID counter contains an invalid sequence value")
        return sequence


class MongoBookRepository:
    """CRUD, filter, and report queries for books."""

    def __init__(self, books: Any, authors: Any) -> None:
        self._books = books
        self._authors = authors

    @staticmethod
    def _books_from_documents(documents: list[dict[str, Any]]) -> tuple[Book, ...]:
        return tuple(book_from_document(document) for document in documents)

    @_storage_boundary
    async def add(self, book: Book) -> None:
        await self._books.insert_one(book_to_document(book))

    @_storage_boundary
    async def get_by_id(self, book_id: int) -> Book | None:
        document = await self._books.find_one({"id": Int64(book_id)})
        return book_from_document(document) if document is not None else None

    @_storage_boundary
    async def list(
        self,
        *,
        author: str | None,
        title: str | None,
        tags: tuple[str, ...],
        page: int,
        limit: int,
    ) -> tuple[tuple[Book, ...], int]:
        query = await self._filter_query(author=author, title=title, tags=tags)
        total = await self._books.count_documents(query)
        if (page - 1) * limit >= total:
            return (), total
        cursor = (
            self._books.find(query)
            .sort("id", ASCENDING)
            .skip((page - 1) * limit)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return self._books_from_documents(docs), total

    @_storage_boundary
    async def update(
        self,
        book_id: int,
        *,
        updated_at: datetime,
        title: str | None = None,
        publisher: str | None = None,
        author_ids: tuple[int, ...] | None = None,
        pages: int | None = None,
        tags: tuple[str, ...] | None = None,
    ) -> Book | None:
        values: dict[str, Any] = {}
        for field, value in (
            ("title", title),
            ("publisher", publisher),
            ("pages", pages),
            ("tags", tags),
            ("author_ids", author_ids),
        ):
            if value is None:
                continue
            if field == "author_ids":
                value = [Int64(author_id) for author_id in value]
            elif field == "pages":
                value = Int64(value)
            elif field == "tags":
                value = list(value)
            values[field] = value
        update = {"$set": values, "$max": {"updated_at": updated_at}}
        document = await self._books.find_one_and_update(
            {"id": Int64(book_id)},
            update,
            return_document=ReturnDocument.AFTER,
        )
        return book_from_document(document) if document is not None else None

    @_storage_boundary
    async def delete(self, book_id: int) -> bool:
        result = await self._books.delete_one({"id": Int64(book_id)})
        return result.deleted_count == 1

    @_storage_boundary
    async def list_for_author(
        self, author_id: int, *, page: int, limit: int
    ) -> tuple[tuple[Book, ...], int]:
        query = {"author_ids": Int64(author_id)}
        total = await self._books.count_documents(query)
        if (page - 1) * limit >= total:
            return (), total
        cursor = (
            self._books.find(query)
            .sort("id", ASCENDING)
            .skip((page - 1) * limit)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return self._books_from_documents(docs), total

    @_storage_boundary
    async def author_book_counts(self) -> dict[int, int]:
        pipeline = [
            {"$unwind": "$author_ids"},
            {"$group": {"_id": "$author_ids", "count": {"$sum": 1}}},
        ]
        cursor = await self._books.aggregate(pipeline)
        rows = await cursor.to_list(length=None)
        counts: dict[int, int] = {}
        for row in rows:
            author_id, count = row["_id"], row["count"]
            counts[author_id] = count
        return counts

    @_storage_boundary
    async def publisher_average_pages(self, publisher: str) -> tuple[float, int] | None:
        pipeline = [
            {"$match": {"publisher": publisher}},
            {
                "$group": {
                    "_id": None,
                    "average_pages": {"$avg": "$pages"},
                    "book_count": {"$sum": 1},
                }
            },
        ]
        cursor = await self._books.aggregate(pipeline)
        rows = await cursor.to_list(length=1)
        if not rows:
            return None
        return float(rows[0]["average_pages"]), int(rows[0]["book_count"])

    @_storage_boundary
    async def _filter_query(
        self, *, author: str | None, title: str | None, tags: tuple[str, ...]
    ) -> dict[str, Any]:
        clauses: list[dict[str, Any]] = []
        if title is not None:
            clauses.append({"title": {"$regex": re.escape(title), "$options": "i"}})
        if author is not None:
            author_pattern = {"$regex": re.escape(author), "$options": "i"}
            ids = await self._authors.distinct("id", {"name": author_pattern})
            clauses.append({"author_ids": {"$in": ids}})
        if tags:
            clauses.append({"tags": {"$all": list(tags)}})
        if not clauses:
            return {}
        return {"$and": clauses}


class MongoAuthorRepository:
    """Author lookups, batched reads, and book count projections."""

    def __init__(self, authors: Any) -> None:
        self._authors = authors

    @_storage_boundary
    async def get_by_id(self, author_id: int) -> Author | None:
        document = await self._authors.find_one({"id": Int64(author_id)})
        return author_from_document(document) if document is not None else None

    @_storage_boundary
    async def get_many(self, author_ids: tuple[int, ...]) -> tuple[Author, ...]:
        if not author_ids:
            return ()
        documents = await self._authors.find(
            {"id": {"$in": [Int64(i) for i in author_ids]}}
        ).to_list(length=len(author_ids))
        by_id = {document["id"]: author_from_document(document) for document in documents}
        return tuple(by_id[author_id] for author_id in author_ids if author_id in by_id)

    @_storage_boundary
    async def list(self) -> tuple[Author, ...]:
        documents = await self._authors.find({}).sort("id", ASCENDING).to_list(length=None)
        return tuple(author_from_document(document) for document in documents)

    @_storage_boundary
    async def add(self, author: Author) -> None:
        await self._authors.insert_one(author_to_document(author))
