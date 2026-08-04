"""Acceptance tests for supervised automatic color proposals."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from heva.workflow import automatic_color_proposal
from heva.workflow.automatic_color_proposal import (
    AutomaticColorProposalError,
    generate_automatic_color_proposals,
)
from heva.workflow.color_mapping import (
    confirm_color_configuration,
    load_color_configuration,
    propose_color_configuration,
    resolve_color,
    save_color_configuration,
)
from heva.workflow.project_registry import sync_registry


def _pending_document(tmp_path: Path) -> str:
    documents = tmp_path / "documents"
    documents.mkdir()
    (documents / "source.pdf").write_bytes(b"source")
    sync_registry(tmp_path, source_dir="documents")
    registry = json.loads((tmp_path / ".heva/project.json").read_text())
    document_id = registry["documents"][0]["document_id"]
    save_color_configuration(
        tmp_path,
        document_id,
        propose_color_configuration(["#CCCC00"]),
    )
    return document_id


def test_automatic_proposal_persists_pending_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document_id = _pending_document(tmp_path)
    monkeypatch.setattr(
        automatic_color_proposal,
        "_raw_records",
        lambda source: [
            {
                "sentence": "The city council adopted a new planning policy.",
                "entities": [{"text": "planning policy", "label": "#CCCC00"}],
            }
        ],
    )
    monkeypatch.setattr(
        automatic_color_proposal,
        "_query_ollama",
        lambda *args, **kwargs: {
            "mapping": {"#CCCC00": "political"},
            "reasoning": {"#CCCC00": "The text concerns planning policy."},
        },
    )

    proposed = generate_automatic_color_proposals(tmp_path, document_id)

    configuration = load_color_configuration(tmp_path, document_id)
    color = configuration.colors[0]
    assert proposed == 1
    assert not configuration.human_confirmed
    assert color.status == "pending_review"
    assert color.label is None
    assert color.suggested_label == "political"
    assert color.method == "ollama"
    assert color.reasoning == "The text concerns planning policy."


def test_automatic_proposal_rejects_uncontrolled_model_label(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document_id = _pending_document(tmp_path)
    monkeypatch.setattr(
        automatic_color_proposal,
        "_raw_records",
        lambda source: [
            {
                "sentence": "Highlighted evidence.",
                "entities": [{"text": "evidence", "label": "#CCCC00"}],
            }
        ],
    )
    monkeypatch.setattr(
        automatic_color_proposal,
        "_query_ollama",
        lambda *args, **kwargs: {
            "mapping": {"#CCCC00": "made-up-label"},
            "reasoning": {"#CCCC00": "Unsupported inference."},
        },
    )

    with pytest.raises(AutomaticColorProposalError, match="controlled HEVA"):
        generate_automatic_color_proposals(tmp_path, document_id)

    assert (
        load_color_configuration(tmp_path, document_id)
        .colors[0]
        .suggested_label
        is None
    )


def test_automatic_proposal_never_replaces_confirmed_decisions(
    tmp_path: Path,
) -> None:
    document_id = _pending_document(tmp_path)
    configuration = load_color_configuration(tmp_path, document_id)
    configuration = resolve_color(configuration, "#CCCC00", label="political")
    configuration = confirm_color_configuration(
        configuration,
        confirmed_by="Research Annotator",
    )
    save_color_configuration(tmp_path, document_id, configuration)

    with pytest.raises(AutomaticColorProposalError, match="already confirmed"):
        generate_automatic_color_proposals(tmp_path, document_id)
