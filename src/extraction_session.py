"""Compatibility entry point; use management.heva_management.extraction_session."""

from management.heva_management.extraction_session import *  # noqa: F403
from management.heva_management.extraction_session import main

if __name__ == "__main__":
    raise SystemExit(main())
