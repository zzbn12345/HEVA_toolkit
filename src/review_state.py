"""Compatibility entry point; use management.heva_management.review_state."""

from management.heva_management.review_state import *  # noqa: F403
from management.heva_management.review_state import main

if __name__ == "__main__":
    raise SystemExit(main())
