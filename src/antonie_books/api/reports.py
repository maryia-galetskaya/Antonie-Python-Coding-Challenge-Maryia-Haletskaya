"""HTTP routes for author and publisher reports."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from antonie_books.api.books import _page_response
from antonie_books.api.dependencies import get_author_service, get_publisher_service
from antonie_books.api.schemas import (
    AuthorWithBookCountResponse,
    BookPageResponse,
    PublisherAverageResponse,
)
from antonie_books.application.dto import ListAuthorBooksInput, PublisherInput
from antonie_books.application.errors import PublisherNotFoundError
from antonie_books.application.services import AuthorService, PublisherService

authors_router = APIRouter(prefix="/authors", tags=["authors"])
publishers_router = APIRouter(prefix="/publishers", tags=["publishers"])
AuthorId = Annotated[int, Path(gt=0, le=2**63 - 1)]


@authors_router.get("", response_model=list[AuthorWithBookCountResponse])
async def list_authors(
    service: Annotated[AuthorService, Depends(get_author_service)],
) -> list[AuthorWithBookCountResponse]:
    return [
        AuthorWithBookCountResponse(
            id=result.author.id,
            name=result.author.name,
            birth_date=result.author.birth_date,
            book_count=result.book_count,
        )
        for result in await service.list_with_book_counts()
    ]


@authors_router.get("/{author_id}/books", response_model=BookPageResponse)
async def list_author_books(
    author_id: AuthorId,
    service: Annotated[AuthorService, Depends(get_author_service)],
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> BookPageResponse:
    result = await service.list_books(ListAuthorBooksInput(author_id, page, limit))
    return _page_response(result)


@publishers_router.get(
    "/{publisher_name:path}/average_pages", response_model=PublisherAverageResponse
)
async def publisher_average_pages(
    publisher_name: Annotated[str, Path(min_length=1)],
    service: Annotated[PublisherService, Depends(get_publisher_service)],
) -> PublisherAverageResponse:
    result = await service.get_average(PublisherInput(publisher_name))
    if result is None:
        raise PublisherNotFoundError(publisher_name)
    return PublisherAverageResponse(
        publisher=result.publisher,
        average_pages=result.average_pages,
        book_count=result.book_count,
    )
