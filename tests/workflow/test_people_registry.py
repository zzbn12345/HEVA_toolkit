"""Acceptance tests for project people and accountable workflow roles."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from heva.workflow.people_registry import (
    PeopleRegistryError,
    PersonRecord,
    activate_curator,
    add_person,
    load_people_registry,
    remove_person,
    update_person,
)


def test_people_can_hold_multiple_roles_and_select_active_curator(tmp_path: Path) -> None:
    """One identity may curate and own data without conflating original annotation."""

    person = add_person(
        tmp_path,
        PersonRecord(
            name="  Alex Researcher  ",
            roles=["data_owner", "curator", "curator"],
            affiliation=" Heritage Lab ",
        ),
    )
    activate_curator(tmp_path, person.person_id)
    restored = load_people_registry(tmp_path)

    assert person.name == "Alex Researcher"
    assert person.roles == ["curator", "data_owner"]
    assert restored.active_curator() == person
    assert (tmp_path / ".heva/people.json").is_file()


def test_original_annotator_cannot_be_activated_as_curator(tmp_path: Path) -> None:
    """An original PDF annotator is not silently authorized to curate the package."""

    annotator = add_person(
        tmp_path,
        PersonRecord(name="Original Annotator", roles=["annotator"]),
    )

    with pytest.raises(PeopleRegistryError, match="curator role"):
        activate_curator(tmp_path, annotator.person_id)


def test_active_curator_role_cannot_be_removed_implicitly(tmp_path: Path) -> None:
    """Role edits cannot leave workflow actions attributed to an invalid selection."""

    person = add_person(tmp_path, PersonRecord(name="Curator", roles=["curator"]))
    activate_curator(tmp_path, person.person_id)

    with pytest.raises(PeopleRegistryError, match="Select another active curator"):
        update_person(
            tmp_path,
            person.person_id,
            PersonRecord(
                person_id=person.person_id,
                name=person.name,
                roles=["annotator"],
            ),
        )


def test_removing_active_curator_selects_another_curator_only(tmp_path: Path) -> None:
    """Removal never promotes an annotator or owner into the active curator role."""

    first = add_person(tmp_path, PersonRecord(name="First", roles=["curator"]))
    add_person(tmp_path, PersonRecord(name="Annotator", roles=["annotator"]))
    second = add_person(tmp_path, PersonRecord(name="Second", roles=["curator"]))
    activate_curator(tmp_path, first.person_id)

    registry = remove_person(tmp_path, first.person_id)

    assert registry.active_curator_id == second.person_id


def test_legacy_operator_profiles_migrate_as_curators_without_deletion(
    tmp_path: Path,
) -> None:
    """Former app operators become curators, never inferred original annotators."""

    legacy_path = tmp_path / ".heva/annotators.json"
    legacy_path.parent.mkdir()
    legacy_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "active_annotator_id": "ANN-ABC123",
                "annotators": [
                    {
                        "annotator_id": "ANN-ABC123",
                        "name": "Legacy Operator",
                        "affiliation": "Heritage Lab",
                        "email": None,
                        "orcid": None,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    registry = load_people_registry(tmp_path)

    assert registry.people[0].person_id == "PERSON-ABC123"
    assert registry.people[0].roles == ["curator"]
    assert registry.active_curator_id == "PERSON-ABC123"
    assert legacy_path.is_file()
    assert (tmp_path / ".heva/people.json").is_file()


def test_invalid_legacy_people_fail_without_partial_migration(tmp_path: Path) -> None:
    """Malformed legacy identity data never creates a misleading people registry."""

    legacy_path = tmp_path / ".heva/annotators.json"
    legacy_path.parent.mkdir()
    legacy_path.write_text(
        json.dumps(
            {
                "active_annotator_id": "ANN-BROKEN",
                "annotators": [{"annotator_id": "ANN-BROKEN", "name": ""}],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(PeopleRegistryError, match="cannot be migrated"):
        load_people_registry(tmp_path)

    assert not (tmp_path / ".heva/people.json").exists()
