"""Acceptance tests for safe per-document rights persistence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from heva.workflow.document_citation import load_document_citation
from heva.workflow.document_metadata import RightsMetadata
from heva.workflow.document_rights import (
    DocumentRightsError,
    load_document_rights,
    save_document_rights,
)
from heva.workflow.project_registry import sync_registry


def initialized_document(tmp_path: Path) -> str:
    """Create one registered package with default metadata."""

    sources = tmp_path / "documents"
    sources.mkdir()
    (sources / "source.pdf").write_bytes(b"authorized source")
    sync_registry(tmp_path, source_dir="documents")
    registry = json.loads((tmp_path / ".heva/project.json").read_text(encoding="utf-8"))
    document_id = registry["documents"][0]["document_id"]
    load_document_citation(tmp_path, document_id)
    return document_id


def explicit_rights() -> RightsMetadata:
    """Return explicit and release-capable source/derivative decisions."""

    return RightsMetadata(
        access_level="restricted",
        authorization_status="authorized",
        authorization_date="2026-08-12",
        authorized_by="Rights holder",
        evidence_reference="agreements/source-authorization",
        source_distribution_allowed=False,
        extracted_text_distribution_allowed=True,
        annotation_distribution_allowed=True,
        license="CC-BY-4.0",
    )


def test_document_rights_round_trip_without_replacing_other_metadata(tmp_path: Path) -> None:
    document_id = initialized_document(tmp_path)

    saved = save_document_rights(tmp_path, document_id, explicit_rights())
    loaded = load_document_rights(tmp_path, document_id)

    assert loaded == saved
    registry = json.loads((tmp_path / ".heva/project.json").read_text(encoding="utf-8"))
    metadata_path = tmp_path / registry["documents"][0]["metadata_path"]
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["document_id"] == document_id
    assert metadata["rights"]["source_distribution_allowed"] is False


def test_document_rights_are_locked_after_submission(tmp_path: Path) -> None:
    document_id = initialized_document(tmp_path)
    registry_path = tmp_path / ".heva/project.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["documents"][0]["status"] = "in_review"
    registry_path.write_text(json.dumps(registry), encoding="utf-8")

    with pytest.raises(DocumentRightsError, match="locked after submission"):
        save_document_rights(tmp_path, document_id, explicit_rights())
