"""Integrated alpha acceptance journey from source binding to distributable package."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from heva.app.main import create_app
from heva.curation.citation_import import import_citation_row
from heva.curation.color_configuration_registry import (
    create_color_configuration_version,
    select_color_configuration,
)
from heva.curation.color_mapping import propose_color_configuration, save_color_configuration
from heva.curation.document_metadata import (
    PackageMetadata,
    save_package_metadata,
)
from heva.curation.document_contributors import assign_document_annotators
from heva.curation.extraction_draft import persist_extraction_draft, promote_extraction_draft
from heva.curation.package_validator import build_release, validate_project
from heva.curation.people_registry import PersonRecord, activate_curator, add_person
from heva.curation.project_registry import (
    load_project_registry,
    register_external_source,
    sync_registry,
)
from heva.curation.review_state import record_decisions


def test_researcher_sees_the_same_valid_and_exportable_state_everywhere(
    tmp_path: Path,
) -> None:
    """Keep persisted state, domain, GUI, CLI, and selected export gates equivalent."""

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
    assign_document_annotators(dataset, document_id, [annotator.person_id])
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
    metadata.annotation_process.review.completed = True
    metadata.annotation_process.review.reviewed_at = datetime(2026, 8, 11, 12, tzinfo=timezone.utc)
    save_package_metadata(dataset, metadata)
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
    web_report = TestClient(create_app(dataset)).post("/api/validate")
    command = subprocess.run(
        [
            sys.executable,
            "-m",
            "heva.curation.package_validator",
            str(dataset),
            "validate",
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    web_release = TestClient(create_app(dataset)).post(
        "/api/release",
        json={"document_ids": [document_id]},
    )
    release = build_release(dataset, document_ids=[document_id])
    payload = json.loads((release / "heva-annotations.json").read_text())

    target_report = next(item for item in report.documents if item.document_id == document_id)
    cli_report = json.loads(command.stdout)
    assert web_report.status_code == 200
    assert command.returncode == 0, command.stdout + command.stderr
    assert web_release.status_code == 200
    assert target_report.model_dump(mode="json") == web_report.json()["documents"][0]
    assert target_report.model_dump(mode="json") == cli_report["documents"][0]
    assert target_report.release_ready
    assert web_release.json()["membership"] == [document_id]
    assert payload["membership"] == [document_id]
    assert "data_owner" not in payload["documents"][0]
    assert "curator" not in payload["documents"][0]
    assert "rights" not in payload["documents"][0]
    assert payload["documents"][0]["records"][0]["values"] == ["historic"]
    persisted = json.loads(registry_path.read_text())
    assert persisted["documents"][0]["status"] == "in_progress"
    assert str(external) not in (dataset / ".heva/project.json").read_text()
    assert not any(path.suffix == ".pdf" for path in release.iterdir())
