"""Acceptance tests for deterministic, non-mutating sentence quality flags."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from management.heva_management.project_registry import sync_registry
from management.heva_management.quality_flags import (
    QualityThresholds,
    assess_record,
    build_quality_report,
)


def record(sentence: str = "The historic harbour remains visible.") -> dict[str, object]:
    return {
        "sentence_id": 1,
        "page": 1,
        "sentence": sentence,
        "tokens": ["The", "historic", "harbour", "remains", "visible", "."],
        "values": ["historic"],
        "entities": [{
            "start": 4, "end": 20, "text": "historic harbour",
            "label": "historic", "color": "#FF40FF",
        }],
        "ner_tags": ["O", "B-historic", "I-historic", "O", "O", "O"],
        "schema_version": "1.0",
    }


def test_flags_are_deterministic_and_never_change_the_record() -> None:
    candidate = record("Bad\ufffd boundary")
    before = deepcopy(candidate)

    first = assess_record(candidate)
    second = assess_record(candidate)
    codes = {flag.code for flag in first}

    assert first == second
    assert candidate == before
    assert {"suspicious_character", "likely_sentence_boundary_error"} <= codes


def test_thresholds_are_configuration_data() -> None:
    candidate = record("A short sentence.")

    default_codes = {flag.code for flag in assess_record(candidate)}
    strict_codes = {
        flag.code
        for flag in assess_record(
            candidate,
            QualityThresholds(minimum_characters=100),
        )
    }

    assert "unusually_short_sentence" not in default_codes
    assert "unusually_short_sentence" in strict_codes


def test_contract_failures_and_pending_mapping_become_visible_flags() -> None:
    candidate = record()
    candidate["ner_tags"] = ["O"]
    candidate["mapping_provenance"] = {
        "method": "ollama",
        "status": "pending_review",
    }

    codes = {flag.code for flag in assess_record(candidate)}

    assert "token_tag_length_mismatch" in codes
    assert "unresolved_color_mapping" in codes


def test_package_report_preserves_every_sentence_for_human_review(tmp_path: Path) -> None:
    sources = tmp_path / "documents"
    sources.mkdir()
    (sources / "source.pdf").write_bytes(b"source")
    sync_registry(tmp_path, source_dir="documents")
    registry = json.loads((tmp_path / "data/project-registry.json").read_text())
    entry = registry["documents"][0]
    annotations = tmp_path / entry["package_path"] / "annotations.json"
    annotations.write_text(json.dumps([record(), record("Short")]), encoding="utf-8")

    report_path = build_quality_report(tmp_path, entry["document_id"])
    report = json.loads(report_path.read_text())

    assert report["record_count"] == 2
    assert len(report["findings"]) == 2
    assert report["findings"][0]["flags"] == []
    assert report["findings"][1]["flags"]
