"""Acceptance tests for collaborative unresolved extraction drafts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from heva.extraction.errors import ExtractionCancelled
from heva.workflow.color_configuration_registry import (
    create_color_configuration_version,
    select_color_configuration,
)
from heva.workflow.extraction_draft import (
    ExtractionDraftError,
    compile_extraction_draft,
    load_extraction_draft,
    persist_extraction_draft,
    promote_extraction_draft,
    run_registered_raw_extraction,
)
from heva.workflow.people_registry import PersonRecord, activate_curator, add_person
from heva.workflow.color_mapping import (
    load_color_configuration,
    propose_color_configuration,
    save_color_configuration,
)
from heva.workflow.project_registry import sync_registry


def _project(tmp_path: Path) -> tuple[str, list[dict[str, object]]]:
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "source.pdf").write_bytes(b"source")
    sync_registry(tmp_path, source_dir="sources")
    registry = json.loads((tmp_path / ".heva/project.json").read_text())
    curator = add_person(tmp_path, PersonRecord(name="Project Curator", roles=["curator"]))
    activate_curator(tmp_path, curator.person_id)
    records: list[dict[str, object]] = [
        {
            "sentence_id": 1,
            "page": 2,
            "sentence": "Old port and new market",
            "tokens": ["Old", "port", "and", "new", "market"],
            "values": ["#FFFF00", "#FFF200"],
            "entities": [
                {"start": 0, "end": 8, "text": "Old port", "label": "#FFFF00"},
                {"start": 13, "end": 23, "text": "new market", "label": "#FFF200"},
            ],
            "ner_tags": ["B-#FFFF00", "I-#FFFF00", "O", "B-#FFF200", "I-#FFF200"],
        }
    ]
    return registry["documents"][0]["document_id"], records


def test_raw_evidence_is_saved_outside_canonical_annotations(tmp_path: Path) -> None:
    """An unresolved run remains reusable without masquerading as training data."""

    document_id, records = _project(tmp_path)
    path = persist_extraction_draft(
        tmp_path,
        document_id,
        records,
        extractor="test extractor",
        extractor_version="1.0",
    )
    draft = load_extraction_draft(tmp_path, document_id)

    assert path == tmp_path / ".heva/documents" / document_id / "extraction-draft.json"
    assert not (tmp_path / "documents" / document_id / "annotations.json").exists()
    assert {entity.color for entity in draft.sentences[0].entities} == {"#FFFF00", "#FFF200"}
    assert all(entity.label is None for entity in draft.sentences[0].entities)
    assert all(entity.mapping_status == "unresolved" for entity in draft.sentences[0].entities)


def test_selected_version_compiles_all_raw_colors_to_canonical_labels(tmp_path: Path) -> None:
    """Several shades can resolve to one controlled label with exact provenance."""

    document_id, records = _project(tmp_path)
    persist_extraction_draft(
        tmp_path,
        document_id,
        records,
        extractor="test extractor",
        extractor_version="1.0",
    )
    configuration = create_color_configuration_version(
        tmp_path,
        configuration_id="heritage-palette",
        name="Heritage palette",
        mappings=[{"label": "historic", "hexes": ["#FFFF00", "#FFF200"]}],
    )
    select_color_configuration(tmp_path, configuration.configuration_id, configuration.version)

    compiled = compile_extraction_draft(tmp_path, document_id)

    assert compiled[0]["values"] == ["historic"]
    assert [entity["label"] for entity in compiled[0]["entities"]] == [
        "historic",
        "historic",
    ]
    assert compiled[0]["ner_tags"] == [
        "B-historic",
        "I-historic",
        "O",
        "B-historic",
        "I-historic",
    ]
    assert compiled[0]["mapping_provenance"]["config_id"] == "heritage-palette@1"


def test_unresolved_color_blocks_compilation(tmp_path: Path) -> None:
    """No raw shade silently disappears when a configuration is incomplete."""

    document_id, records = _project(tmp_path)
    persist_extraction_draft(
        tmp_path,
        document_id,
        records,
        extractor="test extractor",
        extractor_version="1.0",
    )
    configuration = create_color_configuration_version(
        tmp_path,
        configuration_id="partial",
        name="Partial palette",
        mappings=[{"label": "historic", "hexes": ["#FFFF00"]}],
    )
    select_color_configuration(tmp_path, configuration.configuration_id, configuration.version)

    with pytest.raises(ExtractionDraftError, match="#FFF200"):
        compile_extraction_draft(tmp_path, document_id)


def test_empty_rerun_preserves_previous_collaborative_draft(tmp_path: Path) -> None:
    """A failed extractor rerun cannot erase evidence another curator may need."""

    document_id, records = _project(tmp_path)
    path = persist_extraction_draft(
        tmp_path,
        document_id,
        records,
        extractor="test extractor",
        extractor_version="1.0",
    )
    before = path.read_bytes()

    with pytest.raises(ExtractionDraftError, match="previous extraction draft was preserved"):
        persist_extraction_draft(
            tmp_path,
            document_id,
            [],
            extractor="test extractor",
            extractor_version="1.1",
        )

    assert path.read_bytes() == before


def test_registered_raw_run_does_not_require_ollama_or_color_mapping(tmp_path: Path) -> None:
    """The alpha extractor can save raw evidence before any semantic setup exists."""

    document_id, records = _project(tmp_path)
    received: list[Path] = []

    def extractor(source: Path) -> list[dict[str, object]]:
        received.append(source)
        return records

    run_registered_raw_extraction(
        tmp_path,
        document_id,
        extractor=extractor,
        extractor_name="deterministic test extractor",
    )

    assert received == [tmp_path / "sources/source.pdf"]
    assert load_extraction_draft(tmp_path, document_id).extractor == "deterministic test extractor"


def test_registered_raw_run_shows_observed_colors_for_review(tmp_path: Path) -> None:
    """Extracted hex values immediately become visible pending color decisions."""

    document_id, records = _project(tmp_path)

    run_registered_raw_extraction(
        tmp_path,
        document_id,
        extractor=lambda _source: records,
        extractor_name="deterministic test extractor",
    )

    configuration = load_color_configuration(tmp_path, document_id)

    assert [color.hex for color in configuration.colors] == ["#FFF200", "#FFFF00"]
    assert all(color.status == "pending_review" for color in configuration.colors)
    assert all(color.text_color in {"#000000", "#FFFFFF"} for color in configuration.colors)
    assert configuration.human_confirmed is False
    assert configuration.use_for_extraction is False


def test_cancelled_raw_run_preserves_previous_draft(tmp_path: Path) -> None:
    """Cancellation before persistence cannot replace a valid collaborative checkpoint."""

    document_id, records = _project(tmp_path)
    path = persist_extraction_draft(
        tmp_path,
        document_id,
        records,
        extractor="first extractor",
        extractor_version="1.0",
    )
    before = path.read_bytes()

    with pytest.raises(ExtractionCancelled, match="before saving raw evidence"):
        run_registered_raw_extraction(
            tmp_path,
            document_id,
            extractor=lambda _source: records,
            extractor_name="cancelled extractor",
            cancellation_callback=lambda: True,
        )

    assert path.read_bytes() == before


def test_promotion_writes_canonical_annotations_only_after_selected_mapping(tmp_path: Path) -> None:
    """The draft-to-package transition reuses canonical session validation and provenance."""

    document_id, records = _project(tmp_path)
    persist_extraction_draft(
        tmp_path, document_id, records, extractor="test", extractor_version="1.0"
    )
    save_color_configuration(
        tmp_path,
        document_id,
        propose_color_configuration(["#FFFF00", "#FFF200"]),
    )
    configuration = create_color_configuration_version(
        tmp_path,
        configuration_id="approved-palette",
        name="Approved palette",
        mappings=[{"label": "historic", "hexes": ["#FFFF00", "#FFF200"]}],
    )
    select_color_configuration(tmp_path, configuration.configuration_id, 1)

    result = promote_extraction_draft(tmp_path, document_id)
    saved = json.loads(result.annotations_path.read_text())

    assert result.record_count == 1
    assert saved[0]["values"] == ["historic"]
    assert saved[0]["mapping_provenance"]["config_id"] == "approved-palette@1"
