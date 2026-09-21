"""Strict CSV adapter for an authoritative project people spreadsheet."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Iterable

from pydantic import ValidationError

from heva.curation.people_registry import (
    PeopleRegistry,
    PeopleRegistryError,
    PersonRecord,
    save_people_registry,
)


PEOPLE_COLUMNS = (
    "person_id",
    "name",
    "roles",
    "affiliation",
    "email",
    "orcid",
    "active_curator",
)


class PeopleImportError(ValueError):
    """Raised when a people spreadsheet cannot replace registry state safely."""


def _boolean(value: str, row_number: int) -> bool:
    normalized = value.strip().lower()
    if normalized in {"true", "yes", "1"}:
        return True
    if normalized in {"false", "no", "0", ""}:
        return False
    raise PeopleImportError(
        f"Row {row_number} active_curator must be true/false, yes/no, or 1/0."
    )


def read_people_csv(path: str | Path) -> PeopleRegistry:
    """Parse every CSV row before returning one schema-valid replacement registry."""

    source = Path(path)
    try:
        with source.open(newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream)
            if tuple(reader.fieldnames or ()) != PEOPLE_COLUMNS:
                raise PeopleImportError(
                    "People CSV columns must be exactly: " + ", ".join(PEOPLE_COLUMNS)
                )
            people: list[PersonRecord] = []
            active_ids: list[str] = []
            for row_number, row in enumerate(reader, start=2):
                roles = [value.strip() for value in row["roles"].split(";") if value.strip()]
                try:
                    person = PersonRecord(
                        person_id=row["person_id"].strip(),
                        name=row["name"],
                        roles=roles,
                        affiliation=row["affiliation"],
                        email=row["email"],
                        orcid=row["orcid"],
                    )
                except ValidationError as error:
                    raise PeopleImportError(f"Invalid people CSV row {row_number}: {error}") from error
                people.append(person)
                if _boolean(row["active_curator"], row_number):
                    active_ids.append(person.person_id)
    except OSError as error:
        raise PeopleImportError(f"Cannot read people CSV: {error}") from error
    if not people:
        raise PeopleImportError("People CSV must contain at least one person.")
    if len(active_ids) > 1:
        raise PeopleImportError("People CSV may select at most one active curator.")
    try:
        registry = PeopleRegistry(
            active_curator_id=active_ids[0] if active_ids else None,
            people=people,
        )
        identifiers = [person.person_id for person in people]
        if len(identifiers) != len(set(identifiers)):
            raise PeopleImportError("People CSV contains duplicate person_id values.")
        if registry.active_curator_id and registry.active_curator() is None:
            raise PeopleImportError("The selected active person must have the curator role.")
        return registry
    except ValidationError as error:
        raise PeopleImportError(f"People CSV does not match the project schema: {error}") from error


def import_people_csv(project_root: str | Path, path: str | Path) -> PeopleRegistry:
    """Atomically replace current people configuration after complete CSV validation."""

    registry = read_people_csv(path)
    try:
        save_people_registry(project_root, registry)
    except PeopleRegistryError as error:
        raise PeopleImportError(str(error)) from error
    return registry


def main(argv: Iterable[str] | None = None) -> int:
    """Import one CSV for script interoperability with conventional exit status."""

    parser = argparse.ArgumentParser(description="Import HEVA project people from CSV.")
    parser.add_argument("project_root")
    parser.add_argument("csv_path")
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        registry = import_people_csv(args.project_root, args.csv_path)
    except PeopleImportError as error:
        parser.exit(1, f"People import failed: {error}\n")
    print(f"Imported {len(registry.people)} people.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
