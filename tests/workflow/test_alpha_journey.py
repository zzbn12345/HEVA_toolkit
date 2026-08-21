"""Integrated alpha acceptance journey from source binding to distributable package."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from heva.workflow.citation_import import import_citation_row
from heva.workflow.color_configuration_registry import (
    create_color_configuration_version,
    select_color_configuration,
)
from heva.workflow.color_mapping import propose_color_configuration, save_color_configuration
from heva.workflow.document_metadata import (
    AnnotatorMetadata,
    PackageMetadata,
    RightsMetadata,
    save_package_metadata,
)
from heva.workflow.extraction_draft import persist_extraction_draft, promote_extraction_draft
from heva.workflow.package_validator import build_release, validate_project
from heva.workflow.people_registry import PersonRecord, activate_curator, add_person
from heva.workflow.project_registry import (
    load_project_registry,
    register_external_source,
    sync_registry,
)
from heva.workflow.review_state import record_decisions


def test_researcher_can_build_release_without_ollama_or_committed_pdf(tmp_path: Path) -> None:
    """Exercise validation and export without internal submission or approval gates."""

    dataset = tmp_path / "curated-dataset"
    dataset.mkdir()
    (dataset / "placeholder.pdf").write_bytes(b"seed")
    sync_registry(dataset, source_dir=".")
    external = tmp_path / "authorized-sources/report.pdf"
    external.parent.mkdir()
    external.write_bytes(b"authorized source remains outside the dataset")
    document_id = register_external_source(dataset, external)
    registry_path = dataset / ".heva/project.json"
    registry = json.loads(registry_path.read_text())
    registry["documents"] = [
        item for item in registry["documents"] if item["document_id"] == document_id
    ]
    registry["summary"].update({"total": 1, "backlog": 1, "in_progress": 0, "in_review": 0, "done": 0})
    registry_path.write_text(json.dumps(registry), encoding="utf-8")

    annotator = add_person(dataset, PersonRecord(name="Original Annotator", roles=["annotator"]))
    curator = add_person(dataset, PersonRecord(name="Alpha Curator", roles=["curator"]))
    owner = add_person(
        dataset,
        PersonRecord(name="Responsible Data Owner", roles=["data_owner"], affiliation="Archive"),
    )
    activate_curator(dataset, curator.person_id)
    import_citation_row(
        dataset,
        {
            "source_filename": "report.pdf",
            "title": "Authorized heritage report",
            "creators": ["Source Author"],
            "item_type": "report",
            "issued_year": 2025,
            "citation": "Source Author. Authorized heritage report. 2025.",
            "reference": "https://example.org/report",
        },
        validated_by="alpha-fixture/1.0",
    )

    sentence = "The historic harbour remains."
    persist_extraction_draft(
        dataset,
        document_id,
        [{
            "sentence_id": 1,
            "page": 1,
            "sentence": sentence,
            "tokens": ["The", "historic", "harbour", "remains", "."],
            "values": ["#FFFF00"],
            "entities": [{"start": 4, "end": 20, "text": "historic harbour", "label": "#FFFF00"}],
            "ner_tags": ["O", "B-#FFFF00", "I-#FFFF00", "O", "O"],
        }],
        extractor="alpha deterministic fixture",
        extractor_version="1.0",
    )
    save_color_configuration(dataset, document_id, propose_color_configuration(["#FFFF00"]))
    palette = create_color_configuration_version(
        dataset,
        configuration_id="alpha-palette",
        name="Alpha palette",
        mappings=[{"label": "historic", "hexes": ["#FFFF00"]}],
    )
    select_color_configuration(dataset, palette.configuration_id, palette.version)
    promote_extraction_draft(dataset, document_id)
    record_decisions(dataset, document_id, [1], status="approved", reviewer=curator.name)

    entry = next(item for item in load_project_registry(dataset).documents if item.document_id == document_id)
    metadata = PackageMetadata.model_validate_json((dataset / entry.metadata_path).read_text())
    metadata.annotator = AnnotatorMetadata(name=annotator.name, affiliation=annotator.affiliation)
    metadata.rights = RightsMetadata(
        access_level="restricted",
        authorization_status="authorized",
        authorization_date="2026-08-11",
        authorized_by=owner.name,
        evidence_reference="owner-waiver-001",
        source_distribution_allowed=False,
        extracted_text_distribution_allowed=True,
        annotation_distribution_allowed=True,
        license="CC-BY-4.0",
    )
    metadata.annotation_process.review.completed = True
    metadata.annotation_process.review.reviewed_at = datetime(2026, 8, 11, 12, tzinfo=timezone.utc)
    save_package_metadata(dataset, metadata)
    registry = json.loads(registry_path.read_text())
    selected = next(item for item in registry["documents"] if item["document_id"] == document_id)
    selected["status"] = "in_review"
    registry["summary"].update({"backlog": 1, "in_review": 1, "done": 0})
    registry_path.write_text(json.dumps(registry), encoding="utf-8")
    (dataset / "dataset-metadata.json").write_text(
        json.dumps({
            "name": "heva-alpha",
            "title": "HEVA alpha dataset",
            "description": "Integrated alpha acceptance dataset.",
            "creators": [owner.name],
            "contributors": [annotator.name, curator.name],
            "license": "CC-BY-4.0",
            "rights": "Annotations may be distributed; source PDFs are excluded.",
            "known_limitations": ["Synthetic acceptance evidence is not an accuracy benchmark."],
        }),
        encoding="utf-8",
    )

    report = validate_project(dataset)
    release = build_release(dataset)
    payload = json.loads((release / "heva-annotations.json").read_text())

    target_report = next(item for item in report.documents if item.document_id == document_id)
    assert target_report.release_ready
    assert payload["membership"] == [document_id]
    assert "data_owner" not in payload["documents"][0]
    assert "curator" not in payload["documents"][0]
    assert "rights" not in payload["documents"][0]
    assert payload["documents"][0]["records"][0]["values"] == ["historic"]
    assert str(external) not in (dataset / ".heva/project.json").read_text()
    assert not any(path.suffix == ".pdf" for path in release.iterdir())
