"""Compatibility import; use app.heva_app.main."""

from app.heva_app.main import app, create_app, main

__all__ = ["app", "create_app", "main"]
