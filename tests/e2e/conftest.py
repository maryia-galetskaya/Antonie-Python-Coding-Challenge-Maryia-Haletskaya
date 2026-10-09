"""HTTP fixtures for tests against the API and MongoDB Compose services."""

import os
import time
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from pymongo import MongoClient, timeout
from pymongo.errors import PyMongoError

E2E_DATABASE_PREFIX = "antonie_e2e_"


@pytest.fixture(scope="session")
def e2e_database_name() -> str:
    database_name = os.getenv("ANTONIE_BOOKS_MONGO_DATABASE", "antonie_e2e_books")
    if not database_name.startswith(E2E_DATABASE_PREFIX):
        raise RuntimeError(
            f"Refusing to clean database {database_name!r}; expected {E2E_DATABASE_PREFIX!r}"
        )
    return database_name


@pytest.fixture(scope="session")
def e2e_mongo_client() -> Iterator[MongoClient[Any]]:
    mongo_uri = os.getenv("ANTONIE_BOOKS_MONGO_URI", "mongodb://127.0.0.1:27018/?retryWrites=false")
    client = MongoClient(
        mongo_uri,
        timeoutMS=2_000,
        serverSelectionTimeoutMS=2_000,
        connectTimeoutMS=2_000,
    )
    deadline = time.monotonic() + 20
    last_error: PyMongoError | None = None
    try:
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            try:
                with timeout(min(1.0, remaining)):
                    client.admin.command("ping", maxTimeMS=1_000)
                break
            except PyMongoError as exc:
                last_error = exc
                time.sleep(min(0.25, max(0, deadline - time.monotonic())))
        else:
            raise RuntimeError("MongoDB did not become ready within 20 seconds") from last_error
        yield client
    finally:
        client.close()


@pytest.fixture
def e2e_database(e2e_mongo_client: MongoClient[Any], e2e_database_name: str):
    return e2e_mongo_client[e2e_database_name]


@pytest.fixture(autouse=True)
def clean_e2e_database(e2e_database) -> Iterator[None]:
    """Isolate each HTTP test while retaining the persistent allocation counter."""
    for collection in ("books", "authors"):
        e2e_database[collection].delete_many({})
    yield
    for collection in ("books", "authors"):
        e2e_database[collection].delete_many({})


@pytest.fixture(scope="session")
def api_client(e2e_database_name: str) -> Iterator[httpx.Client]:
    del e2e_database_name
    base_url = os.getenv("ANTONIE_BOOKS_E2E_URL", "http://127.0.0.1:8001")
    client = httpx.Client(base_url=base_url, timeout=2.0)
    deadline = time.monotonic() + 30
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            remaining = deadline - time.monotonic()
            response = client.get("/books", timeout=max(0.1, min(2.0, remaining)))
            if response.status_code == 200:
                break
            last_error = RuntimeError(f"GET /books returned {response.status_code}")
        except httpx.HTTPError as exc:
            last_error = exc
        time.sleep(min(0.25, max(0, deadline - time.monotonic())))
    else:
        client.close()
        raise RuntimeError("API did not become ready within 30 seconds") from last_error
    yield client
    client.close()
