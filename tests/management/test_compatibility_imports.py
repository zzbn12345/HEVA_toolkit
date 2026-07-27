"""Temporary compatibility imports remain available during package migration."""

from management.heva_management.contract import validate_record as canonical_validate
from management.heva_management.project_registry import sync_registry as canonical_sync
from src.heva_contract import validate_record as legacy_validate
from src.project_registry import sync_registry as legacy_sync


def test_src_imports_forward_to_canonical_implementations() -> None:
    assert legacy_validate is canonical_validate
    assert legacy_sync is canonical_sync
