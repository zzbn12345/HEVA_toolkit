"""Acceptance tests for honest, separated HEVA evaluation metrics."""

from __future__ import annotations

import json
from pathlib import Path

from heva.workflow.evaluation import evaluate_manifest


def record(label: str = "historic") -> dict[str, object]:
    return {
        "sentence_id": 1,
        "page": 1,
        "sentence": "Historic harbour.",
        "tokens": ["Historic", "harbour", "."],
        "values": [label],
        "entities": [
            {
                "start": 0,
                "end": 16,
                "text": "Historic harbour",
                "label": label,
                "color": "#FF40FF",
            }
        ],
        "ner_tags": [f"B-{label}", f"I-{label}", "O"],
        "schema_version": "1.0",
    }


def write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def test_report_separates_records_spans_labels_and_human_effort(
    tmp_path: Path,
) -> None:
    write(tmp_path / "gold.json", [record()])
    write(
        tmp_path / "observed.json",
        {
            "records": [record()],
            "ollama_proposals": 4,
            "curator_corrections": 1,
            "ollama_abstentions": 1,
            "time_saved_seconds": 30.0,
            "duration_seconds": 0.5,
            "peak_memory_mb": 12.0,
        },
    )
    write(tmp_path / "unsupported.json", {"error_code": "unsupported_scan"})
    cases = [
        {
            "case_id": category,
            "category": category,
            "source_reference": f"approved-corpus/{category}",
            "expected_path": "gold.json",
            "observed_path": "observed.json",
        }
        for category in (
            "structured_annotations",
            "flattened_highlights",
            "colored_fonts",
            "mixed_conventions",
            "decorations",
        )
    ]
    cases.extend(
        {
            "case_id": category,
            "category": category,
            "source_reference": f"approved-corpus/{category}",
            "observed_path": "unsupported.json",
            "expected_support": False,
            "expected_error_code": "unsupported_scan",
        }
        for category in ("malformed_pdf", "unsupported_scan")
    )
    write(
        tmp_path / "manifest.json",
        {
            "approved_by": "Curator",
            "approved_at": "2026-07-29",
            "cases": cases,
        },
    )

    report = evaluate_manifest(tmp_path / "manifest.json")

    supported = report.cases[0]
    assert report.coverage_complete is True
    assert report.passed is True
    assert supported.record_precision.value == 1.0
    assert supported.span_recall.value == 1.0
    assert supported.label_accuracy.value == 1.0
    assert supported.correction_rate.value == 0.25
    assert supported.abstention_rate.value == 0.2
    assert supported.duration_seconds == 0.5
    assert supported.peak_memory_mb == 12.0


def test_missing_required_input_category_fails_overall_evidence(tmp_path: Path) -> None:
    write(tmp_path / "gold.json", [record()])
    write(tmp_path / "observed.json", {"records": [record()]})
    write(
        tmp_path / "manifest.json",
        {
            "approved_by": "Curator",
            "approved_at": "2026-07-29",
            "cases": [
                {
                    "case_id": "structured",
                    "category": "structured_annotations",
                    "source_reference": "approved-corpus/structured",
                    "expected_path": "gold.json",
                    "observed_path": "observed.json",
                }
            ],
        },
    )

    report = evaluate_manifest(tmp_path / "manifest.json")

    assert report.coverage_complete is False
    assert report.passed is False
    assert "unsupported_scan" in report.missing_categories
