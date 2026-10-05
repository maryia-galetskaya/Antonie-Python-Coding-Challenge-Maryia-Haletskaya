"""HTTP fixtures for tests against the API and MongoDB Compose services."""

import os
import time
from collections.abc import Iterator

import httpx
import pytest
from pymongo import MongoClient

E2E_DATABASE_PREFIX = "antonie_e2e_"


@pytest.fixture(scope="session")
def e2e_database_name() -> str:
    """Return the configured test database only after checking its safety prefix."""

    database_name = os.getenv("ANTONIE_BOOKS_MONGO_DATABASE", "antonie_e2e_books")
    if not database_name.startswith(E2E_DATABASE_PREFIX):
        raise RuntimeError(
            f"Refusing to clean database {database_name!r}; "
            f"e2e databases must start with {E2E_DATABASE_PREFIX!r}"
        )
    return database_name


@pytest.fixture(scope="session")
def api_client(e2e_database_name: str) -> Iterator[httpx.Client]:
    """Poll the API over HTTP until ready after the guarded database cleanup fixture."""

    del e2e_database_name
    base_url = os.getenv("ANTONIE_BOOKS_E2E_URL", "http://localhost:8001")
    client = httpx.Client(base_url=base_url, timeout=2.0)
    deadline = time.monotonic() + 60
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            response = client.get("/books")
            if response.status_code == 200:
                break
            last_error = RuntimeError(f"GET /books returned {response.status_code}")
        except httpx.HTTPError as exc:
            last_error = exc
        time.sleep(0.5)
    else:
        client.close()
        raise RuntimeError("API did not become ready within 60 seconds") from last_error

    yield client
    client.close()


@pytest.fixture(scope="session", autouse=True)
def clean_e2e_database(e2e_database_name: str) -> Iterator[None]:
    """Clear e2e records while preserving the startup-initialized ID counter."""

    mongo_uri = os.getenv("ANTONIE_BOOKS_MONGO_URI", "mongodb://localhost:27018/?retryWrites=false")
    with MongoClient(mongo_uri, serverSelectionTimeoutMS=5_000) as client:
        database = client[e2e_database_name]
        database["books"].delete_many({})
        database["authors"].delete_many({})
        yield
        database["books"].delete_many({})
        database["authors"].delete_many({})
