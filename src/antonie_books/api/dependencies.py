"""Manual dependency lookup used by API routers."""

from collections.abc import Mapping
from typing import Any

from fastapi import Request


def get_container(request: Request) -> object:
    """Return the application dependency container configured by ``create_app``."""

    return request.app.state.container


def service_dependency(service_name: str):
    """Build a FastAPI dependency that reads a named service from the container."""

    def get_service(request: Request) -> Any:
        container = get_container(request)
        if isinstance(container, Mapping):
            service = container.get(service_name)
        else:
            service = getattr(container, service_name, None)
        if service is None:
            raise RuntimeError(f"Application service {service_name!r} is not configured")
        return service

    get_service.__name__ = f"get_{service_name}"
    return get_service


get_book_service = service_dependency("book_service")
get_author_service = service_dependency("author_service")
get_publisher_service = service_dependency("publisher_service")

__all__ = [
    "get_author_service",
    "get_book_service",
    "get_container",
    "get_publisher_service",
    "service_dependency",
]
