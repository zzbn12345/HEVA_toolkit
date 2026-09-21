"""Acceptance tests for document-by-document review queue assembly."""

from __future__ import annotations

import json
from pathlib import Path

from heva.curation.document_metadata import (
    AnnotationProcessMetadata,
    AnnotatorMetadata,
    ColorConfigurationMetadata,
    ColorMappingMetadata,
    PackageMetadata,
    OriginalAnnotatorMetadata,
    ResourceMetadata,
    RightsMetadata,
    SourceMetadata,
)
from heva.curation.project_registry import sync_registry
from heva.curation.extraction_draft import persist_extraction_draft
from heva.curation.color_mapping import (
    confirm_color_configuration,
    propose_color_configuration,
    resolve_color,
    save_color_configuration,
)
from heva.curation.people_registry import PersonRecord, activate_curator, add_person
from heva.curation.review_queue import (
    list_review_queue,
    load_review_document,
    submit_review_document,
)
from heva.curation.review_state import (
    accept_quality_warning,
    initialize_sentence_reviews,
    record_decisions,
)


def record(sentence_id: int, sentence: str) -> dict[str, object]:
    if sentence == "Short":
        tokens = ["Short"]
        values: list[str] = []
        entities: list[dict[str, object]] = []
        ner_tags = ["O"]
    else:
        tokens = ["Historic", "harbour", "."]
        values = ["historic"]
        entities = [
            {
                "start": 0,
                "end": 16,
                "text": "Historic harbour",
                "label": "historic",
                "color": "#FF40FF",
            }
        ]
        ner_tags = ["B-historic", "I-historic", "O"]
    return {
        "sentence_id": sentence_id,
        "page": 1,
        "sentence": sentence,
        "tokens": tokens,
        "values": values,
        "entities": entities,
        "ner_tags": ner_tags,
        "schema_version": "1.0",
    }


def prepared_project(tmp_path: Path) -> list[dict[str, object]]:
    sources = tmp_path / "documents"
    sources.mkdir()
    (sources / "b.pdf").write_bytes(b"b")
    (sources / "a.pdf").write_bytes(b"a")
    sync_registry(tmp_path, source_dir="documents")
    registry = json.loads((tmp_path / ".heva/project.json").read_text())
    for entry in registry["documents"]:
        package = tmp_path / entry["package_path"]
        (package / "annotations.json").write_text(
            json.dumps(
                [
                    record(1, "Historic harbour."),
                    record(2, "Short"),
                ]
            ),
            encoding="utf-8",
        )
        initialize_sentence_reviews(tmp_path, entry["document_id"])
    return registry["documents"]


def write_ready_metadata(
    tmp_path: Path,
    entry: dict[str, object],
    *,
    citation_confirmed: bool = True,
) -> None:
    curator = add_person(
        tmp_path,
        PersonRecord(name=f"Curator {entry['document_id']}", roles=["curator"]),
    )
    activate_curator(tmp_path, curator.person_id)
    metadata = PackageMetadata(
        document_id=str(entry["document_id"]),
        source=SourceMetadata(
            title="Historic harbour",
            creators=["Research Author"],
            citation="Research Author. Historic harbour.",
            reference="https://example.org/source",
            human_confirmed=citation_confirmed,
            confirmed_by="Annotator" if citation_confirmed else None,
            confirmed_at="2026-07-29T08:30:00Z" if citation_confirmed else None,
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
            authorization_date="2026-07-29",
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
            performed_at="2026-07-29T09:00:00Z",
        ),
        color_configuration=ColorConfigurationMetadata(
            detection_method="manual",
            human_confirmed=True,
            confirmed_by="Annotator",
            confirmed_at="2026-07-29T09:15:00Z",
            colors=[
                ColorMappingMetadata(
                    hex="#FF40FF",
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
                record_count=2,
            )
        ],
    )
    package = tmp_path / str(entry["package_path"])
    (package / "metadata.json").write_text(
        metadata.model_dump_json(indent=2),
        encoding="utf-8",
    )


def test_queue_summarizes_batches_but_keeps_documents_separate(tmp_path: Path) -> None:
    documents = prepared_project(tmp_path)
    first_id = documents[0]["document_id"]
    record_decisions(
        tmp_path,
        first_id,
        [1],
        status="approved",
        reviewer="Annotator",
    )

    queue = list_review_queue(tmp_path)

    assert len(queue) == 2
    assert queue[0].document_id == first_id
    assert queue[0].counts.approved == 1
    assert queue[0].counts.pending == 1
    assert queue[0].completion_percent == 50
    assert queue[1].counts.approved == 0
    assert queue[1].counts.pending == 2
    assert queue[1].completion_percent == 0


def test_needs_correction_is_not_counted_as_completed_review(tmp_path: Path) -> None:
    documents = prepared_project(tmp_path)
    document_id = documents[0]["document_id"]
    record_decisions(
        tmp_path,
        document_id,
        [1],
        status="needs_correction",
        reviewer="Annotator",
    )
    record_decisions(
        tmp_path,
        document_id,
        [2],
        status="excluded",
        reviewer="Annotator",
    )

    item = next(
        row for row in list_review_queue(tmp_path) if row.document_id == document_id
    )

    assert item.completion_percent == 50
    assert item.counts.needs_correction == 1
    assert item.counts.excluded == 1


def test_document_review_contains_only_selected_document_and_navigation(tmp_path: Path) -> None:
    documents = prepared_project(tmp_path)

    selected = load_review_document(tmp_path, documents[0]["document_id"])

    assert selected["document_id"] == documents[0]["document_id"]
    assert selected["previous_document_id"] is None
    assert selected["next_document_id"] == documents[1]["document_id"]
    assert [item["record"]["sentence_id"] for item in selected["sentences"]] == [1, 2]
    assert selected["sentences"][1]["flags"]


def test_unresolved_extraction_draft_is_visible_but_not_reviewable(tmp_path: Path) -> None:
    """Raw colored spans remain inspectable before semantic labels are configured."""

    sources = tmp_path / "documents"
    sources.mkdir()
    (sources / "source.pdf").write_bytes(b"source")
    sync_registry(tmp_path, source_dir="documents")
    registry = json.loads((tmp_path / ".heva/project.json").read_text())
    document_id = registry["documents"][0]["document_id"]
    curator = add_person(tmp_path, PersonRecord(name="Curator", roles=["curator"]))
    activate_curator(tmp_path, curator.person_id)
    persist_extraction_draft(
        tmp_path,
        document_id,
        [
            {
                "sentence_id": 1,
                "page": 1,
                "sentence": "Historic harbour",
                "tokens": ["Historic", "harbour"],
                "values": ["#FFFF00"],
                "entities": [
                    {
                        "start": 0,
                        "end": 16,
                        "text": "Historic harbour",
                        "label": "#FFFF00",
                    }
                ],
                "ner_tags": ["B-#FFFF00", "I-#FFFF00"],
            }
        ],
        extractor="test extractor",
        extractor_version="1.0",
    )

    selected = load_review_document(tmp_path, document_id)

    assert selected["draft_only"] is True
    assert selected["editability"] == {
        "editable": False,
        "code": "color_configuration_required",
        "message": (
            "These sentences are raw extraction drafts. Extracted text can be edited "
            "after every observed color has a confirmed HEVA label."
        ),
        "action": (
            "Open Color config, assign and confirm the labels, then build the canonical "
            "annotations. Citation and annotator metadata do not lock editing."
        ),
        "href": f"/create?document_id={document_id}&section=colors",
    }
    assert selected["annotation_complete"] is False
    assert selected["sentences"][0]["record"]["entities"][0] == {
        "start": 0,
        "end": 16,
        "text": "Historic harbour",
        "label": "unresolved",
        "color": "#FFFF00",
    }
    assert selected["sentences"][0]["review"]["status"] == "pending"
    assert selected["sentences"][0]["flags"][0]["code"] == "unresolved_color_mapping"
    assert "confirmed color configuration" in selected["sentences"][0]["flags"][0][
        "message"
    ]
    assert "confirm its colors" not in selected["sentences"][0]["flags"][0]["message"]


def test_confirmed_colors_remain_complete_while_annotations_are_still_a_draft(
    tmp_path: Path,
) -> None:
    """Color confirmation and canonical annotation generation are separate gates."""

    sources = tmp_path / "documents"
    sources.mkdir()
    (sources / "source.pdf").write_bytes(b"source")
    sync_registry(tmp_path, source_dir="documents")
    registry = json.loads((tmp_path / ".heva/project.json").read_text())
    document_id = registry["documents"][0]["document_id"]
    curator = add_person(tmp_path, PersonRecord(name="Researcher", roles=["curator"]))
    activate_curator(tmp_path, curator.person_id)
    persist_extraction_draft(
        tmp_path,
        document_id,
        [
            {
                "sentence_id": 1,
                "page": 1,
                "sentence": "Historic harbour",
                "tokens": ["Historic", "harbour"],
                "values": ["#FF40FF"],
                "entities": [
                    {
                        "start": 0,
                        "end": 16,
                        "text": "Historic harbour",
                        "label": "#FF40FF",
                    }
                ],
                "ner_tags": ["B-#FF40FF", "I-#FF40FF"],
            }
        ],
        extractor="test extractor",
        extractor_version="1.0",
    )
    configuration = propose_color_configuration(["#FF40FF"])
    configuration = resolve_color(configuration, "#FF40FF", label="historic")
    configuration = confirm_color_configuration(
        configuration,
        confirmed_by="Researcher",
    )
    save_color_configuration(tmp_path, document_id, configuration)

    selected = load_review_document(tmp_path, document_id)

    assert selected["draft_only"] is True
    assert selected["readiness_gates"]["color_configuration"] is True
    assert selected["readiness_gates"]["extraction"] is False
    assert selected["readiness_gates"]["sentence_review"] is False
    assert "Review and confirm the document color configuration." not in selected[
        "blocking_reasons"
    ]


def test_canonical_annotations_explain_active_curator_edit_lock(tmp_path: Path) -> None:
    documents = prepared_project(tmp_path)
    document_id = str(documents[0]["document_id"])

    selected = load_review_document(tmp_path, document_id)

    assert selected["draft_only"] is False
    assert selected["editability"]["editable"] is False
    assert selected["editability"]["code"] == "active_curator_required"
    assert selected["editability"]["href"] == "/people"
    assert "Citation and original annotator metadata do not lock editing" in selected[
        "editability"
    ]["action"]


def test_accepted_warning_is_not_an_active_problem_but_remains_visible(tmp_path: Path) -> None:
    documents = prepared_project(tmp_path)
    document_id = str(documents[0]["document_id"])
    curator = add_person(tmp_path, PersonRecord(name="Curator", roles=["curator"]))
    activate_curator(tmp_path, curator.person_id)

    accept_quality_warning(
        tmp_path,
        document_id,
        2,
        "unusually_short_sentence",
        reviewer="Curator",
    )
    selected = load_review_document(tmp_path, document_id)
    sentence = next(
        item for item in selected["sentences"] if item["record"]["sentence_id"] == 2
    )

    assert "unusually_short_sentence" not in {
        flag["code"] for flag in sentence["flags"]
    }
    assert "unusually_short_sentence" in {
        flag["code"] for flag in sentence["accepted_flags"]
    }


def test_document_is_complete_only_when_all_four_gates_pass(tmp_path: Path) -> None:
    documents = prepared_project(tmp_path)
    entry = documents[0]
    document_id = str(entry["document_id"])
    write_ready_metadata(tmp_path, entry)
    record_decisions(
        tmp_path,
        document_id,
        [1],
        status="approved",
        reviewer="Annotator",
    )
    record_decisions(
        tmp_path,
        document_id,
        [2],
        status="excluded",
        reviewer="Annotator",
    )

    item = next(row for row in list_review_queue(tmp_path) if row.document_id == document_id)

    assert item.annotation_complete is True
    assert item.completion_percent == 100
    assert all(item.readiness_gates.values())
    assert item.blocking_reasons == []


def test_legacy_submission_state_does_not_lock_sentence_review(
    tmp_path: Path,
) -> None:
    documents = prepared_project(tmp_path)
    entry = documents[0]
    document_id = str(entry["document_id"])
    write_ready_metadata(tmp_path, entry)
    record_decisions(
        tmp_path,
        document_id,
        [1, 2],
        status="approved",
        reviewer="Annotator",
    )

    selected = submit_review_document(
        tmp_path,
        document_id,
        submitted_by="Annotator",
    )

    assert selected["status"] == "in_review"
    assert selected["annotation_complete"] is True
    package = tmp_path / str(entry["package_path"])
    metadata = json.loads((package / "metadata.json").read_text())
    assert metadata["annotation_process"]["review"]["completed"] is True
    assert metadata["annotation_process"]["review"]["reviewed_at"]
    curation = json.loads((tmp_path / ".heva/documents" / entry["document_id"] / "curation-state.json").read_text())
    assert curation["candidates"][0]["submitted_by"] == "Annotator"
    assert curation["candidates"][0]["validator_report"]["valid"] is True
    assert len(curation["candidates"][0]["candidate_id"]) == 64
    record_decisions(
        tmp_path,
        document_id,
        [1],
        status="excluded",
        reviewer="Annotator",
    )
    reopened = load_review_document(tmp_path, document_id)
    assert reopened["sentences"][0]["review"]["status"] == "excluded"


def test_unconfirmed_citation_does_not_block_annotation_submission(tmp_path: Path) -> None:
    documents = prepared_project(tmp_path)
    entry = documents[0]
    document_id = str(entry["document_id"])
    write_ready_metadata(tmp_path, entry, citation_confirmed=False)
    record_decisions(
        tmp_path,
        document_id,
        [1, 2],
        status="approved",
        reviewer="Annotator",
    )

    item = next(row for row in list_review_queue(tmp_path) if row.document_id == document_id)

    assert item.annotation_complete is True
    assert item.readiness_gates == {
        "curator": True,
        "original_annotator": True,
        "citation": False,
        "color_configuration": True,
        "extraction": True,
        "sentence_review": True,
    }
    assert item.blocking_reasons == []
