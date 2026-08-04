"""Tests for citation proposals and explicit human confirmation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from heva.workflow.document_citation import (
    CitationDraft,
    CitationError,
    confirm_document_citation,
    load_document_citation,
    save_document_citation,
)
from heva.workflow.project_registry import sync_registry


def registered_document(tmp_path: Path) -> str:
    sources = tmp_path / "documents"
    sources.mkdir()
    (sources / "Historic_Harbour.pdf").write_bytes(b"not-a-real-pdf")
    sync_registry(tmp_path, source_dir="documents")
    registry = json.loads((tmp_path / ".heva/project.json").read_text())
    return registry["documents"][0]["document_id"]


def test_filename_proposal_is_visible_but_not_confirmed(tmp_path: Path) -> None:
    document_id = registered_document(tmp_path)

    record = load_document_citation(tmp_path, document_id)

    assert record.data.title == "Historic Harbour"
    assert record.proposed_fields == ["title"]
    assert record.human_confirmed is False
    metadata = json.loads(
        next((tmp_path / "documents").glob("*/metadata.json")).read_text()
    )
    assert metadata["source"]["title"] is None


def test_saving_a_draft_does_not_pass_human_confirmation(tmp_path: Path) -> None:
    document_id = registered_document(tmp_path)

    saved = save_document_citation(
        tmp_path,
        document_id,
        CitationDraft(title="Harbour", creators=["Author"]),
    )

    assert saved.data.title == "Harbour"
    assert saved.human_confirmed is False


def test_confirmation_requires_citation_and_findability(tmp_path: Path) -> None:
    document_id = registered_document(tmp_path)

    with pytest.raises(CitationError, match="citation"):
        confirm_document_citation(
            tmp_path,
            document_id,
            CitationDraft(title="Harbour", creators=["Author"]),
            confirmed_by="Annotator",
        )


def test_complete_citation_records_actor_and_time(tmp_path: Path) -> None:
    document_id = registered_document(tmp_path)

    confirmed = confirm_document_citation(
        tmp_path,
        document_id,
        CitationDraft(
            title="Harbour",
            creators=["Author"],
            citation="Author. Harbour.",
            reference="https://example.org/harbour",
        ),
        confirmed_by="Annotator",
    )

    assert confirmed.human_confirmed is True
    assert confirmed.confirmed_by == "Annotator"
    assert confirmed.confirmed_at is not None
