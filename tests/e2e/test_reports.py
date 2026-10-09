"""Author and publisher report contracts exercised over HTTP."""

from datetime import datetime

import pytest
from bson import Int64

pytestmark = pytest.mark.e2e


def _reset_records(database) -> None:
    database["books"].delete_many({})
    database["authors"].insert_many(
        [
            {"id": Int64(971), "name": "Ada Lovelace", "birth_date": datetime(1815, 12, 10)},
            {"id": Int64(972), "name": "Grace Hopper", "birth_date": None},
            {"id": Int64(973), "name": "Katherine Johnson", "birth_date": None},
        ]
    )


def _create_book(api_client, *, title: str, publisher: str, author_ids: list[int], pages: int):
    response = api_client.post(
        "/books",
        json={
            "title": title,
            "publisher": publisher,
            "author_ids": author_ids,
            "pages": pages,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_author_reports(api_client, e2e_database) -> None:
    _reset_records(e2e_database)
    first = _create_book(
        api_client,
        title="Analytical Engines",
        publisher="North/Star Press",
        author_ids=[971, 972],
        pages=100,
    )
    second = _create_book(
        api_client,
        title="Computing Machinery",
        publisher="North/Star Press",
        author_ids=[972],
        pages=201,
    )

    authors = api_client.get("/authors")
    assert authors.status_code == 200, authors.text
    assert authors.json() == [
        {"id": 971, "name": "Ada Lovelace", "birth_date": "1815-12-10", "book_count": 1},
        {"id": 972, "name": "Grace Hopper", "birth_date": None, "book_count": 2},
        {"id": 973, "name": "Katherine Johnson", "birth_date": None, "book_count": 0},
    ]

    first_page = api_client.get("/authors/972/books", params={"page": 1, "limit": 1})
    assert first_page.status_code == 200, first_page.text
    assert first_page.json() == {
        "items": [first],
        "page": 1,
        "limit": 1,
        "total": 2,
    }
    second_page = api_client.get("/authors/972/books", params={"page": 2, "limit": 1})
    assert second_page.status_code == 200, second_page.text
    assert second_page.json() == {
        "items": [second],
        "page": 2,
        "limit": 1,
        "total": 2,
    }
    empty = api_client.get("/authors/973/books")
    assert empty.status_code == 200
    assert empty.json() == {"items": [], "page": 1, "limit": 20, "total": 0}
    missing_author = api_client.get("/authors/999999/books")
    assert missing_author.status_code == 404
    assert missing_author.json()["error"]["code"] == "author_not_found"


def test_publisher_average_pages_report(api_client, e2e_database) -> None:
    _reset_records(e2e_database)
    first = _create_book(
        api_client,
        title="Analytical Engines",
        publisher="North/Star Press",
        author_ids=[971, 972],
        pages=100,
    )
    second = _create_book(
        api_client,
        title="Computing Machinery",
        publisher="North/Star Press",
        author_ids=[972],
        pages=201,
    )

    encoded_name = "North%2FStar%20Press"
    average = api_client.get(f"/publishers/{encoded_name}/average_pages")
    assert average.status_code == 200, average.text
    assert average.json() == {
        "publisher": "North/Star Press",
        "average_pages": 150.5,
        "book_count": 2,
    }
    assert api_client.get("/publishers/north%2FStar%20Press/average_pages").status_code == 404
    assert api_client.get("/publishers/Missing%2FPress/average_pages").status_code == 404

    patched = api_client.patch(f"/books/{first['id']}", json={"pages": 200})
    assert patched.status_code == 200, patched.text
    assert api_client.get(f"/publishers/{encoded_name}/average_pages").json() == {
        "publisher": "North/Star Press",
        "average_pages": 200.5,
        "book_count": 2,
    }
    deleted = api_client.delete(f"/books/{second['id']}")
    assert deleted.status_code == 204
    assert api_client.get(f"/publishers/{encoded_name}/average_pages").json() == {
        "publisher": "North/Star Press",
        "average_pages": 200.0,
        "book_count": 1,
    }
