"""Acceptance tests for the versioned HEVA extracted-record contract."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from frictionless import Schema

from src.heva_contract import (
    HEVA_LABELS,
    ContractParseError,
    load_records,
    validate_record,
)


DATA = Path(__file__).parents[1] / "data"


def representative_record() -> dict[str, object]:
    return {
        "sentence_id": 1,
        "page": 1,
        "sentence": "The historic harbour remains visible.",
        "tokens": ["The", "historic", "harbour", "remains", "visible", "."],
        "values": ["historic"],
        "entities": [
            {
                "start": 4,
                "end": 20,
                "text": "historic harbour",
                "label": "historic",
                "color": "#FF40FF",
            }
        ],
        "ner_tags": ["O", "B-historic", "I-historic", "O", "O", "O"],
        "schema_version": "1.0",
        "mapping_provenance": {
            "method": "human_reviewed",
            "status": "approved",
            "config_id": "galle-p127-colors",
        },
    }


def test_frictionless_schema_describes_existing_and_versioned_fields() -> None:
    schema_path = Path(__file__).parents[1] / "schemas" / "heva-extracted-record.json"
    schema = Schema.from_descriptor(json.loads(schema_path.read_text(encoding="utf-8")))

    assert schema.field_names == [
        "sentence_id",
        "page",
        "sentence",
        "tokens",
        "values",
        "entities",
        "ner_tags",
        "schema_version",
        "mapping_provenance",
    ]


def test_valid_record_preserves_color_and_mapping_provenance() -> None:
    result = validate_record(representative_record())

    assert result.valid
    assert result.record is not None
    assert result.record.entities[0].color == "#FF40FF"
    assert result.record.mapping_provenance is not None
    assert result.record.mapping_provenance.method == "human_reviewed"
    assert result.record.to_dict()["mapping_provenance"]["status"] == "approved"


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        (lambda row: row["entities"][0].update(start=5), "entity_text_mismatch"),
        (lambda row: row["entities"][0].update(label="invented"), "unknown_label"),
        (lambda row: row.update(values=["invented"]), "unknown_label"),
        (lambda row: row.update(ner_tags=["O"]), "token_tag_length_mismatch"),
        (
            lambda row: row.update(
                ner_tags=["O", "I-historic", "I-historic", "O", "O", "O"]
            ),
            "invalid_bio_transition",
        ),
    ],
)
def test_semantic_failures_have_stable_codes(mutation, expected_code: str) -> None:
    row = representative_record()
    mutation(row)

    result = validate_record(row)

    assert not result.valid
    assert expected_code in {issue.code for issue in result.issues}
    assert all(issue.path.startswith("$") for issue in result.issues)


def test_json_parse_failure_is_distinct_and_location_aware() -> None:
    malformed = DATA / "json_word_P2_oracle.json"

    with pytest.raises(ContractParseError) as error:
        load_records(malformed)

    assert error.value.code == "invalid_json"
    assert error.value.line == 202
    assert error.value.column == 8


def test_all_extracted_examples_satisfy_the_contract() -> None:
    files = sorted(DATA.glob("*_extracted.json"))
    assert len(files) == 4

    loaded = [record for path in files for record in load_records(path)]

    assert len(loaded) == 82
    assert all(record.valid for record in loaded)
    assert {value for result in loaded for value in result.record.values} <= HEVA_LABELS
