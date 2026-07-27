"""Compatibility entry point; use management.heva_management.package_validator."""

from management.heva_management.package_validator import *  # noqa: F403
from management.heva_management.package_validator import main

if __name__ == "__main__":
    raise SystemExit(main())
