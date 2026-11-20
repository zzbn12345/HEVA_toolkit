"""Acceptance tests for project value sets that colors can be mapped to."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from heva.curation.citation_import import import_citation_row
from heva.curation.color_configuration_registry import (
    ProjectColorConfigurationError,
    apply_selected_configuration_to_document,
    create_color_configuration_version,
    document_label_vocabulary,
    load_color_configuration_registry,
    select_color_configuration,
    selected_value_set,
)
from heva.curation.color_mapping import (
    apply_shared_color_mapping,
    load_color_configuration,
    propose_color_configuration,
    resolve_color,
    review_and_confirm_color_configuration,
    save_color_configuration,
)
from heva.curation.contract import HEVA_LABELS, validate_record
from heva.curation.document_contributors import assign_document_annotators
from heva.curation.document_metadata import PackageMetadata, save_package_metadata
from heva.curation.extraction_draft import persist_extraction_draft, promote_extraction_draft
from heva.curation.package_compiler import (
    CSV_FIELDS,
    PackageCompileError,
    compile_csv_packages,
    load_compilation_rows,
)
from heva.curation.package_validator import (
    PackageValidationError,
    build_release,
    validate_document_package,
)
from heva.curation.people_registry import PersonRecord, activate_curator, add_person
from heva.curation.project_registry import load_project_registry, sync_registry
from heva.curation.review_state import record_decisions
from heva.curation.value_sets import (
    HERITAGE_VALUE_SET_ID,
    ValueSetError,
    create_value_set_version,
    get_value_set,
    label_validation_context,
    list_value_sets,
    load_value_set_registry,
    project_label_vocabulary,
)


HEALTH_VALUES = [
    {"label": "physical", "description": "Bodily health and functioning"},
    {"label": "mental"},
    {"label": "social-support"},
]


def _curator(project: Path) -> str:
    person = add_person(project, PersonRecord(name="Project Curator", roles=["curator"]))
    activate_curator(project, person.person_id)
    return person.person_id


def _health_value_set(project: Path):
    return create_value_set_version(
        project,
        value_set_id="health-values",
        name="Health values",
        values=HEALTH_VALUES,
    )


def test_heritage_values_are_built_in_and_never_persisted(tmp_path: Path) -> None:
    """Projects without custom value sets keep exactly the controlled HEVA vocabulary."""

    value_sets = list_value_sets(tmp_path)

    assert [item.value_set_id for item in value_sets] == [HERITAGE_VALUE_SET_ID]
    assert value_sets[0].labels == HEVA_LABELS
    assert get_value_set(tmp_path, None, None).labels == HEVA_LABELS
    assert project_label_vocabulary(tmp_path) == HEVA_LABELS
    assert not (tmp_path / ".heva/value-sets.json").exists()


def test_curator_creates_appended_value_set_versions(tmp_path: Path) -> None:
    """A changed value set is a new version; earlier versions remain reproducible."""

    curator_id = _curator(tmp_path)
    first = _health_value_set(tmp_path)
    before = (tmp_path / ".heva/value-sets.json").read_text()
    second = create_value_set_version(
        tmp_path,
        value_set_id="health-values",
        name="Health values",
        values=[*HEALTH_VALUES, {"label": "environmental"}],
    )

    assert (first.version, second.version) == (1, 2)
    assert first.created_by == curator_id
    assert first.labels == {"physical", "mental", "social-support"}
    assert get_value_set(tmp_path, "health-values", 1).labels == first.labels
    assert json.loads(before)["value_sets"][0] == json.loads(
        (tmp_path / ".heva/value-sets.json").read_text()
    )["value_sets"][0]
    assert project_label_vocabulary(tmp_path) == HEVA_LABELS | second.labels


def test_value_set_requires_active_curator(tmp_path: Path) -> None:
    with pytest.raises(ValueSetError, match="active curator"):
        _health_value_set(tmp_path)


def test_heritage_value_set_cannot_be_redefined(tmp_path: Path) -> None:
    _curator(tmp_path)

    with pytest.raises(ValueSetError, match="built into HEVA"):
        create_value_set_version(
            tmp_path,
            value_set_id=HERITAGE_VALUE_SET_ID,
            name="Replacement",
            values=[{"label": "historic"}],
        )


@pytest.mark.parametrize(
    "values",
    [
        [{"label": "mental"}, {"label": "mental"}],
        [{"label": "Mental Health"}],
        [{"label": "#FFFF00"}],
        [],
    ],
)
def test_invalid_values_are_rejected(tmp_path: Path, values: list[dict[str, str]]) -> None:
    _curator(tmp_path)

    with pytest.raises(ValueError):
        create_value_set_version(
            tmp_path,
            value_set_id="health-values",
            name="Health values",
            values=values,
        )
    assert not (tmp_path / ".heva/value-sets.json").exists()


def test_unreadable_registry_is_reported_without_blocking_file_reads(tmp_path: Path) -> None:
    (tmp_path / ".heva").mkdir()
    (tmp_path / ".heva/value-sets.json").write_text("{not json", encoding="utf-8")

    with pytest.raises(ValueSetError, match="cannot be read"):
        load_value_set_registry(tmp_path)
    assert label_validation_context(tmp_path) == {"labels": HEVA_LABELS}


def test_palette_maps_colors_only_to_its_value_set(tmp_path: Path) -> None:
    """A palette bound to a value set rejects labels from any other vocabulary."""

    _curator(tmp_path)
    health = _health_value_set(tmp_path)
    palette = create_color_configuration_version(
        tmp_path,
        configuration_id="health-palette",
        name="Health palette",
        mappings=[
            {"label": "physical", "hexes": ["#FFFF00"]},
            {"label": "mental", "hexes": ["#00FFFF"]},
        ],
        value_set_id=health.value_set_id,
        value_set_version=health.version,
    )
    select_color_configuration(tmp_path, palette.configuration_id, palette.version)

    assert palette.value_set_reference == ("health-values", 1)
    assert selected_value_set(tmp_path).labels == health.labels
    restored = load_color_configuration_registry(tmp_path).configurations[0]
    assert restored.values == {"#00FFFF": "mental", "#FFFF00": "physical"}
    with pytest.raises(ValueError, match="controlled HEVA label"):
        create_color_configuration_version(
            tmp_path,
            configuration_id="mixed",
            name="Mixed",
            mappings=[{"label": "historic", "hexes": ["#FF0000"]}],
            value_set_id="health-values",
            value_set_version=1,
        )
    with pytest.raises(ProjectColorConfigurationError, match="does not exist"):
        create_color_configuration_version(
            tmp_path,
            configuration_id="unknown",
            name="Unknown",
            mappings=[{"label": "physical", "hexes": ["#FF0000"]}],
            value_set_id="health-values",
            value_set_version=9,
        )


def test_palettes_without_value_set_keep_heritage_meaning(tmp_path: Path) -> None:
    """Palettes saved before value sets existed load and resolve as heritage values."""

    _curator(tmp_path)
    palette = create_color_configuration_version(
        tmp_path,
        configuration_id="heritage",
        name="Heritage",
        mappings=[{"label": "historic", "hexes": ["#FFFF00"]}],
    )
    saved = json.loads((tmp_path / ".heva/color-configurations.json").read_text())

    assert saved["configurations"][0]["value_set_id"] is None
    assert palette.value_set_reference == (HERITAGE_VALUE_SET_ID, 1)
    assert selected_value_set(tmp_path).labels == HEVA_LABELS


def test_record_contract_accepts_an_explicit_vocabulary() -> None:
    """Records use the heritage values by default and a value set when one is given."""

    record = {
        "sentence_id": 1,
        "page": 1,
        "sentence": "Walking helps",
        "tokens": ["Walking", "helps"],
        "values": ["physical"],
        "entities": [{"start": 0, "end": 7, "text": "Walking", "label": "physical"}],
        "ner_tags": ["B-physical", "O"],
    }

    assert {"unknown_label", "invalid_bio_tag"} <= {
        issue.code for issue in validate_record(record).issues
    }
    assert validate_record(record, labels=frozenset({"physical"})).valid


def test_color_decisions_use_the_given_value_set() -> None:
    configuration = propose_color_configuration(["#FFFF00"])

    with pytest.raises(ValueError, match="controlled HEVA label"):
        resolve_color(configuration, "#FFFF00", label="physical")
    resolved = resolve_color(
        configuration,
        "#FFFF00",
        label="physical",
        labels=frozenset({"physical"}),
    )
    assert resolved.colors[0].label == "physical"


def _health_project(tmp_path: Path, *, heritage: bool = False) -> tuple[Path, str]:
    """Build a one-document project annotated with a custom health value set.

    With ``heritage=True`` the same document is mapped to the built-in heritage values.
    """

    project = tmp_path / "health-dataset"
    project.mkdir()
    (project / "report.pdf").write_bytes(b"source")
    sync_registry(project, source_dir=".")
    document_id = load_project_registry(project).documents[0].document_id
    annotator = add_person(project, PersonRecord(name="Original Annotator", roles=["annotator"]))
    curator = add_person(project, PersonRecord(name="Health Curator", roles=["curator"]))
    owner = add_person(
        project,
        PersonRecord(name="Data Owner", roles=["data_owner"], affiliation="Clinic"),
    )
    activate_curator(project, curator.person_id)
    assign_document_annotators(project, document_id, [annotator.person_id])
    import_citation_row(
        project,
        {
            "source_filename": "report.pdf",
            "title": "Community health report",
            "creators": ["Source Author"],
            "item_type": "report",
            "issued_year": 2025,
            "citation": "Source Author. Community health report. 2025.",
            "reference": "https://example.org/health-report",
        },
        validated_by="value-set-fixture/1.0",
    )
    persist_extraction_draft(
        project,
        document_id,
        [{
            "sentence_id": 1,
            "page": 1,
            "sentence": "Daily walks reduce stress.",
            "tokens": ["Daily", "walks", "reduce", "stress", "."],
            "values": ["#FFFF00", "#00FFFF"],
            "entities": [
                {"start": 0, "end": 11, "text": "Daily walks", "label": "#FFFF00"},
                {"start": 19, "end": 25, "text": "stress", "label": "#00FFFF"},
            ],
            "ner_tags": ["B-#FFFF00", "I-#FFFF00", "O", "B-#00FFFF", "O"],
        }],
        extractor="value-set fixture",
        extractor_version="1.0",
    )
    save_color_configuration(
        project,
        document_id,
        propose_color_configuration(["#FFFF00", "#00FFFF"]),
    )
    if heritage:
        palette = create_color_configuration_version(
            project,
            configuration_id="heritage-palette",
            name="Heritage palette",
            mappings=[
                {"label": "social", "hexes": ["#FFFF00"]},
                {"label": "historic", "hexes": ["#00FFFF"]},
            ],
        )
    else:
        health = _health_value_set(project)
        palette = create_color_configuration_version(
            project,
            configuration_id="health-palette",
            name="Health palette",
            mappings=[
                {"label": "physical", "hexes": ["#FFFF00"]},
                {"label": "mental", "hexes": ["#00FFFF"]},
            ],
            value_set_id=health.value_set_id,
            value_set_version=health.version,
        )
    select_color_configuration(project, palette.configuration_id, palette.version)
    promote_extraction_draft(project, document_id)
    record_decisions(project, document_id, [1], status="approved", reviewer=curator.name)
    entry = load_project_registry(project).documents[0]
    metadata = PackageMetadata.model_validate_json(
        (project / entry.metadata_path).read_text(),
        context=label_validation_context(project),
    )
    metadata.annotation_process.review.completed = True
    metadata.annotation_process.review.reviewed_at = datetime(2026, 8, 11, 12, tzinfo=timezone.utc)
    save_package_metadata(project, metadata)
    (project / "dataset-metadata.json").write_text(
        json.dumps({
            "name": "health-values-dataset",
            "title": "Health values dataset",
            "description": "Synthetic dataset annotated with a custom value set.",
            "creators": [owner.name],
            "contributors": [annotator.name, curator.name],
            "license": "CC-BY-4.0",
            "rights": "Annotations may be distributed; source PDFs are excluded.",
            "known_limitations": ["Synthetic acceptance evidence."],
        }),
        encoding="utf-8",
    )
    return project, document_id


def test_custom_value_set_document_validates_and_exports(tmp_path: Path) -> None:
    """A health dataset passes the same validation and export gates as heritage data."""

    project, document_id = _health_project(tmp_path)

    report = validate_document_package(project, document_id)
    archive = build_release(project)
    records = json.loads((project / f"documents/{document_id}/annotations.json").read_text())

    assert [issue.code for issue in report.issues if issue.severity == "error"] == []
    assert archive.exists()
    assert records[0]["values"] == ["mental", "physical"]
    assert records[0]["mapping_provenance"]["config_id"] == "health-palette@1"
    assert document_label_vocabulary(project, document_id) == frozenset(
        {"physical", "mental", "social-support"}
    )
    configuration = load_color_configuration(project, document_id)
    assert {color.label for color in configuration.colors} == {"physical", "mental"}


def test_release_describes_the_value_set_of_every_document(tmp_path: Path) -> None:
    """Released labels can be interpreted without access to the project files."""

    project, document_id = _health_project(tmp_path)

    release = build_release(project)
    descriptor = json.loads((release / "datapackage.json").read_text())
    payload = json.loads((release / "heva-annotations.json").read_text())

    health = {
        "value_set_id": "health-values",
        "version": 1,
        "name": "Health values",
        "description": None,
        "built_in": False,
        "values": [
            {"label": "physical", "description": "Bodily health and functioning"},
            {"label": "mental", "description": None},
            {"label": "social-support", "description": None},
        ],
    }
    assert descriptor["value_sets"] == [health]
    assert payload["value_sets"] == [health]
    assert payload["documents"][0]["value_set"] == {
        "value_set_id": "health-values",
        "version": 1,
    }
    assert "PERSON-" not in (release / "datapackage.json").read_text()


def test_heritage_release_names_the_built_in_value_set(tmp_path: Path) -> None:
    project, _ = _health_project(tmp_path, heritage=True)

    release = build_release(project)
    descriptor = json.loads((release / "datapackage.json").read_text())
    payload = json.loads((release / "heva-annotations.json").read_text())

    assert [item["value_set_id"] for item in descriptor["value_sets"]] == [HERITAGE_VALUE_SET_ID]
    assert descriptor["value_sets"][0]["built_in"] is True
    assert {value["label"] for value in descriptor["value_sets"][0]["values"]} == HEVA_LABELS
    assert payload["documents"][0]["value_set"]["value_set_id"] == HERITAGE_VALUE_SET_ID
    assert payload["documents"][0]["records"][0]["values"] == ["historic", "social"]


def test_custom_labels_without_palette_reference_cannot_be_released(tmp_path: Path) -> None:
    """A document never claims the heritage values while carrying other labels."""

    project, document_id = _health_project(tmp_path)
    metadata_path = project / f"documents/{document_id}/metadata.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["color_configuration"]["configuration_id"] = None
    metadata["color_configuration"]["configuration_version"] = None
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    report = validate_document_package(project, document_id)

    assert "label_outside_value_set" in {issue.code for issue in report.issues}
    with pytest.raises(PackageValidationError, match="label_outside_value_set"):
        build_release(project)


def test_batch_sharing_keeps_the_source_palette_reference(tmp_path: Path) -> None:
    """Documents that receive a shared mapping record which value set the labels use."""

    _curator(tmp_path)
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "a.pdf").write_bytes(b"a")
    (sources / "b.pdf").write_bytes(b"b")
    sync_registry(tmp_path, source_dir="sources")
    source_id, target_id = [item.document_id for item in load_project_registry(tmp_path).documents]
    for document_id in (source_id, target_id):
        save_color_configuration(tmp_path, document_id, propose_color_configuration(["#FFFF00"]))
    health = _health_value_set(tmp_path)
    palette = create_color_configuration_version(
        tmp_path,
        configuration_id="health-palette",
        name="Health palette",
        mappings=[{"label": "mental", "hexes": ["#FFFF00"]}],
        value_set_id=health.value_set_id,
        value_set_version=health.version,
    )
    select_color_configuration(tmp_path, palette.configuration_id, palette.version)
    apply_selected_configuration_to_document(tmp_path, source_id)

    apply_shared_color_mapping(tmp_path, source_id, [target_id], confirmed_by="Project Curator")
    target = load_color_configuration(tmp_path, target_id)

    assert target.colors[0].label == "mental"
    assert (target.configuration_id, target.configuration_version) == ("health-palette", 1)
    assert document_label_vocabulary(tmp_path, target_id) == health.labels


def test_label_outside_document_value_set_is_reported(tmp_path: Path) -> None:
    """A document cannot silently mix labels from two vocabularies."""

    project, document_id = _health_project(tmp_path)
    metadata_path = project / f"documents/{document_id}/metadata.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["color_configuration"]["colors"][0]["label"] = "historic"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    report = validate_document_package(project, document_id)

    assert "label_outside_value_set" in {issue.code for issue in report.issues}
    assert not report.release_ready


def test_color_review_rejects_values_outside_the_selected_set(tmp_path: Path) -> None:
    project, document_id = _health_project(tmp_path)

    with pytest.raises(ValueError, match="controlled HEVA label"):
        review_and_confirm_color_configuration(
            project,
            document_id,
            [{"hex": "#FFFF00", "label": "physical"}, {"hex": "#00FFFF", "label": "mental"}],
            confirmed_by="Health Curator",
            labels=frozenset({"physical"}),
        )


def test_csv_compiler_accepts_the_project_value_sets(tmp_path: Path) -> None:
    """Edited CSV rows that use a project's own values compile back into the package."""

    project, document_id = _health_project(tmp_path)
    annotations = project / f"documents/{document_id}/annotations.json"
    record = json.loads(annotations.read_text())[0]
    edited = project / "edited.csv"
    with edited.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerow(
            {
                field: (
                    json.dumps(record[field])
                    if isinstance(record.get(field), list)
                    else record.get(field) or ""
                )
                for field in CSV_FIELDS
            }
            | {"document_id": document_id, "curated_sentence": "Daily walks reduce stress!"}
        )

    with pytest.raises(PackageCompileError, match="Unknown HEVA label: physical"):
        load_compilation_rows(edited)
    counts = compile_csv_packages(project, edited)

    assert counts == {document_id: 1}
    saved = json.loads(annotations.read_text())[0]
    assert saved["values"] == ["mental", "physical"]
    assert saved["curated_sentence"] == "Daily walks reduce stress!"
