from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from antonie_books.api.app import create_app
from antonie_books.api.config import Settings
from antonie_books.api.dependencies import get_book_service
from antonie_books.application.errors import DatabaseUnavailableError
from antonie_books.domain.errors import InvalidDomainValue

pytestmark = pytest.mark.unit


def test_factory_applies_settings_and_stores_manual_container() -> None:
    container = SimpleNamespace(book_service=object())
    settings = Settings(app_name="Books test API", mongo_database="books_test")

    app = create_app(settings, container=container)

    assert app.title == "Books test API"
    assert app.state.settings is settings
    assert app.state.container is container


def test_settings_read_environment_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTONIE_BOOKS_MONGO_DATABASE", "from_environment")

    assert Settings().mongo_database == "from_environment"


def test_domain_errors_use_structured_error_envelope() -> None:
    app = create_app()
    app.add_api_route("/domain-error", lambda: (_ for _ in ()).throw(InvalidDomainValue("bad")))

    response = TestClient(app).get("/domain-error")

    assert response.status_code == 422
    assert response.json() == {"error": {"code": "invalid_domain_value", "message": "bad"}}


def test_database_unavailable_returns_safe_503() -> None:
    app = create_app()
    app.add_api_route(
        "/database-error",
        lambda: (_ for _ in ()).throw(DatabaseUnavailableError("connection details")),
    )

    response = TestClient(app).get("/database-error")

    assert response.status_code == 503
    assert response.headers["retry-after"] == "1"
    assert response.json() == {
        "error": {
            "code": "database_unavailable",
            "message": "The database is temporarily unavailable.",
        }
    }
    assert "connection details" not in response.text


def test_unexpected_errors_return_safe_500() -> None:
    app = create_app()
    app.add_api_route(
        "/unexpected-error",
        lambda: (_ for _ in ()).throw(RuntimeError("sensitive detail")),
    )

    response = TestClient(app, raise_server_exceptions=False).get("/unexpected-error")

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "internal_server_error",
            "message": "An unexpected error occurred.",
        }
    }
    assert "sensitive detail" not in response.text


def test_request_validation_keeps_fastapi_422_format() -> None:
    app = create_app()

    def endpoint(value: int) -> int:
        return value

    app.add_api_route("/validation", endpoint)

    response = TestClient(app).get("/validation", params={"value": "not-an-integer"})

    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == "int_parsing"
    assert "error" not in response.json()


def test_router_dependency_resolves_named_service_from_container() -> None:
    service = object()
    app = create_app(container={"book_service": service})

    def endpoint(injected: object = Depends(get_book_service)) -> bool:
        return injected is service

    app.add_api_route("/service", endpoint)

    response = TestClient(app).get("/service")

    assert response.status_code == 200
    assert response.json() is True


def test_lifespan_hook_is_entered_and_exited() -> None:
    events: list[str] = []

    @asynccontextmanager
    async def lifecycle(app: FastAPI):
        assert app.state.settings is not None
        events.append("started")
        yield
        events.append("stopped")

    with TestClient(create_app(lifespan=lifecycle)):
        assert events == ["started"]

    assert events == ["started", "stopped"]
