"""Typed FastAPI dependencies for the application service container."""

from dataclasses import dataclass

from fastapi import Request

from antonie_books.application.services import AuthorService, BookService, PublisherService


@dataclass(slots=True)
class Services:
    book_service: BookService
    author_service: AuthorService
    publisher_service: PublisherService


def get_container(request: Request) -> Services:
    return request.app.state.container


def get_book_service(request: Request) -> BookService:
    return get_container(request).book_service


def get_author_service(request: Request) -> AuthorService:
    return get_container(request).author_service


def get_publisher_service(request: Request) -> PublisherService:
    return get_container(request).publisher_service
