"""Compatibility entry point; use management.heva_management.release_builder."""

from management.heva_management.release_builder import *  # noqa: F403
from management.heva_management.release_builder import main

if __name__ == "__main__":
    raise SystemExit(main())
