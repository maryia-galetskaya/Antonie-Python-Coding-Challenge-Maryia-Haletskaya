"""MongoDB implementations of the application repository ports."""

import re
from typing import Any

from bson import Int64
from pymongo import ASCENDING, ReturnDocument

from antonie_books.application.commands import UpdateBookCommand
from antonie_books.application.filters import BookFilter, PageRequest
from antonie_books.application.results import AuthorResult, PageResult
from antonie_books.domain.models import Author, Book
from antonie_books.infrastructure.mappers import (
    author_from_document,
    author_to_document,
    book_from_document,
    book_to_document,
)


class MongoBookIdGenerator:
    """Allocate persistent sequential public IDs from the pre-initialized counter."""

    def __init__(self, counters: Any) -> None:
        self._counters = counters

    async def next_id(self) -> int:
        document = await self._counters.find_one_and_update(
            {"_id": "books"},
            {"$inc": {"seq": Int64(1)}},
            return_document=ReturnDocument.AFTER,
        )
        if document is None:
            raise RuntimeError("The books ID counter is missing; restart after restoring it")
        return int(document["seq"])


class MongoBookRepository:
    """CRUD, filter, and report queries for books."""

    def __init__(self, books: Any, authors: Any) -> None:
        self._books = books
        self._authors = authors

    async def add(self, book: Book) -> None:
        await self._books.insert_one(book_to_document(book))

    async def get_by_id(self, book_id: int) -> Book | None:
        document = await self._books.find_one({"id": Int64(book_id)})
        return book_from_document(document) if document is not None else None

    async def list(self, filters: BookFilter) -> PageResult[Book]:
        query = await self._filter_query(filters)
        total = await self._books.count_documents(query)
        cursor = (
            self._books.find(query)
            .sort("id", ASCENDING)
            .skip((filters.page.page - 1) * filters.page.limit)
            .limit(filters.page.limit)
        )
        docs = await cursor.to_list(length=filters.page.limit)
        return PageResult(
            tuple(book_from_document(document) for document in docs),
            filters.page.page,
            filters.page.limit,
            total,
        )

    async def update(
        self, book_id: int, changes: UpdateBookCommand, updated_at: Any
    ) -> Book | None:
        values: dict[str, Any] = {}
        for field in ("title", "publisher", "pages", "tags", "author_ids"):
            value = getattr(changes, field)
            if value is None:
                continue
            if field == "author_ids":
                value = [Int64(author_id) for author_id in value]
            elif field == "pages":
                value = Int64(value)
            elif field == "tags":
                value = list(value)
            # Pipeline updates treat strings beginning with "$" as field references. Literal
            # wrappers preserve client-supplied values as data while still allowing the
            # timestamp expression below to advance monotonically.
            values[field] = {"$literal": value}
        values["updated_at"] = {
            "$max": [
                updated_at,
                {
                    "$dateAdd": {
                        "startDate": "$updated_at",
                        "unit": "millisecond",
                        "amount": 1,
                    }
                },
            ]
        }
        document = await self._books.find_one_and_update(
            {"id": Int64(book_id)},
            [{"$set": values}],
            return_document=ReturnDocument.AFTER,
        )
        return book_from_document(document) if document is not None else None

    async def delete(self, book_id: int) -> bool:
        result = await self._books.delete_one({"id": Int64(book_id)})
        return result.deleted_count == 1

    async def list_for_author(self, author_id: int, page: PageRequest) -> PageResult[Book]:
        query = {"author_ids": Int64(author_id)}
        total = await self._books.count_documents(query)
        cursor = (
            self._books.find(query)
            .sort("id", ASCENDING)
            .skip((page.page - 1) * page.limit)
            .limit(page.limit)
        )
        docs = await cursor.to_list(length=page.limit)
        return PageResult(
            tuple(book_from_document(doc) for doc in docs), page.page, page.limit, total
        )

    async def author_book_counts(self) -> dict[int, int]:
        pipeline = [
            {"$unwind": "$author_ids"},
            {"$group": {"_id": "$author_ids", "count": {"$sum": 1}}},
        ]
        rows = await self._books.aggregate(pipeline).to_list(length=None)
        return {int(row["_id"]): int(row["count"]) for row in rows}

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
        rows = await self._books.aggregate(pipeline).to_list(length=1)
        if not rows:
            return None
        return float(rows[0]["average_pages"]), int(rows[0]["book_count"])

    async def _filter_query(self, filters: BookFilter) -> dict[str, Any]:
        clauses: list[dict[str, Any]] = []
        if filters.title is not None:
            clauses.append({"title": {"$regex": re.escape(filters.title), "$options": "i"}})
        if filters.author is not None:
            author_pattern = {"$regex": re.escape(filters.author), "$options": "i"}
            ids = await self._authors.distinct("id", {"name": author_pattern})
            clauses.append({"author_ids": {"$in": ids}})
        if filters.tags:
            clauses.append({"tags": {"$all": list(filters.tags)}})
        if not clauses:
            return {}
        return {"$and": clauses}


class MongoAuthorRepository:
    """Author lookups, batched reads, and book count projections."""

    def __init__(self, authors: Any, books: Any) -> None:
        self._authors = authors
        self._books = books

    async def get_by_id(self, author_id: int) -> Author | None:
        document = await self._authors.find_one({"id": Int64(author_id)})
        return author_from_document(document) if document is not None else None

    async def get_many(self, author_ids: tuple[int, ...]) -> tuple[Author, ...]:
        if not author_ids:
            return ()
        documents = await self._authors.find(
            {"id": {"$in": [Int64(i) for i in author_ids]}}
        ).to_list(length=len(author_ids))
        by_id = {int(document["id"]): author_from_document(document) for document in documents}
        return tuple(by_id[author_id] for author_id in author_ids if author_id in by_id)

    async def list(self) -> tuple[Author, ...]:
        documents = await self._authors.find({}).sort("id", ASCENDING).to_list(length=None)
        return tuple(author_from_document(document) for document in documents)

    async def list_with_book_counts(self) -> tuple[AuthorResult, ...]:
        pipeline = [
            {
                "$lookup": {
                    "from": "books",
                    "let": {"author_id": "$id"},
                    "pipeline": [
                        {"$match": {"$expr": {"$in": ["$$author_id", "$author_ids"]}}},
                        {"$count": "count"},
                    ],
                    "as": "book_count_rows",
                }
            },
            {
                "$project": {
                    "id": 1,
                    "name": 1,
                    "birth_date": 1,
                    "book_count": {"$ifNull": [{"$arrayElemAt": ["$book_count_rows.count", 0]}, 0]},
                }
            },
            {"$sort": {"id": ASCENDING}},
        ]
        documents = await self._authors.aggregate(pipeline).to_list(length=None)
        return tuple(
            AuthorResult(author_from_document(document), int(document["book_count"]))
            for document in documents
        )

    async def add(self, author: Author) -> None:
        await self._authors.insert_one(author_to_document(author))
