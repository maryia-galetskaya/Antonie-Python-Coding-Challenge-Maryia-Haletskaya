"""FastAPI application factory and manual dependency wiring."""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from fastapi import FastAPI

from antonie_books.api.config import Settings
from antonie_books.api.errors import register_exception_handlers

Lifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]


@asynccontextmanager
async def _empty_lifespan(app: FastAPI):
    """Default no-op lifespan, replaceable with storage initialization later."""

    del app
    yield


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
        lifecycle = lifespan or _empty_lifespan
        async with lifecycle(app):
            yield

    app = FastAPI(title=runtime_settings.app_name, lifespan=app_lifespan)
    app.state.settings = runtime_settings
    app.state.container = container if container is not None else {}
    register_exception_handlers(app)
    return app


__all__ = ["create_app"]
