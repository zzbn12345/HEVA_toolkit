"""Shared, dependency-light exceptions for HEVA source adapters."""


class ExtractionCancelled(RuntimeError):
    """Raised at a safe adapter boundary after a user requests cancellation."""
