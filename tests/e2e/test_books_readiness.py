import pytest

pytestmark = pytest.mark.e2e


def test_e2e_database_is_isolated(e2e_database_name: str) -> None:
    assert e2e_database_name.startswith("antonie_e2e_")


def test_books_list_is_available_over_http(api_client) -> None:
    response = api_client.get("/books")

    assert response.status_code == 200
    assert response.json() == {"items": [], "page": 1, "limit": 20, "total": 0}


def test_books_list_honors_pagination_parameters(api_client) -> None:
    response = api_client.get("/books", params={"page": 2, "limit": 5})

    assert response.status_code == 200
    assert response.json() == {"items": [], "page": 2, "limit": 5, "total": 0}
