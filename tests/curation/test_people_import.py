"""Acceptance tests for the authoritative people CSV adapter."""

from __future__ import annotations

from pathlib import Path

import pytest

from heva.curation.people_import import PeopleImportError, import_people_csv, main
from heva.curation.people_registry import load_people_registry


FIXTURE = Path(__file__).parents[1] / "fixtures" / "people.csv"


def test_people_csv_imports_roles_and_exact_active_curator(tmp_path: Path) -> None:
    imported = import_people_csv(tmp_path, FIXTURE)
    restored = load_people_registry(tmp_path)

    assert restored == imported
    assert len(imported.people) == 3
    assert imported.active_curator().name == "Example Curator"
    assert imported.people[0].roles == ["annotator"]


def test_invalid_people_csv_does_not_partially_replace_registry(tmp_path: Path) -> None:
    original = import_people_csv(tmp_path, FIXTURE)
    invalid = tmp_path / "invalid-people.csv"
    invalid.write_text(
        "person_id,name,roles,affiliation,email,orcid,active_curator\n"
        "PERSON-ONE,One,curator,,,,true\n"
        "PERSON-TWO,Two,data_owner,,,,true\n",
        encoding="utf-8",
    )

    with pytest.raises(PeopleImportError, match="at most one active curator"):
        import_people_csv(tmp_path, invalid)

    assert load_people_registry(tmp_path) == original


def test_people_csv_adapter_is_callable_from_command_line_contract(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main([str(tmp_path), str(FIXTURE)]) == 0
    assert capsys.readouterr().out == "Imported 3 people.\n"
