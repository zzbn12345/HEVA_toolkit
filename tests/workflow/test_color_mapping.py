"""Acceptance tests for the document-local supervised color mapping gate."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from heva.workflow.color_mapping import (
    apply_shared_color_mapping,
    ColorMappingError,
    authorize_pending_mapping_for_extraction,
    confirm_color_configuration,
    load_color_configuration,
    load_confirmed_color_mapping,
    load_extraction_color_mapping,
    observed_colors_from_records,
    propose_color_configuration,
    resolve_color,
    review_and_confirm_color_configuration,
    save_color_configuration,
    validate_shared_batch_mapping,
    write_automatic_color_proposals,
)
from heva.workflow.project_registry import sync_registry


def test_raw_extractor_records_supply_document_colors() -> None:
    records = [
        {
            "entities": [
                {"text": "one", "label": "#ffff00"},
                {"text": "two", "label": "historic", "color": "#FF00FF"},
            ]
        },
        {"entities": [{"text": "repeat", "label": "#FFFF00"}]},
    ]

    assert observed_colors_from_records(records) == ("#FF00FF", "#FFFF00")


def test_ollama_suggestions_remain_pending_and_include_display_evidence() -> None:
    configuration = propose_color_configuration(
        ["#FFFF00"],
        ollama_suggestions={"#FFFF00": "historic"},
        ollama_confidence={"#FFFF00": 0.72},
    )

    color = configuration.colors[0]
    assert configuration.detection_method == "automatic"
    assert not configuration.human_confirmed
    assert color.status == "pending_review"
    assert color.method == "ollama"
    assert color.suggested_label == "historic"
    assert color.label is None
    assert color.color_name == "Yellow"
    assert color.text_color == "#000000"
    assert color.confidence == 0.72


def test_document_legend_is_preferred_over_ollama_and_generic_conventions() -> None:
    configuration = propose_color_configuration(
        ["#FF00FF"],
        legend_mapping={"#FF00FF": "economic"},
        ollama_suggestions={"#FF00FF": "historic"},
        generic_suggestions={"#FF00FF": "social"},
    )

    color = configuration.colors[0]
    assert configuration.detection_method == "document_legend"
    assert color.method == "document_legend"
    assert color.suggested_label == "economic"


def test_human_can_approve_or_ignore_each_color_with_provenance() -> None:
    configuration = propose_color_configuration(
        ["#FFFF00", "#000080"],
        generic_suggestions={"#FFFF00": "historic"},
    )

    configuration = resolve_color(configuration, "#FFFF00", label="historic")
    configuration = resolve_color(
        configuration,
        "#000080",
        ignore_reason="Decorative page header, not a heritage annotation.",
    )
    confirmed = confirm_color_configuration(
        configuration,
        confirmed_by="Research Annotator",
        confirmed_at=datetime(2026, 7, 23, 12, 0, tzinfo=timezone.utc),
    )

    assert confirmed.human_confirmed
    assert [color.status for color in confirmed.colors] == ["ignored", "approved"]
    assert confirmed.colors[0].ignore_reason
    assert confirmed.colors[1].label == "historic"


def test_confirmation_rejects_pending_or_unexplained_ignored_colors() -> None:
    configuration = propose_color_configuration(["#FFFF00"])
    with pytest.raises(ColorMappingError, match="pending"):
        confirm_color_configuration(configuration, confirmed_by="Annotator")

    configuration.colors[0].status = "ignored"
    with pytest.raises(ColorMappingError, match="ignore reason"):
        confirm_color_configuration(configuration, confirmed_by="Annotator")


def test_confirmation_repairs_missing_detection_provenance() -> None:
    """Older mappings gain an explicit conservative method when reconfirmed."""

    configuration = propose_color_configuration(["#FFFF00"])
    configuration.detection_method = None
    configuration = resolve_color(configuration, "#FFFF00", label="political")

    confirmed = confirm_color_configuration(configuration, confirmed_by="Annotator")

    assert confirmed.detection_method == "manual"


def test_batch_shared_mapping_requires_same_palette_and_each_document_confirmation() -> None:
    first = propose_color_configuration(
        ["#FFFF00"], legend_mapping={"#FFFF00": "historic"}
    )
    first = resolve_color(first, "#FFFF00", label="historic")
    first = confirm_color_configuration(first, confirmed_by="Annotator")

    different = propose_color_configuration(
        ["#FF00FF"], legend_mapping={"#FF00FF": "economic"}
    )
    report = validate_shared_batch_mapping({"DOC-1": first, "DOC-2": different})
    assert not report.allowed
    assert "batch_palette_mismatch" in {issue.code for issue in report.issues}

    unconfirmed = propose_color_configuration(
        ["#FFFF00"], legend_mapping={"#FFFF00": "historic"}
    )
    report = validate_shared_batch_mapping({"DOC-1": first, "DOC-2": unconfirmed})
    assert not report.allowed
    assert "shared_mapping_unconfirmed" in {issue.code for issue in report.issues}

    second = resolve_color(unconfirmed, "#FFFF00", label="historic")
    second = confirm_color_configuration(second, confirmed_by="Second Annotator")
    assert validate_shared_batch_mapping({"DOC-1": first, "DOC-2": second}).allowed


def test_confirmed_configuration_is_saved_in_document_package(tmp_path: Path) -> None:
    documents = tmp_path / "documents"
    documents.mkdir()
    (documents / "source.pdf").write_bytes(b"source")
    sync_registry(tmp_path, source_dir="documents")
    registry = json.loads((tmp_path / ".heva" / "project.json").read_text())
    document_id = registry["documents"][0]["document_id"]
    configuration = propose_color_configuration(
        ["#FFFF00"], legend_mapping={"#FFFF00": "historic"}
    )
    configuration = resolve_color(configuration, "#FFFF00", label="historic")
    configuration = confirm_color_configuration(configuration, confirmed_by="Annotator")

    metadata_path = save_color_configuration(tmp_path, document_id, configuration)
    saved = json.loads(metadata_path.read_text())

    assert metadata_path.parent.name == document_id
    assert saved["color_configuration"]["human_confirmed"]
    assert saved["color_configuration"]["colors"][0]["label"] == "historic"
    assert load_confirmed_color_mapping(tmp_path, document_id) == {
        "#FFFF00": "historic"
    }


def test_unconfirmed_package_mapping_cannot_drive_semantic_extraction(
    tmp_path: Path,
) -> None:
    documents = tmp_path / "documents"
    documents.mkdir()
    (documents / "source.pdf").write_bytes(b"source")
    sync_registry(tmp_path, source_dir="documents")
    registry = json.loads((tmp_path / ".heva" / "project.json").read_text())
    document_id = registry["documents"][0]["document_id"]
    proposal = propose_color_configuration(
        ["#FFFF00"], ollama_suggestions={"#FFFF00": "historic"}
    )
    save_color_configuration(tmp_path, document_id, proposal)

    with pytest.raises(ColorMappingError, match="not been confirmed"):
        load_confirmed_color_mapping(tmp_path, document_id)


def test_automatic_proposals_are_written_pending_without_overwriting(
    tmp_path: Path,
) -> None:
    documents = tmp_path / "documents"
    documents.mkdir()
    (documents / "source.docx").write_bytes(b"source")
    sync_registry(tmp_path, source_dir="documents")
    registry = json.loads((tmp_path / ".heva" / "project.json").read_text())
    document_id = registry["documents"][0]["document_id"]

    metadata_path = write_automatic_color_proposals(
        tmp_path,
        document_id,
        ["#FFFF00"],
        {"#FFFF00": "historic"},
        reasoning={"#FFFF00": "Suggested from highlighted sentence context."},
        confidence={"#FFFF00": 0.72},
        source_mechanisms={"#FFFF00": "word_font_color"},
    )
    saved = json.loads(metadata_path.read_text())
    color = saved["color_configuration"]["colors"][0]

    assert not saved["color_configuration"]["human_confirmed"]
    assert color["suggested_label"] == "historic"
    assert color["label"] is None
    assert color["status"] == "pending_review"
    assert color["method"] == "ollama"
    assert color["confidence"] == 0.72
    assert color["source_mechanism"] == "word_font_color"

    with pytest.raises(ColorMappingError, match="will not overwrite"):
        write_automatic_color_proposals(
            tmp_path,
            document_id,
            ["#FF00FF"],
            {"#FF00FF": "economic"},
        )

    unchanged = json.loads(metadata_path.read_text())
    assert unchanged["color_configuration"] == saved["color_configuration"]


def test_pending_map_requires_explicit_decision_before_extraction(tmp_path: Path) -> None:
    documents = tmp_path / "documents"
    documents.mkdir()
    (documents / "source.pdf").write_bytes(b"source")
    sync_registry(tmp_path, source_dir="documents")
    registry = json.loads((tmp_path / ".heva/project.json").read_text())
    document_id = registry["documents"][0]["document_id"]
    proposal = propose_color_configuration(
        ["#FFFF00"], ollama_suggestions={"#FFFF00": "historic"}
    )
    save_color_configuration(tmp_path, document_id, proposal)

    with pytest.raises(ColorMappingError, match="explicitly authorized"):
        load_extraction_color_mapping(tmp_path, document_id)

    authorized = authorize_pending_mapping_for_extraction(
        proposal,
        authorized_by="Research Annotator",
    )
    save_color_configuration(tmp_path, document_id, authorized)
    selected = load_extraction_color_mapping(tmp_path, document_id)

    assert selected.values == {"#FFFF00": "historic"}
    assert selected.status == "pending_review"


def test_document_color_review_persists_explicit_label_and_ignore_decisions(
    tmp_path: Path,
) -> None:
    documents = tmp_path / "documents"
    documents.mkdir()
    (documents / "source.pdf").write_bytes(b"source")
    sync_registry(tmp_path, source_dir="documents")
    registry = json.loads((tmp_path / ".heva/project.json").read_text())
    document_id = registry["documents"][0]["document_id"]
    save_color_configuration(
        tmp_path,
        document_id,
        propose_color_configuration(
            ["#CCCC00", "#FF66CC"],
            generic_suggestions={"#CCCC00": "historic"},
        ),
    )

    confirmed = review_and_confirm_color_configuration(
        tmp_path,
        document_id,
        [
            {"hex": "#CCCC00", "label": "political"},
            {
                "hex": "#FF66CC",
                "ignore_reason": "Formatting color, not an annotation.",
            },
        ],
        confirmed_by="Research Annotator",
    )

    restored = load_color_configuration(tmp_path, document_id)
    assert confirmed.human_confirmed
    assert restored.confirmed_by == "Research Annotator"
    assert {item.hex: item.status for item in restored.colors} == {
        "#CCCC00": "approved",
        "#FF66CC": "ignored",
    }


def test_document_color_review_requires_a_decision_for_every_observed_color(
    tmp_path: Path,
) -> None:
    documents = tmp_path / "documents"
    documents.mkdir()
    (documents / "source.pdf").write_bytes(b"source")
    sync_registry(tmp_path, source_dir="documents")
    registry = json.loads((tmp_path / ".heva/project.json").read_text())
    document_id = registry["documents"][0]["document_id"]
    save_color_configuration(
        tmp_path,
        document_id,
        propose_color_configuration(["#CCCC00", "#FF66CC"]),
    )

    with pytest.raises(ColorMappingError, match="every observed"):
        review_and_confirm_color_configuration(
            tmp_path,
            document_id,
            [{"hex": "#CCCC00", "label": "political"}],
            confirmed_by="Research Annotator",
        )


def test_confirmed_mapping_can_be_shared_only_with_an_exact_pending_palette(
    tmp_path: Path,
) -> None:
    documents = tmp_path / "documents"
    documents.mkdir()
    for name in ("source.pdf", "matching.pdf", "different.pdf"):
        (documents / name).write_bytes(name.encode())
    sync_registry(tmp_path, source_dir="documents")
    registry = json.loads((tmp_path / ".heva/project.json").read_text())
    ids = {
        Path(item["source_path"]).name: item["document_id"]
        for item in registry["documents"]
    }
    source = propose_color_configuration(["#CCCC00", "#FF66CC"])
    source = resolve_color(source, "#CCCC00", label="political")
    source = resolve_color(source, "#FF66CC", label="historic")
    source = confirm_color_configuration(source, confirmed_by="Source Reviewer")
    save_color_configuration(tmp_path, ids["source.pdf"], source)
    save_color_configuration(
        tmp_path,
        ids["matching.pdf"],
        propose_color_configuration(["#CCCC00", "#FF66CC"]),
    )
    save_color_configuration(
        tmp_path,
        ids["different.pdf"],
        propose_color_configuration(["#CCCC00"]),
    )

    applied = apply_shared_color_mapping(
        tmp_path,
        ids["source.pdf"],
        [ids["matching.pdf"]],
        confirmed_by="Batch Reviewer",
    )

    matching = load_color_configuration(tmp_path, ids["matching.pdf"])
    assert applied == (ids["matching.pdf"],)
    assert matching.human_confirmed
    assert matching.confirmed_by == "Batch Reviewer"
    assert matching.shared_from_document_id == ids["source.pdf"]
    assert {item.hex: item.label for item in matching.colors} == {
        "#CCCC00": "political",
        "#FF66CC": "historic",
    }
    with pytest.raises(ColorMappingError, match="different color palette"):
        apply_shared_color_mapping(
            tmp_path,
            ids["source.pdf"],
            [ids["different.pdf"]],
            confirmed_by="Batch Reviewer",
        )
    assert not load_color_configuration(
        tmp_path,
        ids["different.pdf"],
    ).human_confirmed
