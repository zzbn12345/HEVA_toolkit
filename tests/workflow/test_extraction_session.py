"""Acceptance tests for persisting one registered document extraction."""

from __future__ import annotations

import json
from pathlib import Path

import fitz
import pytest

from heva.workflow.color_mapping import (
    confirm_color_configuration,
    propose_color_configuration,
    resolve_color,
    save_color_configuration,
)
from heva.workflow.extraction_session import (
    EmptyExtractionError,
    ExtractionSessionError,
    ExtractionValidationError,
    load_extraction_checkpoint_status,
    main,
    persist_extraction_results,
    run_registered_batch,
    run_registered_extraction,
)
from heva.workflow.project_registry import sync_registry


def record() -> dict[str, object]:
    return {
        "sentence_id": 1,
        "page": 1,
        "sentence": "The historic harbour remains visible.",
        "tokens": ["The", "historic", "harbour", "remains", "visible", "."],
        "values": ["historic"],
        "entities": [{
            "start": 4, "end": 20, "text": "historic harbour",
            "label": "historic", "color": "#FF40FF",
        }],
        "ner_tags": ["O", "B-historic", "I-historic", "O", "O", "O"],
        "schema_version": "1.0",
        "mapping_provenance": {
            "method": "human_reviewed", "status": "approved", "config_id": "test-map",
        },
    }


def project(tmp_path: Path) -> str:
    sources = tmp_path / "documents"
    sources.mkdir()
    (sources / "source.pdf").write_bytes(b"source")
    sync_registry(tmp_path, source_dir="documents")
    registry = json.loads((tmp_path / ".heva/project.json").read_text())
    document_id = registry["documents"][0]["document_id"]
    config = propose_color_configuration(
        ["#FF40FF"], legend_mapping={"#FF40FF": "historic"}
    )
    config = resolve_color(config, "#FF40FF", label="historic")
    config = confirm_color_configuration(config, confirmed_by="Annotator")
    save_color_configuration(tmp_path, document_id, config)
    return document_id


def test_valid_results_enter_registered_package_with_provenance(tmp_path: Path) -> None:
    document_id = project(tmp_path)

    result = persist_extraction_results(
        tmp_path, document_id, [record()],
        extraction_method="automatic", extractor="HEVA PDF extractor",
        extractor_version="0.1.0",
    )

    assert json.loads(result.annotations_path.read_text())[0]["entities"][0]["color"] == "#FF40FF"
    metadata = json.loads((result.annotations_path.parent / "metadata.json").read_text())
    assert metadata["resources"][0]["record_count"] == 1
    assert metadata["annotation_process"]["extractor_version"] == "0.1.0"
    registry = json.loads((tmp_path / ".heva/project.json").read_text())
    assert registry["documents"][0]["status"] == "in_progress"


def test_invalid_results_do_not_replace_existing_annotations(tmp_path: Path) -> None:
    document_id = project(tmp_path)
    package = tmp_path / "documents" / document_id
    annotations = package / "annotations.json"
    annotations.write_text('[{"preserved": true}]', encoding="utf-8")
    invalid = record()
    invalid["ner_tags"] = ["O"]

    with pytest.raises(ExtractionValidationError):
        persist_extraction_results(
            tmp_path, document_id, [invalid],
            extraction_method="automatic", extractor="test", extractor_version="1",
        )

    assert json.loads(annotations.read_text()) == [{"preserved": True}]


def test_registered_runner_reuses_matching_completed_checkpoint(tmp_path: Path) -> None:
    document_id = project(tmp_path)
    persisted = persist_extraction_results(
        tmp_path, document_id, [record()],
        extraction_method="automatic", extractor="test", extractor_version="1",
    )

    resumed = run_registered_extraction(tmp_path, document_id)

    assert resumed.reused_checkpoint
    assert resumed.annotations_path == persisted.annotations_path
    assert resumed.record_count == 1
    assert load_extraction_checkpoint_status(tmp_path, document_id).state == "current"


def test_mapping_change_marks_checkpoint_stale_without_deleting_records(
    tmp_path: Path,
) -> None:
    document_id = project(tmp_path)
    persisted = persist_extraction_results(
        tmp_path,
        document_id,
        [record()],
        extraction_method="automatic",
        extractor="test",
        extractor_version="1",
    )
    registry = json.loads((tmp_path / ".heva/project.json").read_text())
    metadata_path = tmp_path / registry["documents"][0]["metadata_path"]
    metadata = json.loads(metadata_path.read_text())
    metadata["color_configuration"]["colors"][0]["label"] = "political"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    status = load_extraction_checkpoint_status(tmp_path, document_id)

    assert status.state == "stale"
    assert "color mapping has changed" in status.stale_reasons[0]
    assert json.loads(persisted.annotations_path.read_text()) == [record()]


def test_changed_source_state_marks_checkpoint_stale(tmp_path: Path) -> None:
    document_id = project(tmp_path)
    persist_extraction_results(
        tmp_path,
        document_id,
        [record()],
        extraction_method="automatic",
        extractor="test",
        extractor_version="1",
    )
    registry_path = tmp_path / ".heva/project.json"
    registry = json.loads(registry_path.read_text())
    registry["documents"][0]["source_state"] = "changed"
    registry["documents"][0]["observed_checksum_sha256"] = "a" * 64
    registry_path.write_text(json.dumps(registry), encoding="utf-8")

    status = load_extraction_checkpoint_status(tmp_path, document_id)

    assert status.state == "stale"
    assert any("source state is changed" in reason for reason in status.stale_reasons)


def test_zero_record_extraction_is_a_corrective_failure_and_preserves_checkpoint(
    tmp_path: Path,
) -> None:
    document_id = project(tmp_path)
    package = tmp_path / "documents" / document_id
    annotations = package / "annotations.json"
    annotations.write_text('[{"preserved": true}]', encoding="utf-8")

    with pytest.raises(EmptyExtractionError, match="No annotation records"):
        persist_extraction_results(
            tmp_path,
            document_id,
            [],
            extraction_method="automatic",
            extractor="test",
            extractor_version="1",
        )

    assert json.loads(annotations.read_text()) == [{"preserved": True}]


def test_registered_runner_reports_scanned_pdf_without_claiming_ocr(
    tmp_path: Path,
) -> None:
    documents = tmp_path / "documents"
    documents.mkdir()
    source = documents / "scan.pdf"
    pdf = fitz.open()
    pdf.new_page()
    pdf.save(source)
    sync_registry(tmp_path, source_dir="documents")
    registry = json.loads((tmp_path / ".heva/project.json").read_text())
    document_id = registry["documents"][0]["document_id"]
    config = propose_color_configuration(
        ["#FF40FF"], legend_mapping={"#FF40FF": "historic"}
    )
    config = resolve_color(config, "#FF40FF", label="historic")
    config = confirm_color_configuration(config, confirmed_by="Annotator")
    save_color_configuration(tmp_path, document_id, config)

    with pytest.raises(ExtractionSessionError, match="does not currently provide OCR"):
        run_registered_extraction(tmp_path, document_id)


def test_registered_project_command_uses_shared_pdf_extractor(
    tmp_path: Path,
) -> None:
    """The project command persists optimized extraction into its document package."""
    documents = tmp_path / "documents"
    documents.mkdir()
    source = documents / "highlighted.pdf"
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((100, 100), "Historic harbour remains visible.", fontsize=12)
    highlighted = page.search_for("Historic harbour")[0]
    page.draw_rect(highlighted, fill=(1, 1, 0), color=None, overlay=False)
    pdf.save(source)
    pdf.close()
    sync_registry(tmp_path, source_dir="documents")
    registry = json.loads((tmp_path / ".heva/project.json").read_text())
    document_id = registry["documents"][0]["document_id"]
    config = propose_color_configuration(
        ["#FFFF00"], legend_mapping={"#FFFF00": "historic"}
    )
    config = resolve_color(config, "#FFFF00", label="historic")
    config = confirm_color_configuration(config, confirmed_by="Annotator")
    save_color_configuration(tmp_path, document_id, config)

    exit_code = main([
        str(tmp_path),
        "--document-id",
        document_id,
        "--force",
        "--json",
    ])

    assert exit_code == 0
    package = tmp_path / "documents" / document_id
    records = json.loads((package / "annotations.json").read_text(encoding="utf-8"))
    assert records[0]["entities"][0]["label"] == "historic"


def test_batch_runs_independent_packages_in_stable_order_and_isolates_failures(
    tmp_path: Path,
) -> None:
    documents = tmp_path / "documents"
    documents.mkdir()
    (documents / "b.pdf").write_bytes(b"b")
    (documents / "a.pdf").write_bytes(b"a")
    sync_registry(tmp_path, source_dir="documents")
    registry = json.loads((tmp_path / ".heva/project.json").read_text())
    ordered_ids = [item["document_id"] for item in registry["documents"]]
    calls: list[str] = []

    def fake_runner(root: Path, document_id: str, *, force: bool):
        calls.append(document_id)
        if document_id == ordered_ids[1]:
            raise ExtractionSessionError("Document-specific failure.")
        package = root / "documents" / document_id
        return type(
            "Result",
            (),
            {
                "reused_checkpoint": True,
                "record_count": 3,
                "annotations_path": package / "annotations.json",
                "session_path": tmp_path / ".heva/documents" / document_id / "extraction-session.json",
            },
        )()

    report = run_registered_batch(tmp_path, runner=fake_runner)

    assert calls == ordered_ids
    assert [item.status for item in report.documents] == ["reused", "failed"]
    assert report.documents[1].error == "Document-specific failure."
    assert not report.successful
