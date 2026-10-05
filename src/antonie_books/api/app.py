"""FastAPI application factory and manual dependency wiring."""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI

from antonie_books.api.books import router as books_router
from antonie_books.api.config import Settings
from antonie_books.api.errors import register_exception_handlers
from antonie_books.application.services import AuthorService, BookService, PublisherService
from antonie_books.infrastructure.mongo import connect_mongo
from antonie_books.infrastructure.repositories import (
    MongoAuthorRepository,
    MongoBookIdGenerator,
    MongoBookRepository,
)

Lifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]


@asynccontextmanager
async def _mongo_lifespan(app: FastAPI):
    """Connect to MongoDB before serving requests and close the client on shutdown."""

    settings: Settings = app.state.settings
    client, database = await connect_mongo(settings.mongo_uri, settings.mongo_database)
    app.state.mongo_client = client
    app.state.mongo_database = database.database
    if app.state.use_mongo_services:
        mongo_db = database.database
        books = MongoBookRepository(mongo_db["books"], mongo_db["authors"])
        authors = MongoAuthorRepository(mongo_db["authors"], mongo_db["books"])

        class SystemClock:
            def now(self) -> datetime:
                return datetime.now(UTC)

        app.state.container = {
            "book_service": BookService(
                books, authors, MongoBookIdGenerator(mongo_db["counters"]), SystemClock()
            ),
            "author_service": AuthorService(authors, books),
            "publisher_service": PublisherService(books),
        }
    try:
        yield
    finally:
        await client.close()


def create_app(
    settings: Settings | None = None,
    *,
    container: object | None = None,
    lifespan: Lifespan | None = None,
) -> FastAPI:
    """Create a configured API instance with explicit dependencies and lifecycle."""

    runtime_settings = settings or Settings()

    @asynccontextmanager
    async def app_lifespan(app: FastAPI):
        lifecycle = lifespan or _mongo_lifespan
        async with lifecycle(app):
            yield

    app = FastAPI(title=runtime_settings.app_name, lifespan=app_lifespan)
    app.state.settings = runtime_settings
    app.state.container = container if container is not None else {}
    app.state.use_mongo_services = container is None
    register_exception_handlers(app)
    app.include_router(books_router)

    return app


__all__ = ["create_app"]
