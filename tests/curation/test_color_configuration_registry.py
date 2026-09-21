"""Acceptance tests for immutable reusable project color configurations."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from heva.curation.color_configuration_registry import (
    ProjectColorConfigurationError,
    ProjectColorMapping,
    apply_selected_configuration_to_document,
    create_color_configuration_version,
    load_color_configuration_registry,
    select_color_configuration,
)
from heva.curation.color_mapping import (
    load_color_configuration,
    propose_color_configuration,
    save_color_configuration,
)
from heva.curation.people_registry import PersonRecord, activate_curator, add_person
from heva.curation.project_registry import sync_registry


def _curator(project: Path) -> str:
    person = add_person(project, PersonRecord(name="Project Curator", roles=["curator"]))
    activate_curator(project, person.person_id)
    return person.person_id


def test_one_category_accepts_several_normalized_hex_values(tmp_path: Path) -> None:
    """Different shades can intentionally represent the same HEVA category."""

    _curator(tmp_path)
    configuration = create_color_configuration_version(
        tmp_path,
        configuration_id="student-palette",
        name="Student palette",
        mappings=[{"label": "historic", "hexes": ["#ffff00", "#FFF200"]}],
    )

    assert configuration.version == 1
    assert configuration.values == {
        "#FFF200": "historic",
        "#FFFF00": "historic",
    }


def test_same_hex_cannot_have_two_meanings(tmp_path: Path) -> None:
    """An immutable version never contains an ambiguous semantic mapping."""

    _curator(tmp_path)

    with pytest.raises(ValueError, match="assigned to both"):
        create_color_configuration_version(
            tmp_path,
            configuration_id="ambiguous",
            name="Ambiguous",
            mappings=[
                {"label": "historic", "hexes": ["#FFFF00"]},
                {"label": "economic", "hexes": ["#FFFF00"]},
            ],
        )


def test_changes_append_a_version_and_preserve_previous_bytes(tmp_path: Path) -> None:
    """Changing semantic convention creates a new version rather than editing history."""

    _curator(tmp_path)
    first = create_color_configuration_version(
        tmp_path,
        configuration_id="heritage",
        name="Heritage colors",
        mappings=[{"label": "historic", "hexes": ["#FFFF00"]}],
    )
    first_snapshot = first.model_dump(mode="json")
    second = create_color_configuration_version(
        tmp_path,
        configuration_id="heritage",
        name="Heritage colors",
        mappings=[{"label": "political", "hexes": ["#FFFF00"]}],
    )
    restored = load_color_configuration_registry(tmp_path)

    assert second.version == 2
    assert restored.configurations[0].model_dump(mode="json") == first_snapshot
    assert restored.configurations[1].version == 2


def test_corrupt_selection_is_rejected_on_load(tmp_path: Path) -> None:
    """A project cannot claim to select a missing immutable version."""

    path = tmp_path / ".heva/color-configurations.json"
    path.parent.mkdir()
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "selected": {
                    "configuration_id": "missing",
                    "version": 1,
                    "selected_by": "PERSON-ABC",
                    "selected_at": "2026-08-11T10:00:00Z",
                },
                "configurations": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ProjectColorConfigurationError, match="cannot be read"):
        load_color_configuration_registry(tmp_path)


def test_creation_and_selection_require_active_curator(tmp_path: Path) -> None:
    """Reusable semantic decisions always have an accountable curator."""

    with pytest.raises(ProjectColorConfigurationError, match="active curator"):
        create_color_configuration_version(
            tmp_path,
            configuration_id="heritage",
            name="Heritage",
            mappings=[{"label": "historic", "hexes": ["#FFFF00"]}],
        )


def test_selected_version_resolves_document_palette_with_provenance(tmp_path: Path) -> None:
    """A document records the exact reusable version that assigned its labels."""

    curator_id = _curator(tmp_path)
    documents = tmp_path / "sources"
    documents.mkdir()
    (documents / "source.pdf").write_bytes(b"source")
    sync_registry(tmp_path, source_dir="sources")
    registry = json.loads((tmp_path / ".heva/project.json").read_text())
    document_id = registry["documents"][0]["document_id"]
    save_color_configuration(
        tmp_path,
        document_id,
        propose_color_configuration(["#FFFF00", "#FFF200"]),
    )
    configuration = create_color_configuration_version(
        tmp_path,
        configuration_id="student-palette",
        name="Student palette",
        mappings=[{"label": "historic", "hexes": ["#FFFF00", "#FFF200"]}],
    )
    select_color_configuration(tmp_path, configuration.configuration_id, 1)

    apply_selected_configuration_to_document(tmp_path, document_id)
    restored = load_color_configuration(tmp_path, document_id)

    assert restored.configuration_id == "student-palette"
    assert restored.configuration_version == 1
    assert restored.human_confirmed
    assert {color.hex: color.label for color in restored.colors} == {
        "#FFF200": "historic",
        "#FFFF00": "historic",
    }
    selection = load_color_configuration_registry(tmp_path).selected
    assert selection is not None and selection.selected_by == curator_id


def test_document_rejects_colors_missing_from_selected_version(tmp_path: Path) -> None:
    """A reusable configuration cannot silently ignore an unrecognized document shade."""

    _curator(tmp_path)
    documents = tmp_path / "sources"
    documents.mkdir()
    (documents / "source.pdf").write_bytes(b"source")
    sync_registry(tmp_path, source_dir="sources")
    registry = json.loads((tmp_path / ".heva/project.json").read_text())
    document_id = registry["documents"][0]["document_id"]
    save_color_configuration(
        tmp_path,
        document_id,
        propose_color_configuration(["#FF00FF"]),
    )
    configuration = create_color_configuration_version(
        tmp_path,
        configuration_id="heritage",
        name="Heritage",
        mappings=[ProjectColorMapping(label="historic", hexes=["#FFFF00"])],
    )
    select_color_configuration(tmp_path, configuration.configuration_id, 1)

    with pytest.raises(ProjectColorConfigurationError, match="#FF00FF"):
        apply_selected_configuration_to_document(tmp_path, document_id)
