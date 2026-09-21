"""Acceptance tests for explicit original-annotator document assignments."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from heva.app.main import create_app
from heva.curation.document_contributors import (
    DocumentContributorError,
    assign_document_annotators,
    load_document_annotators,
)
from heva.curation.document_metadata import PackageMetadata, save_package_metadata
from heva.curation.people_registry import (
    PeopleRegistryError,
    PersonRecord,
    activate_curator,
    add_person,
    remove_person,
    update_person,
)
from heva.curation.project_registry import load_project_registry, sync_registry


def _document(tmp_path: Path) -> str:
    sources = tmp_path / "documents"
    sources.mkdir()
    (sources / "source.pdf").write_bytes(b"pdf")
    sync_registry(tmp_path, source_dir="documents")
    registry = load_project_registry(tmp_path)
    return registry.documents[0].document_id


def test_multiple_original_annotators_are_public_snapshots_without_email(
    tmp_path: Path,
) -> None:
    document_id = _document(tmp_path)
    first = add_person(
        tmp_path,
        PersonRecord(
            person_id="PERSON-FIRST",
            name="First Annotator",
            roles=["annotator"],
            affiliation="Archive",
            email="private@example.org",
            orcid="0000-0002-1825-0097",
        ),
    )
    second = add_person(
        tmp_path,
        PersonRecord(person_id="PERSON-SECOND", name="Second Annotator", roles=["annotator"]),
    )

    assigned = assign_document_annotators(
        tmp_path, document_id, [first.person_id, second.person_id]
    )
    metadata = json.loads(
        (tmp_path / "documents" / document_id / "metadata.json").read_text()
    )

    assert [item.person_id for item in assigned] == ["PERSON-FIRST", "PERSON-SECOND"]
    assert "email" not in metadata["original_annotators"][0]
    assert metadata["original_annotators"][0]["affiliation"] == "Archive"


def test_active_curator_is_never_inferred_as_original_annotator(tmp_path: Path) -> None:
    document_id = _document(tmp_path)
    curator = add_person(
        tmp_path,
        PersonRecord(person_id="PERSON-CURATOR", name="Curator", roles=["curator"]),
    )
    activate_curator(tmp_path, curator.person_id)

    assert load_document_annotators(tmp_path, document_id) == []
    with pytest.raises(DocumentContributorError, match="annotator role"):
        assign_document_annotators(tmp_path, document_id, [curator.person_id])


def test_assigned_person_edits_refresh_snapshots_and_removal_is_blocked(
    tmp_path: Path,
) -> None:
    document_id = _document(tmp_path)
    person = add_person(
        tmp_path,
        PersonRecord(person_id="PERSON-ONE", name="Old Name", roles=["annotator"]),
    )
    assign_document_annotators(tmp_path, document_id, [person.person_id])

    update_person(
        tmp_path,
        person.person_id,
        PersonRecord(
            person_id=person.person_id,
            name="New Name",
            roles=["annotator"],
            affiliation="University",
        ),
    )

    assert load_document_annotators(tmp_path, document_id)[0].name == "New Name"
    with pytest.raises(PeopleRegistryError, match="annotator role"):
        update_person(
            tmp_path,
            person.person_id,
            PersonRecord(
                person_id=person.person_id,
                name="New Name",
                roles=["data_owner"],
            ),
        )
    with pytest.raises(PeopleRegistryError, match=document_id):
        remove_person(tmp_path, person.person_id)


def test_unambiguous_legacy_singular_annotator_migrates_to_person_reference(
    tmp_path: Path,
) -> None:
    document_id = _document(tmp_path)
    add_person(
        tmp_path,
        PersonRecord(
            person_id="PERSON-LEGACY",
            name="Legacy Annotator",
            roles=["annotator"],
        ),
    )
    metadata = PackageMetadata(document_id=document_id)
    metadata.annotator.name = "Legacy Annotator"
    save_package_metadata(tmp_path, metadata)

    assigned = load_document_annotators(tmp_path, document_id)

    assert [item.person_id for item in assigned] == ["PERSON-LEGACY"]
    restored = json.loads(
        (tmp_path / "documents" / document_id / "metadata.json").read_text()
    )
    assert restored["annotator"]["name"] is None


def test_document_annotators_can_be_assigned_programmatically(tmp_path: Path) -> None:
    document_id = _document(tmp_path)
    person = add_person(
        tmp_path,
        PersonRecord(
            person_id="PERSON-API",
            name="API Annotator",
            roles=["annotator"],
        ),
    )
    client = TestClient(create_app(tmp_path))

    saved = client.put(
        f"/api/documents/{document_id}/annotators",
        json={"person_ids": [person.person_id]},
    )
    loaded = client.get(f"/api/documents/{document_id}/annotators")

    assert saved.status_code == 200
    assert loaded.json()["assigned_person_ids"] == [person.person_id]
