"""FastAPI application factory and manual dependency wiring."""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from fastapi import FastAPI, Query

from antonie_books.api.config import Settings
from antonie_books.api.errors import register_exception_handlers
from antonie_books.infrastructure.mongo import connect_mongo

Lifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]


@asynccontextmanager
async def _mongo_lifespan(app: FastAPI):
    """Connect to MongoDB before serving requests and close the client on shutdown."""

    settings: Settings = app.state.settings
    client, database = await connect_mongo(settings.mongo_uri, settings.mongo_database)
    app.state.mongo_client = client
    app.state.mongo_database = database.database
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
    register_exception_handlers(app)

    @app.get("/books", tags=["books"])
    async def list_books(
        page: int = Query(default=1, ge=1), limit: int = Query(default=20, ge=1, le=100)
    ) -> dict[str, object]:
        """Temporary empty collection response used until the book routes are added."""

        return {"items": [], "page": page, "limit": limit, "total": 0}

    return app


__all__ = ["create_app"]
