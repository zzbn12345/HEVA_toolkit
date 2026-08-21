"""Acceptance tests for layered package validation and approved export."""

from __future__ import annotations

import csv
import json
from pathlib import Path
import subprocess
import sys

import pytest

from heva.workflow.document_metadata import (
    AnnotationProcessMetadata,
    AnnotatorMetadata,
    ColorConfigurationMetadata,
    ColorMappingMetadata,
    PackageMetadata,
    OriginalAnnotatorMetadata,
    ResourceMetadata,
    ReviewMetadata,
    RightsMetadata,
    SourceMetadata,
)
from heva.workflow.package_validator import (
    PackageValidationError,
    build_release,
    format_validation_report,
    validate_document_package,
    validate_project,
)
from heva.workflow.project_registry import sync_registry
from heva.workflow.review_state import (
    initialize_sentence_reviews,
    record_decisions,
)


def record() -> dict[str, object]:
    return {
        "sentence_id": 1,
        "page": 2,
        "sentence": "The historic harbour remains.",
        "tokens": ["The", "historic", "harbour", "remains", "."],
        "values": ["historic"],
        "entities": [
            {
                "start": 4,
                "end": 20,
                "text": "historic harbour",
                "label": "historic",
                "color": "#FFFF00",
            }
        ],
        "ner_tags": ["O", "B-historic", "I-historic", "O", "O"],
        "schema_version": "1.0",
    }


def ready_metadata(document_id: str) -> PackageMetadata:
    return PackageMetadata(
        document_id=document_id,
        source=SourceMetadata(
            title="Harbour report",
            creators=["Author"],
            citation="Author (2025), Harbour report.",
            reference="https://example.org/report",
            human_confirmed=True,
            confirmed_by="Annotator",
            confirmed_at="2026-07-24T08:30:00Z",
        ),
        annotator=AnnotatorMetadata(name="Annotator"),
        original_annotators=[
            OriginalAnnotatorMetadata(
                person_id="PERSON-ANNOTATOR01",
                name="Annotator",
            )
        ],
        rights=RightsMetadata(
            access_level="restricted",
            authorization_status="authorized",
            authorization_date="2026-07-24",
            authorized_by="Rights holder",
            evidence_reference="rights/authorization",
            source_distribution_allowed=False,
            extracted_text_distribution_allowed=True,
            annotation_distribution_allowed=True,
            license="CC-BY-4.0",
        ),
        annotation_process=AnnotationProcessMetadata(
            method="automatic",
            extractor="HEVA",
            extractor_version="0.1.0",
            performed_at="2026-07-24T09:00:00Z",
            review=ReviewMetadata(
                completed=True,
                reviewed_at="2026-07-24T10:00:00Z",
            ),
        ),
        color_configuration=ColorConfigurationMetadata(
            detection_method="automatic",
            human_confirmed=True,
            confirmed_by="Annotator",
            confirmed_at="2026-07-24T09:15:00Z",
            colors=[
                ColorMappingMetadata(
                    hex="#FFFF00",
                    label="historic",
                    status="approved",
                )
            ],
        ),
        resources=[
            ResourceMetadata(
                name="annotations",
                path="annotations.json",
                format="json",
                record_count=1,
            )
        ],
    )


def project(tmp_path: Path) -> tuple[str, Path, Path]:
    sources = tmp_path / "documents"
    sources.mkdir()
    (sources / "source.pdf").write_bytes(b"authorized source")
    sync_registry(tmp_path, source_dir="documents")
    registry_path = tmp_path / ".heva/project.json"
    registry = json.loads(registry_path.read_text())
    entry = registry["documents"][0]
    document_id = entry["document_id"]
    package = tmp_path / entry["package_path"]
    (package / "annotations.json").write_text(json.dumps([record()]), encoding="utf-8")
    (package / "metadata.json").write_text(
        ready_metadata(document_id).model_dump_json(indent=2),
        encoding="utf-8",
    )
    initialize_sentence_reviews(tmp_path, document_id)
    record_decisions(
        tmp_path,
        document_id,
        [1],
        status="approved",
        reviewer="Annotator",
    )
    registry["documents"][0]["status"] = "in_review"
    registry["summary"]["backlog"] = 0
    registry["summary"]["in_review"] = 1
    registry_path.write_text(json.dumps(registry), encoding="utf-8")
    (tmp_path / "dataset-metadata.json").write_text(
        json.dumps(
            {
                "name": "heva-harbour-annotations",
                "title": "HEVA harbour annotations",
                "description": "Curator-approved heritage-value annotations.",
                "creators": ["Research team"],
                "contributors": ["Annotator"],
                "license": "CC-BY-4.0",
                "rights": "Annotations may be shared; source documents remain restricted.",
                "known_limitations": [
                    "The candidate does not claim OCR support or complete heritage coverage."
                ],
            }
        ),
        encoding="utf-8",
    )
    return document_id, package, registry_path


def test_layered_report_has_actionable_stable_fields(tmp_path: Path) -> None:
    document_id, package, _ = project(tmp_path)
    metadata = json.loads((package / "metadata.json").read_text())
    metadata["rights"]["authorization_status"] = "pending"
    (package / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    report = validate_document_package(tmp_path, document_id)
    issue = next(item for item in report.issues if item.code == "source_not_authorized")

    assert not report.valid
    assert issue.severity == "error"
    assert issue.document_id == document_id
    assert issue.path == "$.package_metadata.rights.authorization_status"
    assert issue.action
    assert issue.guide == "DATA_PACKAGE"
    assert "Guide: docs/DATA_PACKAGE.md" in format_validation_report(
        validate_project(tmp_path)
    )
    assert report.source_path == "documents/source.pdf"
    assert report.workflow_status == "in_review"
    assert report.completed is False


def test_project_report_uses_validation_as_alpha_completion(
    tmp_path: Path,
) -> None:
    document_id, _, _ = project(tmp_path)

    report = validate_project(tmp_path)
    rendered = format_validation_report(report)

    assert report.valid is True
    assert report.summary.passed == 1
    assert report.summary.completed == 1
    assert report.summary.not_completed == 0
    assert f"PASS documents/source.pdf ({document_id}, completed, in_review)" in rendered
    assert "1 passed, 0 failed" in rendered


def test_incomplete_review_blocks_export(tmp_path: Path) -> None:
    document_id, package, _ = project(tmp_path)
    review = json.loads((tmp_path / ".heva/documents" / document_id / "review-state.json").read_text())
    review["sentences"][0]["status"] = "pending"
    (tmp_path / ".heva/documents" / document_id / "review-state.json").write_text(json.dumps(review), encoding="utf-8")

    with pytest.raises(PackageValidationError, match="sentence_review_incomplete"):
        build_release(tmp_path)


def test_changed_sentence_invalidates_its_existing_review(tmp_path: Path) -> None:
    document_id, package, _ = project(tmp_path)
    annotations = json.loads((package / "annotations.json").read_text())
    annotations[0]["page"] = 3
    (package / "annotations.json").write_text(json.dumps(annotations), encoding="utf-8")

    report = validate_document_package(tmp_path, document_id)

    assert "stale_sentence_review" in {item.code for item in report.issues}
    assert not report.valid


def test_invalid_package_returns_failing_cli_status(tmp_path: Path) -> None:
    document_id, package, _ = project(tmp_path)
    (package / "annotations.json").write_text("{broken", encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "heva.workflow.package_validator",
            str(tmp_path),
            "validate",
            "--document-id",
            document_id,
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 1
    assert '"code": "invalid_json"' in completed.stdout


def test_cli_human_report_has_test_runner_summary_and_action(tmp_path: Path) -> None:
    document_id, package, _ = project(tmp_path)
    (package / "annotations.json").write_text("{broken", encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "heva.workflow.package_validator",
            str(tmp_path),
            "validate",
            "--document-id",
            document_id,
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 1
    assert "FAIL documents/source.pdf" in completed.stdout
    assert "ERROR invalid_json $.annotations" in completed.stdout
    assert "Fix:" in completed.stdout
    assert "0 passed, 1 failed" in completed.stdout


def test_validated_release_is_deterministic_and_excludes_working_files(tmp_path: Path) -> None:
    document_id, _, registry_path = project(tmp_path)

    first = build_release(tmp_path)
    first_files = {path.name: path.read_bytes() for path in first.iterdir()}
    second = build_release(tmp_path)
    second_files = {path.name: path.read_bytes() for path in second.iterdir()}

    assert first_files == second_files
    assert set(first_files) == {
        "build-log.json",
        "datapackage.json",
        "heva-annotations.csv",
        "heva-annotations.json",
    }
    assert b"review-state" not in first_files["heva-annotations.json"]
    assert b".pdf" not in first_files["heva-annotations.json"]
    with (second / "heva-annotations.csv").open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    assert rows[0]["document_id"] == document_id
    assert rows[0]["sentence_id"] == "1"
    registry = json.loads(registry_path.read_text())
    assert registry["documents"][0]["status"] == "in_review"
    payload = json.loads(first_files["heva-annotations.json"])
    assert payload["membership"] == [document_id]
    assert payload["documents"][0]["citation"]
    assert payload["documents"][0]["rights"]["source_distribution_allowed"] is False
    assert "data_owner" not in payload["documents"][0]
    assert "curator" not in payload["documents"][0]
    assert len(payload["documents"][0]["annotations_checksum_sha256"]) == 64
    descriptor = json.loads(first_files["datapackage.json"])
    assert all(resource["hash"].startswith("sha256:") for resource in descriptor["resources"])


def test_legacy_done_status_does_not_require_curator_acceptance(
    tmp_path: Path,
) -> None:
    document_id, _, registry_path = project(tmp_path)
    registry = json.loads(registry_path.read_text())
    registry["documents"][0]["status"] = "done"
    registry["summary"]["in_review"] = 0
    registry["summary"]["done"] = 1
    registry_path.write_text(json.dumps(registry), encoding="utf-8")

    assert build_release(tmp_path).is_dir()


def test_release_accepts_valid_document_without_submission(tmp_path: Path) -> None:
    project(tmp_path)

    assert build_release(tmp_path).is_dir()
