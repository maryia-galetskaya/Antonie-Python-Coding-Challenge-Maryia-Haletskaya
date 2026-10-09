"""Book CRUD contract exercised over HTTP against the Compose API and MongoDB."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import httpx
import pytest
from bson import Int64

pytestmark = pytest.mark.e2e


def _insert_authors(e2e_database) -> None:
    authors = e2e_database["authors"]
    authors.delete_many({})
    authors.insert_many(
        [
            {"id": Int64(901), "name": " Ada Lovelace ", "birth_date": None},
            {"id": Int64(902), "name": "Grace Hopper", "birth_date": datetime(1906, 12, 9)},
        ]
    )


def test_book_http_crud_lifecycle(api_client, e2e_database) -> None:
    _insert_authors(e2e_database)
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
    assert updated_at >= created_at

    deleted = api_client.delete(create.headers["location"])
    assert deleted.status_code == 204
    assert deleted.content == b""
    assert api_client.delete(create.headers["location"]).status_code == 404
    assert api_client.get(create.headers["location"]).status_code == 404


def test_parallel_book_posts_receive_unique_ids(api_client, e2e_database) -> None:
    _insert_authors(e2e_database)
    payload = {
        "title": "Concurrent allocation",
        "publisher": "Parallel Press",
        "author_ids": [901],
        "pages": 100,
    }

    def post_book(_: int) -> httpx.Response:
        with httpx.Client(base_url=str(api_client.base_url), timeout=10.0) as client:
            return client.post("/books", json=payload)

    with ThreadPoolExecutor(max_workers=12) as executor:
        responses = list(executor.map(post_book, range(24)))

    assert [response.status_code for response in responses] == [201] * 24, [
        response.text for response in responses
    ]
    public_ids = [response.json()["id"] for response in responses]
    assert len(set(public_ids)) == len(public_ids)


def test_deleted_book_id_is_not_reused(api_client, e2e_database) -> None:
    _insert_authors(e2e_database)
    payload = {
        "title": "Deleted ID reservation",
        "publisher": "Monotonic Press",
        "author_ids": [901],
        "pages": 100,
    }

    deleted_candidate = api_client.post("/books", json=payload)
    assert deleted_candidate.status_code == 201, deleted_candidate.text
    deleted_id = deleted_candidate.json()["id"]
    deletion = api_client.delete(deleted_candidate.headers["location"])
    assert deletion.status_code == 204

    replacement = api_client.post("/books", json=payload)
    assert replacement.status_code == 201, replacement.text
    assert replacement.json()["id"] != deleted_id
    assert replacement.json()["id"] > deleted_id


def test_book_create_rejects_invalid_payloads(api_client, e2e_database) -> None:
    _insert_authors(e2e_database)
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

    books_before_invalid_create = api_client.get("/books").json()["total"]
    unknown_author = api_client.post("/books", json={**payload, "author_ids": [999_999]})
    assert unknown_author.status_code == 422
    assert unknown_author.json()["error"]["code"] == "author_not_found"
    assert api_client.get("/books").json()["total"] == books_before_invalid_create


def test_book_patch_rejects_invalid_payloads(api_client, e2e_database) -> None:
    _insert_authors(e2e_database)
    created = api_client.post(
        "/books",
        json={"title": "Valid", "publisher": "Press", "author_ids": [901], "pages": 10},
    )
    assert created.status_code == 201, created.text
    location = created.headers["location"]
    original_book = created.json()
    unknown_author_patch = api_client.patch(location, json={"author_ids": [999_999]})
    assert unknown_author_patch.status_code == 422
    assert unknown_author_patch.json()["error"]["code"] == "author_not_found"
    unchanged_book = api_client.get(location)
    assert unchanged_book.status_code == 200
    assert unchanged_book.json() == original_book

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
        response = api_client.patch(location, json=invalid_patch)
        assert response.status_code == 422, (invalid_patch, response.text)


def test_missing_books_and_authors_return_not_found(api_client) -> None:
    missing_author_books = api_client.get("/authors/999999/books")
    assert missing_author_books.status_code == 404
    assert missing_author_books.json()["error"]["code"] == "author_not_found"

    missing = api_client.get("/books/9223372036854775807")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "book_not_found"


def _create_filter_books(api_client, e2e_database) -> list[dict]:
    _insert_authors(e2e_database)
    fixtures = [
        ("Python [Regex] Guide", [901], ["Python", "Development"]),
        ("Python in Practice", [902, 903], ["Python", "Development"]),
        ("Rust [Regex] Guide", [903], ["Development"]),
        ("Python Basics", [901], ["python"]),
    ]
    e2e_database["authors"].insert_one(
        {"id": Int64(903), "name": "Bob Gregory", "birth_date": None}
    )
    created_books = []
    for title, author_ids, tags in fixtures:
        response = api_client.post(
            "/books",
            json={
                "title": title,
                "publisher": "Filter Press",
                "author_ids": author_ids,
                "pages": 100,
                "tags": tags,
            },
        )
        assert response.status_code == 201, response.text
        created_books.append(response.json())
    return created_books


def test_book_filters(api_client, e2e_database) -> None:
    _create_filter_books(api_client, e2e_database)
    literal_regex = api_client.get("/books", params={"title": "[Regex]"})
    assert literal_regex.status_code == 200
    assert [item["title"] for item in literal_regex.json()["items"]] == [
        "Python [Regex] Guide",
        "Rust [Regex] Guide",
    ]

    coauthor = api_client.get("/books", params={"author": "gRaCe"})
    assert coauthor.status_code == 200
    assert [item["title"] for item in coauthor.json()["items"]] == ["Python in Practice"]

    and_filters = api_client.get(
        "/books",
        params=[
            ("author", "bob"),
            ("title", "python"),
            ("tags", "Python"),
            ("tags", "Development"),
        ],
    )
    assert and_filters.status_code == 200
    assert [item["title"] for item in and_filters.json()["items"]] == ["Python in Practice"]
    assert and_filters.json()["total"] == 1

    tag_case = api_client.get("/books", params=[("tags", "Python"), ("tags", "Development")])
    assert [item["title"] for item in tag_case.json()["items"]] == [
        "Python [Regex] Guide",
        "Python in Practice",
    ]
    lower_tag = api_client.get("/books", params={"tags": "python"})
    assert [item["title"] for item in lower_tag.json()["items"]] == ["Python Basics"]


def test_book_pagination(api_client, e2e_database) -> None:
    created_books = _create_filter_books(api_client, e2e_database)
    page_one = api_client.get("/books", params={"page": 1, "limit": 2})
    page_two = api_client.get("/books", params={"page": 2, "limit": 2})
    beyond = api_client.get("/books", params={"page": 3, "limit": 2})
    deep_page = api_client.get("/books", params={"page": 101, "limit": 2})
    assert (
        page_one.status_code
        == page_two.status_code
        == beyond.status_code
        == deep_page.status_code
        == 200
    )
    assert [item["id"] for item in page_one.json()["items"]] == [
        created_books[0]["id"],
        created_books[1]["id"],
    ]
    assert [item["id"] for item in page_two.json()["items"]] == [
        created_books[2]["id"],
        created_books[3]["id"],
    ]
    assert page_one.json()["total"] == page_two.json()["total"] == beyond.json()["total"] == 4
    assert beyond.json()["items"] == []
    assert deep_page.json() == {"items": [], "page": 101, "limit": 2, "total": 4}

    filtered_page = api_client.get("/books", params={"title": "python", "page": 2, "limit": 1})
    assert filtered_page.json()["total"] == 3
    assert [item["title"] for item in filtered_page.json()["items"]] == ["Python in Practice"]
    filtered_deep_page = api_client.get(
        "/books", params={"title": "python", "page": 101, "limit": 1}
    )
    assert filtered_deep_page.json() == {
        "items": [],
        "page": 101,
        "limit": 1,
        "total": 3,
    }

    assert api_client.get("/books", params={"page": 100, "limit": 100}).status_code == 200


@pytest.mark.parametrize("params", [{"author": "   "}, {"title": "   "}, {"tags": "   "}])
def test_book_filters_reject_empty_values(api_client, params) -> None:
    response = api_client.get("/books", params=params)
    assert response.status_code == 422, (params, response.text)


@pytest.mark.parametrize(
    "params",
    [
        {"page": 0},
        {"limit": 0},
        {"limit": 101},
    ],
)
def test_book_pagination_rejects_invalid_bounds(api_client, params) -> None:
    response = api_client.get("/books", params=params)
    assert response.status_code == 422, (params, response.text)
