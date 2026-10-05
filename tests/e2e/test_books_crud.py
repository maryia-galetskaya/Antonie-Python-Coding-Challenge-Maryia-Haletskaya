"""Book CRUD contract exercised over HTTP against the Compose API and MongoDB."""

from datetime import datetime

import pytest
from bson import Int64
from pymongo import MongoClient

pytestmark = pytest.mark.e2e


def _insert_authors(e2e_database_name: str) -> None:
    with MongoClient(
        "mongodb://localhost:27018/?retryWrites=false", serverSelectionTimeoutMS=5_000
    ) as client:
        authors = client[e2e_database_name]["authors"]
        authors.delete_many({})
        authors.insert_many(
            [
                {"id": Int64(901), "name": " Ada Lovelace ", "birth_date": None},
                {"id": Int64(902), "name": "Grace Hopper", "birth_date": datetime(1906, 12, 9)},
            ]
        )


def test_book_http_crud_lifecycle(api_client, e2e_database_name: str) -> None:
    _insert_authors(e2e_database_name)
    create = api_client.post(
        "/books",
        json={
            "title": "  Analytical Engines  ",
            "publisher": "  Example Press ",
            "author_ids": [901, 902],
            "pages": 321,
            "tags": [" history ", "math", "history"],
        },
    )

    assert create.status_code == 201, create.text
    book = create.json()
    assert create.headers["location"] == f"/books/{book['id']}"
    assert book["id"] > 0
    assert book["title"] == "Analytical Engines"
    assert book["publisher"] == "Example Press"
    assert book["author_ids"] == [901, 902]
    assert book["authors"] == [
        {"id": 901, "name": "Ada Lovelace", "birth_date": None},
        {"id": 902, "name": "Grace Hopper", "birth_date": "1906-12-09"},
    ]
    assert book["pages"] == 321
    assert book["tags"] == ["history", "math"]
    created_at = datetime.fromisoformat(book["created_at"].replace("Z", "+00:00"))
    updated_at = datetime.fromisoformat(book["updated_at"].replace("Z", "+00:00"))
    assert created_at.tzinfo is not None
    assert updated_at.tzinfo is not None
    assert created_at.utcoffset().total_seconds() == 0
    assert updated_at.utcoffset().total_seconds() == 0
    assert created_at.microsecond % 1000 == updated_at.microsecond % 1000 == 0
    assert updated_at == created_at

    listed = api_client.get("/books", params={"page": 1, "limit": 10})
    assert listed.status_code == 200
    assert listed.json() == {"items": [book], "page": 1, "limit": 10, "total": 1}

    fetched = api_client.get(create.headers["location"])
    assert fetched.status_code == 200
    assert fetched.json() == book

    patched = api_client.patch(
        create.headers["location"], json={"title": "  Revised Title  ", "tags": [" new ", "new"]}
    )
    assert patched.status_code == 200, patched.text
    changed = patched.json()
    assert changed["id"] == book["id"]
    assert changed["title"] == "Revised Title"
    assert changed["publisher"] == book["publisher"]
    assert changed["author_ids"] == book["author_ids"]
    assert changed["authors"] == book["authors"]
    assert changed["pages"] == book["pages"]
    assert changed["tags"] == ["new"]
    assert changed["created_at"] == book["created_at"]
    updated_at = datetime.fromisoformat(changed["updated_at"].replace("Z", "+00:00"))
    assert updated_at.tzinfo is not None
    assert updated_at.microsecond % 1000 == 0
    assert updated_at > created_at

    deleted = api_client.delete(create.headers["location"])
    assert deleted.status_code == 204
    assert deleted.content == b""
    assert api_client.delete(create.headers["location"]).status_code == 404
    assert api_client.get(create.headers["location"]).status_code == 404


def test_book_http_errors_and_strict_validation(api_client, e2e_database_name: str) -> None:
    _insert_authors(e2e_database_name)
    payload = {
        "title": "Valid",
        "publisher": "Press",
        "author_ids": [901],
        "pages": 10,
    }
    invalid_payloads = [
        {**payload, "id": 1},
        {**payload, "created_at": "2025-01-01T00:00:00Z"},
        {**payload, "updated_at": "2025-01-01T00:00:00Z"},
        {**payload, "title": "   "},
        {**payload, "pages": True},
        {**payload, "pages": 10.0},
        {**payload, "pages": "10"},
        {**payload, "pages": 2**63},
        {**payload, "author_ids": [901.5]},
        {**payload, "author_ids": ["901"]},
        {**payload, "author_ids": []},
        {**payload, "author_ids": [901, 901]},
        {**payload, "tags": ["  "]},
    ]
    for invalid in invalid_payloads:
        response = api_client.post("/books", json=invalid)
        assert response.status_code == 422, (invalid, response.text)

    unknown_author = api_client.post("/books", json={**payload, "author_ids": [999_999]})
    assert unknown_author.status_code == 422
    assert unknown_author.json()["error"]["code"] == "author_not_found"

    created = api_client.post("/books", json=payload)
    assert created.status_code == 201, created.text
    location = created.headers["location"]
    original_book = created.json()

    unknown_author_patch = api_client.patch(location, json={"author_ids": [999_999]})
    assert unknown_author_patch.status_code == 422
    assert unknown_author_patch.json()["error"]["code"] == "author_not_found"
    unchanged_book = api_client.get(location)
    assert unchanged_book.status_code == 200
    assert unchanged_book.json() == original_book

    missing = api_client.get("/books/9223372036854775807")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "book_not_found"

    invalid_patches = (
        {},
        {"title": None},
        {"id": 1},
        {"created_at": "2025-01-01"},
        {"pages": False},
        {"pages": None},
        {"author_ids": None},
        {"unexpected": "field"},
    )
    for invalid_patch in invalid_patches:
        response = api_client.patch("/books/1", json=invalid_patch)
        assert response.status_code == 422, (invalid_patch, response.text)
