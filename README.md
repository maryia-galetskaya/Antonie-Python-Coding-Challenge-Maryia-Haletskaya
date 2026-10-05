# Antonie Books API

A Python API for managing books and authors, built as a coding challenge. The planned stack is FastAPI and MongoDB, with numeric public IDs for books and authors.

## Project status

Implementation is in progress. The API will support book management, author and publisher queries, filtering, and pagination. Authors are initialized from repeatable demo seed data. See the project plan and API contract for the intended behavior.

## Planned development

- Python 3.14.8 and `uv` for dependency and environment management.
- FastAPI with a `src`-layout package and separated domain, application, infrastructure, and API layers.
- MongoDB 8.0 for persistence and Docker Compose for local and end-to-end environments.
- Unit tests for services and HTTP end-to-end tests against MongoDB.

Setup, configuration, API usage, and test instructions will be added as the implementation is completed.

## Docker development and end-to-end tests

Start the development API and persistent MongoDB with `docker compose up --build`. The API is
available at `http://localhost:8000`; MongoDB is available on port `27017`. Stop the services with
`docker compose down` (add `-v` only when you want to remove the development database volume).

Run the isolated end-to-end environment with `docker compose -f compose.e2e.yaml up --build -d`,
then run `uv run pytest -m e2e`. The tests use ordinary HTTP requests to
`http://localhost:8001` and poll `/books` for up to 60 seconds. The e2e service uses database
`antonie_e2e_books` and temporary MongoDB storage; its cleanup fixture refuses database names
outside the `antonie_e2e_` prefix. Stop it with `docker compose -f compose.e2e.yaml down`.
Pytest is configured with `pytest-xdist -n 0` to run sequentially because the e2e suite shares one
disposable database.
