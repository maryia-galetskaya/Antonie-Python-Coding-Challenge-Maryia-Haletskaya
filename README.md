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
