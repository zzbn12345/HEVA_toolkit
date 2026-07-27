"""Compatibility entry point; use management.heva_management.quality_flags."""

from management.heva_management.quality_flags import *  # noqa: F403
from management.heva_management.quality_flags import main

if __name__ == "__main__":
    raise SystemExit(main())
