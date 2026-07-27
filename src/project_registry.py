"""Compatibility entry point; use management.heva_management.project_registry."""

from management.heva_management.project_registry import *  # noqa: F403
from management.heva_management.project_registry import main

if __name__ == "__main__":
    raise SystemExit(main())
