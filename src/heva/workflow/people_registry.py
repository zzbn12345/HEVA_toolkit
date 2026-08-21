"""Project people and roles for accountable HEVA curation.

The registry distinguishes people from the roles they exercise. A person may be an
original PDF annotator, a curator using HEVA, and/or the data owner responsible for an
approved document. Existing project ``annotators.json`` records represented the active
HEVA operator, so migration assigns them the curator role rather than inventing original
annotation authorship.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


PEOPLE_PATH = Path(".heva/people.json")
LEGACY_ANNOTATORS_PATH = Path(".heva/annotators.json")
PersonRole = Literal["annotator", "curator", "data_owner"]


class PersonRecord(BaseModel):
    """One identified person and the project roles they may exercise."""

    model_config = ConfigDict(extra="forbid")

    person_id: str = Field(
        default_factory=lambda: f"PERSON-{uuid4().hex[:12].upper()}",
        pattern=r"^PERSON-[A-Z0-9]+$",
    )
    name: str = Field(min_length=1)
    roles: list[PersonRole] = Field(min_length=1)
    affiliation: str | None = None
    email: str | None = Field(default=None, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    orcid: str | None = Field(default=None, pattern=r"^\d{4}-\d{4}-\d{4}-[\dX]{4}$")

    @field_validator("name", "affiliation", "email", "orcid", mode="before")
    @classmethod
    def normalize_text(cls, value: object) -> object:
        """Trim form/import values and normalize optional blanks to null."""

        if isinstance(value, str):
            return value.strip() or None
        return value

    @field_validator("roles")
    @classmethod
    def normalize_roles(cls, roles: list[PersonRole]) -> list[PersonRole]:
        """Store each controlled role once in stable workflow order."""

        order = {"annotator": 0, "curator": 1, "data_owner": 2}
        return sorted(set(roles), key=order.__getitem__)


class PeopleRegistry(BaseModel):
    """Versioned people collection and the curator active in this workspace."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    active_curator_id: str | None = None
    people: list[PersonRecord] = Field(default_factory=list)

    def active_curator(self) -> PersonRecord | None:
        """Return the selected curator when the referenced person still has that role."""

        return next(
            (
                person
                for person in self.people
                if person.person_id == self.active_curator_id
                and "curator" in person.roles
            ),
            None,
        )


class PeopleRegistryError(ValueError):
    """Raised when project people cannot be loaded or changed safely."""


def _write_registry(path: Path, registry: PeopleRegistry) -> None:
    """Persist people atomically so an interrupted write cannot truncate the registry."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(registry.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _legacy_person_id(annotator_id: str | None, index: int) -> str:
    """Derive a stable person identifier without retaining misleading ANN semantics."""

    if annotator_id and annotator_id.startswith("ANN-"):
        return f"PERSON-{annotator_id.removeprefix('ANN-')}"
    return f"PERSON-LEGACY{index:04d}"


def _migrate_legacy_annotators(root: Path) -> PeopleRegistry | None:
    """Import the former operator collection as curators without deleting evidence."""

    legacy_path = root / LEGACY_ANNOTATORS_PATH
    if not legacy_path.is_file():
        return None
    try:
        decoded = json.loads(legacy_path.read_text(encoding="utf-8"))
        legacy_people = decoded.get("annotators", [])
        active_legacy_id = decoded.get("active_annotator_id")
        people = [
            PersonRecord(
                person_id=_legacy_person_id(item.get("annotator_id"), index),
                name=item.get("name"),
                roles=["curator"],
                affiliation=item.get("affiliation"),
                email=item.get("email"),
                orcid=item.get("orcid"),
            )
            for index, item in enumerate(legacy_people, start=1)
        ]
    except (OSError, json.JSONDecodeError, ValidationError, AttributeError) as error:
        raise PeopleRegistryError(
            "The former annotator collection cannot be migrated to project people."
        ) from error
    active_curator_id = next(
        (
            person.person_id
            for person, item in zip(people, legacy_people, strict=True)
            if item.get("annotator_id") == active_legacy_id
        ),
        None,
    )
    return PeopleRegistry(active_curator_id=active_curator_id, people=people)


def load_people_registry(project_root: str | Path) -> PeopleRegistry:
    """Load people, creating a one-time compatibility migration when necessary."""

    root = Path(project_root)
    path = root / PEOPLE_PATH
    try:
        return PeopleRegistry.model_validate_json(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        migrated = _migrate_legacy_annotators(root)
        registry = migrated or PeopleRegistry()
        if migrated is not None:
            _write_registry(path, registry)
        return registry
    except (OSError, ValidationError) as error:
        raise PeopleRegistryError("The project people registry cannot be read.") from error


def save_people_registry(project_root: str | Path, registry: PeopleRegistry) -> Path:
    """Validate cross-record identity and persist the project people registry."""

    identifiers = [person.person_id for person in registry.people]
    if len(identifiers) != len(set(identifiers)):
        raise PeopleRegistryError("Every project person must have a unique person_id.")
    if registry.active_curator_id is not None and registry.active_curator() is None:
        raise PeopleRegistryError(
            "The active curator must reference a person with the curator role."
        )
    path = Path(project_root) / PEOPLE_PATH
    _write_registry(path, registry)
    return path


def add_person(project_root: str | Path, person: PersonRecord) -> PersonRecord:
    """Add one validated person without implicitly selecting any active role."""

    registry = load_people_registry(project_root)
    if any(existing.person_id == person.person_id for existing in registry.people):
        raise PeopleRegistryError(f"Person {person.person_id} already exists.")
    registry.people.append(person)
    save_people_registry(project_root, registry)
    return person


def update_person(
    project_root: str | Path,
    person_id: str,
    replacement: PersonRecord,
) -> PersonRecord:
    """Replace editable person fields while preserving the stable identifier."""

    if replacement.person_id != person_id:
        raise PeopleRegistryError("A person_id cannot be changed during an update.")
    registry = load_people_registry(project_root)
    for index, existing in enumerate(registry.people):
        if existing.person_id != person_id:
            continue
        if registry.active_curator_id == person_id and "curator" not in replacement.roles:
            raise PeopleRegistryError(
                "Select another active curator before removing this curator role."
            )
        if "annotator" in existing.roles and "annotator" not in replacement.roles:
            from heva.workflow.document_contributors import assigned_document_ids

            assigned = assigned_document_ids(project_root, person_id)
            if assigned:
                raise PeopleRegistryError(
                    "Reassign this original annotator before removing their annotator role: "
                    + ", ".join(assigned)
                )
        registry.people[index] = replacement
        save_people_registry(project_root, registry)
        from heva.workflow.document_contributors import refresh_person_snapshots

        refresh_person_snapshots(project_root, replacement)
        return replacement
    raise PeopleRegistryError(f"Person {person_id} does not exist.")


def activate_curator(project_root: str | Path, person_id: str) -> PersonRecord:
    """Select the curator whose identity will be recorded by subsequent actions."""

    registry = load_people_registry(project_root)
    person = next(
        (candidate for candidate in registry.people if candidate.person_id == person_id),
        None,
    )
    if person is None:
        raise PeopleRegistryError(f"Person {person_id} does not exist.")
    if "curator" not in person.roles:
        raise PeopleRegistryError("Only a person with the curator role can be activated.")
    registry.active_curator_id = person_id
    save_people_registry(project_root, registry)
    return person


def remove_person(project_root: str | Path, person_id: str) -> PeopleRegistry:
    """Remove current configuration while leaving historical event evidence untouched."""

    from heva.workflow.document_contributors import assigned_document_ids

    assigned = assigned_document_ids(project_root, person_id)
    if assigned:
        raise PeopleRegistryError(
            "Reassign this original annotator before removing them from the project: "
            + ", ".join(assigned)
        )

    registry = load_people_registry(project_root)
    retained = [person for person in registry.people if person.person_id != person_id]
    if len(retained) == len(registry.people):
        raise PeopleRegistryError(f"Person {person_id} does not exist.")
    registry.people = retained
    if registry.active_curator_id == person_id:
        registry.active_curator_id = next(
            (person.person_id for person in retained if "curator" in person.roles),
            None,
        )
    save_people_registry(project_root, registry)
    return registry
