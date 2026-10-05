"""Unit checks for the public book request validation contract."""

import pytest
from pydantic import ValidationError

from antonie_books.api.schemas import BookCreateRequest, BookPatchRequest

pytestmark = pytest.mark.unit

VALID_BOOK = {
    "title": "  Title ",
    "publisher": " Press  ",
    "author_ids": [1, 2],
    "pages": 42,
}


def test_create_schema_trims_text_and_deduplicates_tags_in_order() -> None:
    request = BookCreateRequest.model_validate({**VALID_BOOK, "tags": [" x ", "y", "x"]})

    assert request.title == "Title"
    assert request.publisher == "Press"
    assert request.tags == ["x", "y"]


@pytest.mark.parametrize(
    "payload",
    [
        {**VALID_BOOK, "pages": True},
        {**VALID_BOOK, "pages": 42.0},
        {**VALID_BOOK, "pages": "42"},
        {**VALID_BOOK, "pages": 2**63},
        {**VALID_BOOK, "author_ids": [1, 1]},
        {**VALID_BOOK, "author_ids": []},
        {**VALID_BOOK, "author_ids": [True]},
        {**VALID_BOOK, "author_ids": [1.5]},
        {**VALID_BOOK, "author_ids": ["1"]},
        {**VALID_BOOK, "title": "  "},
        {**VALID_BOOK, "tags": ["  "]},
        {**VALID_BOOK, "id": 1},
        {**VALID_BOOK, "created_at": "2025-01-01T00:00:00Z"},
        {**VALID_BOOK, "updated_at": "2025-01-01T00:00:00Z"},
    ],
)
def test_create_schema_rejects_invalid_contract_values(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        BookCreateRequest.model_validate(payload)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"title": None},
        {"title": "  "},
        {"pages": "2"},
        {"pages": None},
        {"author_ids": None},
        {"tags": [], "id": 1},
        {"extra": "field", "title": "valid"},
    ],
)
def test_patch_schema_rejects_empty_null_or_forbidden_values(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        BookPatchRequest.model_validate(payload)


def test_patch_schema_preserves_only_supplied_fields() -> None:
    request = BookPatchRequest.model_validate({"tags": [" one ", "one"]})

    assert request.model_dump(exclude_unset=True) == {"tags": ["one"]}
