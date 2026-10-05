"""Errors raised when domain invariants are violated."""


class DomainError(Exception):
    """Base class for expected domain failures."""

    code = "domain_error"


class InvalidDomainValue(DomainError, ValueError):
    """A domain value does not satisfy the business contract."""

    code = "invalid_domain_value"
