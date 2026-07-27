"""Compatibility entry point; use management.heva_management.validate_records."""

from management.heva_management.validate_records import *  # noqa: F403
from management.heva_management.validate_records import main

if __name__ == "__main__":
    raise SystemExit(main())
