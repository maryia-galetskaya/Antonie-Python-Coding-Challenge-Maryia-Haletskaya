"""Application-layer failures that are not domain validation errors."""


class DatabaseUnavailableError(RuntimeError):
    """Raised when a request cannot use the configured database."""


__all__ = ["DatabaseUnavailableError"]
