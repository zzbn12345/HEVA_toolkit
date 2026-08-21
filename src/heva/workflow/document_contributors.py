"""Assign stable project-person identities to original document annotations."""

from __future__ import annotations

from pathlib import Path

from heva.workflow.document_metadata import (
    OriginalAnnotatorMetadata,
    PackageMetadata,
    save_package_metadata,
)
from heva.workflow.people_registry import PersonRecord, load_people_registry
from heva.workflow.project_registry import DEFAULT_REGISTRY_PATH, ProjectRegistry


class DocumentContributorError(ValueError):
    """Raised when a document contributor assignment would be ambiguous or invalid."""


def _metadata(root: Path, document_id: str) -> PackageMetadata:
    """Load one registered document metadata record."""

    try:
        registry = ProjectRegistry.model_validate_json(
            (root / DEFAULT_REGISTRY_PATH).read_text(encoding="utf-8")
        )
        entry = next(item for item in registry.documents if item.document_id == document_id)
        path = root / (entry.metadata_path or f"{entry.package_path}/metadata.json")
        return PackageMetadata.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, StopIteration) as error:
        raise DocumentContributorError(
            f"Document {document_id} metadata cannot be loaded."
        ) from error


def _snapshot(person: PersonRecord) -> OriginalAnnotatorMetadata:
    """Copy only stable public identity fields into distributable metadata."""

    return OriginalAnnotatorMetadata(
        person_id=person.person_id,
        name=person.name,
        affiliation=person.affiliation,
        orcid=person.orcid,
    )


def load_document_annotators(
    project_root: str | Path,
    document_id: str,
) -> list[OriginalAnnotatorMetadata]:
    """Return explicit original-annotator assignments for one document."""

    root = Path(project_root).resolve()
    metadata = _metadata(root, document_id)
    if metadata.original_annotators or not metadata.annotator.name:
        return metadata.original_annotators
    registry = load_people_registry(root)
    matches = [
        person
        for person in registry.people
        if "annotator" in person.roles
        and (
            (metadata.annotator.orcid and person.orcid == metadata.annotator.orcid)
            or person.name.casefold() == metadata.annotator.name.casefold()
        )
    ]
    if len(matches) != 1:
        return []
    return assign_document_annotators(root, document_id, [matches[0].person_id])


def assign_document_annotators(
    project_root: str | Path,
    document_id: str,
    person_ids: list[str],
) -> list[OriginalAnnotatorMetadata]:
    """Replace document assignments with validated annotator-role person snapshots."""

    root = Path(project_root).resolve()
    registry = load_people_registry(root)
    requested = list(dict.fromkeys(person_ids))
    people_by_id = {person.person_id: person for person in registry.people}
    missing = [person_id for person_id in requested if person_id not in people_by_id]
    if missing:
        raise DocumentContributorError(
            f"Unknown project person: {', '.join(missing)}."
        )
    invalid = [
        person_id
        for person_id in requested
        if "annotator" not in people_by_id[person_id].roles
    ]
    if invalid:
        raise DocumentContributorError(
            "Original annotators must have the annotator role: " + ", ".join(invalid)
        )
    metadata = _metadata(root, document_id)
    metadata.original_annotators = [_snapshot(people_by_id[item]) for item in requested]
    # Clear the ambiguous singular legacy field after an explicit assignment.
    metadata.annotator = metadata.annotator.model_copy(
        update={"name": None, "affiliation": None, "email": None, "orcid": None}
    )
    save_package_metadata(root, metadata)
    return metadata.original_annotators


def assigned_document_ids(project_root: str | Path, person_id: str) -> list[str]:
    """List documents that prevent a referenced project person from being removed."""

    root = Path(project_root).resolve()
    try:
        registry = ProjectRegistry.model_validate_json(
            (root / DEFAULT_REGISTRY_PATH).read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return []
    assigned: list[str] = []
    for entry in registry.documents:
        try:
            metadata = _metadata(root, entry.document_id)
        except DocumentContributorError:
            continue
        if any(item.person_id == person_id for item in metadata.original_annotators):
            assigned.append(entry.document_id)
    return assigned


def refresh_person_snapshots(project_root: str | Path, person: PersonRecord) -> None:
    """Refresh public snapshots after a project person is edited."""

    root = Path(project_root).resolve()
    for document_id in assigned_document_ids(root, person.person_id):
        metadata = _metadata(root, document_id)
        metadata.original_annotators = [
            _snapshot(person) if item.person_id == person.person_id else item
            for item in metadata.original_annotators
        ]
        save_package_metadata(root, metadata)
