"""HTTP routes for creating and managing books."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response, status

from antonie_books.api.dependencies import get_book_service
from antonie_books.api.schemas import (
    BookCreateRequest,
    BookPageResponse,
    BookPatchRequest,
    BookResponse,
    NonEmptyFilter,
)
from antonie_books.application.dto import (
    BookIdInput,
    BookOutput,
    BookPageOutput,
    CreateBookInput,
    ListBooksInput,
    UpdateBookInput,
)
from antonie_books.application.services import BookService

router = APIRouter(prefix="/books", tags=["books"])
BookId = Annotated[int, Path(gt=0, le=2**63 - 1)]


def _response(book: BookOutput) -> BookResponse:
    return BookResponse(
        id=book.id,
        title=book.title,
        publisher=book.publisher,
        author_ids=list(book.author_ids),
        authors=[
            {"id": author.id, "name": author.name, "birth_date": author.birth_date}
            for author in book.authors
        ],
        pages=book.pages,
        tags=list(book.tags),
        created_at=book.created_at,
        updated_at=book.updated_at,
    )


def _page_response(result: BookPageOutput) -> BookPageResponse:
    return BookPageResponse(
        items=[_response(item) for item in result.items],
        page=result.page,
        limit=result.limit,
        total=result.total,
    )


@router.post("", response_model=BookResponse, status_code=status.HTTP_201_CREATED)
async def create_book(
    payload: BookCreateRequest,
    response: Response,
    service: Annotated[BookService, Depends(get_book_service)],
) -> BookResponse:
    result = await service.create(
        CreateBookInput(
            title=payload.title,
            publisher=payload.publisher,
            author_ids=tuple(payload.author_ids),
            pages=payload.pages,
            tags=tuple(payload.tags),
        )
    )
    response.headers["Location"] = f"/books/{result.id}"
    return _response(result)


@router.get("", response_model=BookPageResponse)
async def list_books(
    service: Annotated[BookService, Depends(get_book_service)],
    author: Annotated[NonEmptyFilter | None, Query()] = None,
    title: Annotated[NonEmptyFilter | None, Query()] = None,
    tags: Annotated[list[NonEmptyFilter] | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> BookPageResponse:
    result = await service.list(
        ListBooksInput(
            author=author,
            title=title,
            tags=tuple(tags or ()),
            page=page,
            limit=limit,
        )
    )
    return _page_response(result)


@router.get("/{book_id}", response_model=BookResponse)
async def get_book(
    book_id: BookId, service: Annotated[BookService, Depends(get_book_service)]
) -> BookResponse:
    return _response(await service.get(BookIdInput(book_id)))


@router.patch("/{book_id}", response_model=BookResponse)
async def update_book(
    book_id: BookId,
    payload: BookPatchRequest,
    service: Annotated[BookService, Depends(get_book_service)],
) -> BookResponse:
    changes = payload.model_dump(exclude_unset=True)
    if "author_ids" in changes:
        changes["author_ids"] = tuple(changes["author_ids"])
    if "tags" in changes:
        changes["tags"] = tuple(changes["tags"])
    return _response(await service.update(UpdateBookInput(book_id=book_id, **changes)))


@router.delete("/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_book(
    book_id: BookId,
    service: Annotated[BookService, Depends(get_book_service)],
) -> Response:
    await service.delete(BookIdInput(book_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
