"""HTTP exception handlers for expected and unexpected application failures."""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from antonie_books.application.errors import (
    AuthorNotFoundError,
    BookNotFoundError,
    DatabaseUnavailableError,
    DataIntegrityError,
    PublisherNotFoundError,
)
from antonie_books.domain.errors import DomainError

logger = logging.getLogger(__name__)


async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    """Render expected business failures using the public error envelope."""

    del request
    return JSONResponse(
        status_code=422,
        content={"error": {"code": exc.code, "message": str(exc)}},
    )


async def book_not_found_handler(request: Request, exc: BookNotFoundError) -> JSONResponse:
    """Render missing books as a stable not-found response."""

    del request
    return JSONResponse(
        status_code=404,
        content={"error": {"code": exc.code, "message": str(exc)}},
    )


async def author_not_found_handler(request: Request, exc: AuthorNotFoundError) -> JSONResponse:
    """Render unknown author resources as a stable not-found response."""

    del request
    return JSONResponse(
        status_code=404,
        content={"error": {"code": exc.code, "message": str(exc)}},
    )


async def publisher_not_found_handler(
    request: Request, exc: PublisherNotFoundError
) -> JSONResponse:
    """Render unknown publisher reports as a stable not-found response."""

    del request
    return JSONResponse(
        status_code=404,
        content={"error": {"code": exc.code, "message": str(exc)}},
    )


async def database_unavailable_handler(
    request: Request, exc: DatabaseUnavailableError
) -> JSONResponse:
    """Return a stable 503 response when storage is temporarily unavailable."""

    del request
    logger.warning("Database unavailable while handling request: %s", exc)
    return JSONResponse(
        status_code=503,
        content={
            "error": {
                "code": "database_unavailable",
                "message": "The database is temporarily unavailable.",
            }
        },
        headers={"Retry-After": "1"},
    )


async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Log unexpected failures and return no internal exception details to clients."""

    logger.exception("Unhandled error while handling %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_server_error",
                "message": "An unexpected error occurred.",
            }
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register application exception handlers, leaving FastAPI validation intact."""

    app.add_exception_handler(DomainError, domain_error_handler)
    app.add_exception_handler(BookNotFoundError, book_not_found_handler)
    app.add_exception_handler(AuthorNotFoundError, author_not_found_handler)
    app.add_exception_handler(PublisherNotFoundError, publisher_not_found_handler)
    app.add_exception_handler(DatabaseUnavailableError, database_unavailable_handler)
    app.add_exception_handler(DataIntegrityError, unexpected_error_handler)
    app.add_exception_handler(Exception, unexpected_error_handler)
