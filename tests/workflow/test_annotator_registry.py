"""Tests for reusable project annotator collections."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from heva.workflow.annotator_registry import (
    AnnotatorRegistryError,
    activate_annotator,
    add_annotator,
    load_annotator_registry,
    remove_annotator,
    update_annotator,
)
from heva.workflow.document_metadata import AnnotatorMetadata


def test_add_update_and_activate_annotators(tmp_path: Path) -> None:
    first = add_annotator(tmp_path, AnnotatorMetadata(name=" First "))
    second = add_annotator(
        tmp_path,
        AnnotatorMetadata(name="Second", affiliation=" Lab "),
    )

    assert load_annotator_registry(tmp_path).active_annotator_id == second.annotator_id

    updated = update_annotator(
        tmp_path,
        first.annotator_id,
        AnnotatorMetadata(name="First Updated", email=" first@example.org "),
    )
    activate_annotator(tmp_path, first.annotator_id)
    registry = load_annotator_registry(tmp_path)

    assert updated.email == "first@example.org"
    assert registry.active().name == "First Updated"
    assert len(registry.annotators) == 2


def test_legacy_profile_migrates_once_with_stable_id(tmp_path: Path) -> None:
    legacy = tmp_path / "data" / "annotator.json"
    legacy.parent.mkdir()
    legacy.write_text(json.dumps({"name": "Legacy", "orcid": None}), encoding="utf-8")

    first = load_annotator_registry(tmp_path)
    second = load_annotator_registry(tmp_path)

    assert first.annotators[0].annotator_id == second.annotators[0].annotator_id
    assert (tmp_path / "data/annotators.json").is_file()


def test_blank_name_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(AnnotatorRegistryError, match="name"):
        add_annotator(tmp_path, AnnotatorMetadata(name="   "))


def test_remove_active_annotator_selects_remaining_profile(tmp_path: Path) -> None:
    first = add_annotator(tmp_path, AnnotatorMetadata(name="First"))
    second = add_annotator(tmp_path, AnnotatorMetadata(name="Second"))

    registry = remove_annotator(tmp_path, second.annotator_id)

    assert [item.annotator_id for item in registry.annotators] == [first.annotator_id]
    assert registry.active_annotator_id == first.annotator_id
