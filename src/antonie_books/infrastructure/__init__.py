"""MongoDB-backed infrastructure adapters."""

from antonie_books.infrastructure.mongo import MongoDatabase, connect_mongo
from antonie_books.infrastructure.repositories import (
    MongoAuthorRepository,
    MongoBookIdGenerator,
    MongoBookRepository,
)

__all__ = [
    "MongoAuthorRepository",
    "MongoBookIdGenerator",
    "MongoBookRepository",
    "MongoDatabase",
    "connect_mongo",
]
