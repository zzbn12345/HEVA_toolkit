"""Acceptance tests for HEVA document provenance, citation, and rights."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from heva.workflow.document_metadata import (
    AnnotationProcessMetadata,
    AnnotatorMetadata,
    ColorConfigurationMetadata,
    ColorMappingMetadata,
    MetadataError,
    OriginalAnnotatorMetadata,
    PackageMetadata,
    ResourceMetadata,
    ReviewMetadata,
    RightsMetadata,
    SourceMetadata,
    load_annotator,
    save_package_metadata,
    validate_review_readiness,
)
from heva.workflow.project_registry import sync_registry


def complete_metadata(document_id: str = "HEVA-EXAMPLE") -> PackageMetadata:
    return PackageMetadata(
        document_id=document_id,
        source=SourceMetadata(
            title="Galle heritage report",
            creators=["Example Author"],
            citation="Example Author (2011), Galle heritage report.",
            reference="https://example.org/galle-report",
            human_confirmed=True,
            confirmed_by="Research Annotator",
            confirmed_at="2026-07-23T14:00:00Z",
        ),
        annotator=AnnotatorMetadata(
            name="Research Annotator",
            orcid="0000-0002-1825-0097",
        ),
        original_annotators=[
            OriginalAnnotatorMetadata(
                person_id="PERSON-ANNOTATOR01",
                name="Research Annotator",
                orcid="0000-0002-1825-0097",
            )
        ],
        rights=RightsMetadata(
            access_level="restricted",
            authorization_status="authorized",
            authorization_date="2026-07-23",
            authorized_by="Rights holder",
            evidence_reference="rights/galle-authorization",
            source_distribution_allowed=False,
            extracted_text_distribution_allowed=True,
            annotation_distribution_allowed=True,
            license="CC-BY-4.0",
        ),
        annotation_process=AnnotationProcessMetadata(
            method="automatic",
            extractor="HEVA PDF extractor",
            extractor_version="0.1.0",
            performed_at="2026-07-23T14:30:00Z",
            review=ReviewMetadata(
                all_sentences_require_approval=True,
                completed=True,
                reviewed_at="2026-07-23T15:30:00Z",
            ),
        ),
        color_configuration=ColorConfigurationMetadata(
            detection_method="automatic",
            document_consistency="consistent",
            human_confirmed=True,
            confirmed_by="Research Annotator",
            confirmed_at="2026-07-23T14:45:00Z",
            colors=[
                ColorMappingMetadata(
                    hex="#ffff00",
                    color_name="Yellow",
                    text_color="#000000",
                    suggested_label="historic",
                    label="historic",
                    display_name="Historical value",
                    method="document_legend",
                    confidence=1.0,
                    status="approved",
                )
            ],
        ),
        resources=[
            ResourceMetadata(
                name="annotations",
                path="annotations.json",
                format="json",
                record_count=128,
            )
        ],
    )


def test_complete_metadata_is_review_ready_and_separates_creators_from_annotator() -> None:
    metadata = complete_metadata()

    report = validate_review_readiness(metadata)

    assert report.ready
    assert report.issues == ()
    assert metadata.source.creators == ["Example Author"]
    assert metadata.annotator.name == "Research Annotator"
    assert metadata.original_annotators[0].person_id == "PERSON-ANNOTATOR01"
    assert metadata.color_configuration.colors[0].hex == "#FFFF00"
    assert metadata.resources[0].path == "annotations.json"


def test_explained_non_findable_source_is_ready_with_visible_warning() -> None:
    metadata = complete_metadata()
    metadata.source.reference = None
    metadata.source.not_findable_reason = "Internal student work without a public DOI or URL."

    report = validate_review_readiness(metadata)

    assert report.ready
    assert [(issue.code, issue.severity) for issue in report.issues] == [
        ("source_not_findable", "warning")
    ]


def test_missing_provenance_and_unexplained_findability_block_review() -> None:
    metadata = complete_metadata()
    metadata.source.creators = []
    metadata.source.citation = None
    metadata.source.reference = None
    metadata.source.not_findable_reason = None

    report = validate_review_readiness(metadata)
    codes = {issue.code for issue in report.blocking_issues}

    assert not report.ready
    assert codes == {"missing_source_creator", "missing_citation", "missing_findability"}


def test_optional_document_rights_do_not_block_annotation_package() -> None:
    metadata = complete_metadata()
    metadata.rights = RightsMetadata()

    report = validate_review_readiness(metadata)

    assert report.ready


def test_color_detection_method_is_optional_provenance() -> None:
    metadata = complete_metadata()
    metadata.color_configuration.detection_method = None

    report = validate_review_readiness(metadata)

    assert report.ready


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        (
            lambda metadata: setattr(metadata.annotation_process, "method", None),
            "missing_extraction_method",
        ),
        (
            lambda metadata: setattr(metadata.annotation_process.review, "completed", False),
            "annotation_review_incomplete",
        ),
        (
            lambda metadata: setattr(metadata.color_configuration, "human_confirmed", False),
            "color_mapping_unconfirmed",
        ),
        (
            lambda metadata: setattr(metadata.color_configuration, "colors", []),
            "missing_color_mapping",
        ),
        (
            lambda metadata: setattr(metadata, "resources", []),
            "missing_annotations_resource",
        ),
    ],
)
def test_incomplete_annotation_process_blocks_review(mutation, expected_code: str) -> None:
    metadata = complete_metadata()
    mutation(metadata)

    report = validate_review_readiness(metadata)

    assert not report.ready
    assert expected_code in {issue.code for issue in report.blocking_issues}


def test_color_mapping_rejects_unknown_labels_and_invalid_hex() -> None:
    with pytest.raises(ValueError, match="controlled HEVA label"):
        ColorMappingMetadata(hex="#FFFF00", label="historical")

    with pytest.raises(ValueError, match="#RRGGBB"):
        ColorMappingMetadata(hex="yellow", label="historic")


def test_resource_path_cannot_escape_package() -> None:
    with pytest.raises(ValueError, match="inside the document package"):
        ResourceMetadata(
            name="annotations",
            path="../annotations.json",
            format="json",
            record_count=1,
        )


def test_metadata_is_saved_in_registered_package_and_linked_from_registry(
    tmp_path: Path,
) -> None:
    documents = tmp_path / "documents"
    documents.mkdir()
    (documents / "source.pdf").write_bytes(b"source")
    sync_registry(tmp_path, source_dir="documents")
    registry_path = tmp_path / ".heva" / "project.json"
    registry = json.loads(registry_path.read_text())
    document_id = registry["documents"][0]["document_id"]

    metadata_path = save_package_metadata(tmp_path, complete_metadata(document_id))
    updated = json.loads(registry_path.read_text())

    assert metadata_path == tmp_path / "documents" / document_id / "metadata.json"
    assert metadata_path.is_file()
    saved = json.loads(metadata_path.read_text())
    assert saved["annotation_process"]["extractor"] == "HEVA PDF extractor"
    saved_color = saved["color_configuration"]["colors"][0]
    assert saved_color["hex"] == "#FFFF00"
    assert saved_color["label"] == "historic"
    assert saved_color["status"] == "approved"
    assert saved_color["text_color"] == "#000000"
    assert saved["resources"] == [
        {
            "name": "annotations",
            "path": "annotations.json",
            "format": "json",
            "record_count": 128,
        }
    ]
    assert updated["documents"][0]["metadata_path"] == (
        f"documents/{document_id}/metadata.json"
    )


def test_metadata_cannot_be_saved_for_unregistered_document(tmp_path: Path) -> None:
    (tmp_path / ".heva").mkdir()
    (tmp_path / ".heva" / "project.json").write_text(
        json.dumps(
            {
                "registry_version": "1.0",
                "source_directory": "documents",
                "documents": [],
                "summary": {
                    "total": 0,
                    "backlog": 0,
                    "in_progress": 0,
                    "in_review": 0,
                    "done": 0,
                    "changed": 0,
                    "missing": 0,
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(MetadataError, match="not registered"):
        save_package_metadata(tmp_path, complete_metadata("HEVA-UNKNOWN"))


def test_annotator_can_be_loaded_from_json(tmp_path: Path) -> None:
    json_path = tmp_path / "annotator.json"
    json_path.write_text(
        json.dumps({"name": "JSON Annotator", "orcid": "0000-0002-1825-0097"}),
        encoding="utf-8",
    )

    assert load_annotator(json_path).name == "JSON Annotator"


def test_annotator_rejects_non_json_formats(tmp_path: Path) -> None:
    text_path = tmp_path / "annotator.txt"
    text_path.write_text("name: Text Annotator\n", encoding="utf-8")

    with pytest.raises(MetadataError, match="must use .json"):
        load_annotator(text_path)
