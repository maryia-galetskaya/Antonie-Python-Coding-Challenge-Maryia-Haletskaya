"""Search and pagination inputs shared by book query use cases."""

from dataclasses import dataclass

from antonie_books.domain.errors import InvalidDomainValue


@dataclass(frozen=True, slots=True)
class PageRequest:
    page: int = 1
    limit: int = 20

    def __post_init__(self) -> None:
        for name, value in (("page", self.page), ("limit", self.limit)):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise InvalidDomainValue(f"{name} must be a positive integer")
        if self.limit > 100:
            raise InvalidDomainValue("limit must not exceed 100")


@dataclass(frozen=True, slots=True)
class BookFilter:
    """Combined filters; repositories apply all populated filters with AND semantics."""

    author: str | None = None
    title: str | None = None
    tags: tuple[str, ...] = ()
    page: PageRequest = PageRequest()

    def __post_init__(self) -> None:
        if not isinstance(self.page, PageRequest):
            raise InvalidDomainValue("page must be a PageRequest")
        for name in ("author", "title"):
            value = getattr(self, name)
            if value is not None:
                if not isinstance(value, str) or not value.strip():
                    raise InvalidDomainValue(f"{name} filter must not be empty")
                object.__setattr__(self, name, value.strip())
        tags = tuple(self.tags)
        if any(not isinstance(tag, str) or not tag.strip() for tag in tags):
            raise InvalidDomainValue("tag filters must not be empty")
        object.__setattr__(self, "tags", tags)
