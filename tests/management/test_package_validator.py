"""Acceptance tests for layered package validation and approved export."""

from __future__ import annotations

import csv
import json
from pathlib import Path
import subprocess
import sys

import pytest

from management.heva_management.document_metadata import (
    AnnotationProcessMetadata,
    AnnotatorMetadata,
    ColorConfigurationMetadata,
    ColorMappingMetadata,
    PackageMetadata,
    ResourceMetadata,
    ReviewMetadata,
    RightsMetadata,
    SourceMetadata,
)
from management.heva_management.package_validator import (
    PackageValidationError,
    approve_document,
    build_release,
    validate_document_package,
)
from management.heva_management.project_registry import sync_registry
from management.heva_management.review_state import (
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
        ),
        annotator=AnnotatorMetadata(name="Annotator"),
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
    registry_path = tmp_path / "data/project-registry.json"
    registry = json.loads(registry_path.read_text())
    entry = registry["documents"][0]
    document_id = entry["document_id"]
    package = tmp_path / entry["package_path"]
    (package / "annotations.json").write_text(json.dumps([record()]), encoding="utf-8")
    (package / "package-metadata.json").write_text(
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
    return document_id, package, registry_path


def test_layered_report_has_actionable_stable_fields(tmp_path: Path) -> None:
    document_id, package, _ = project(tmp_path)
    metadata = json.loads((package / "package-metadata.json").read_text())
    metadata["rights"]["authorization_status"] = "pending"
    (package / "package-metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    report = validate_document_package(tmp_path, document_id)
    issue = next(item for item in report.issues if item.code == "source_not_authorized")

    assert not report.valid
    assert issue.severity == "error"
    assert issue.document_id == document_id
    assert issue.path == "$.package_metadata.rights.authorization_status"
    assert issue.action


def test_incomplete_review_blocks_approval(tmp_path: Path) -> None:
    document_id, package, _ = project(tmp_path)
    review = json.loads((package / "review-state.json").read_text())
    review["sentences"][0]["status"] = "pending"
    (package / "review-state.json").write_text(json.dumps(review), encoding="utf-8")

    with pytest.raises(PackageValidationError, match="sentence_review_incomplete"):
        approve_document(tmp_path, document_id)


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
            "management.heva_management.package_validator",
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
    assert '"code": "invalid_json"' in completed.stdout


def test_approved_release_is_deterministic_and_excludes_working_files(tmp_path: Path) -> None:
    document_id, _, registry_path = project(tmp_path)
    approve_document(tmp_path, document_id)

    first = build_release(tmp_path)
    first_files = {path.name: path.read_bytes() for path in first.iterdir()}
    second = build_release(tmp_path)
    second_files = {path.name: path.read_bytes() for path in second.iterdir()}

    assert first_files == second_files
    assert set(first_files) == {
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
    assert registry["documents"][0]["status"] == "done"


def test_release_rejects_documents_not_approved(tmp_path: Path) -> None:
    project(tmp_path)

    with pytest.raises(PackageValidationError, match="No approved documents"):
        build_release(tmp_path)
