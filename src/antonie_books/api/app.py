"""FastAPI application factory and manual dependency wiring."""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI

from antonie_books.api.books import router as books_router
from antonie_books.api.dependencies import Services
from antonie_books.api.errors import register_exception_handlers
from antonie_books.api.reports import authors_router, publishers_router
from antonie_books.application.services import AuthorService, BookService, PublisherService
from antonie_books.config import Settings
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
    mongo_db = database.database
    book_repository = MongoBookRepository(mongo_db["books"], mongo_db["authors"])
    author_repository = MongoAuthorRepository(mongo_db["authors"])

    class SystemClock:
        def now(self) -> datetime:
            return datetime.now(UTC)

    if app.state.container is None:
        app.state.container = Services(
            book_service=BookService(
                book_repository=book_repository,
                author_repository=author_repository,
                book_id_generator=MongoBookIdGenerator(mongo_db["counters"]),
                clock=SystemClock(),
            ),
            author_service=AuthorService(author_repository, book_repository),
            publisher_service=PublisherService(book_repository),
        )
    try:
        yield
    finally:
        await client.close()


def create_app(
    settings: Settings | None = None,
    *,
    container: Services | None = None,
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
    app.state.container = container
    register_exception_handlers(app)
    app.include_router(books_router)
    app.include_router(authors_router)
    app.include_router(publishers_router)

    return app
