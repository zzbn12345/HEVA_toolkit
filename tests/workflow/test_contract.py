"""Acceptance tests for the versioned HEVA extracted-record contract."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from heva.workflow.contract import (
    HEVA_LABELS,
    ContractParseError,
    load_records,
    validate_record,
)


ROOT = Path(__file__).parents[2]
DATA = ROOT / "data"


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


def test_schema_descriptor_describes_existing_and_versioned_fields() -> None:
    schema_path = ROOT / "schemas" / "heva-extracted-record.json"
    descriptor = json.loads(schema_path.read_text(encoding="utf-8"))

    assert [field["name"] for field in descriptor["fields"]] == [
        "sentence_id",
        "page",
        "sentence",
        "curated_sentence",
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


def test_curated_sentence_is_the_annotation_coordinate_space() -> None:
    record = representative_record()
    record["curated_sentence"] = "The historic harbor remains visible."
    record["tokens"] = ["The", "historic", "harbor", "remains", "visible", "."]
    record["entities"][0].update(start=4, end=19, text="historic harbor")

    result = validate_record(record)

    assert result.valid
    assert result.record is not None
    assert result.record.sentence == "The historic harbour remains visible."
    assert result.record.curated_sentence == "The historic harbor remains visible."
    assert result.record.to_dict()["curated_sentence"] == record["curated_sentence"]


def test_redundant_curated_sentence_is_omitted() -> None:
    record = representative_record()
    record["curated_sentence"] = record["sentence"]

    result = validate_record(record)

    assert result.valid
    assert result.record is not None
    assert "curated_sentence" not in result.record.to_dict()


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
        (
            lambda row: row.update(ner_tags=["O", "O", "O", "O", "O", "O"]),
            "bio_value_mismatch",
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
    assert error.value.line > 0
    assert error.value.column > 0


def test_all_extracted_examples_satisfy_the_contract() -> None:
    files = sorted(DATA.glob("*_extracted.json"))
    assert len(files) == 4

    loaded = [record for path in files for record in load_records(path)]

    assert len(loaded) == 82
    assert all(record.valid for record in loaded)
    assert {value for result in loaded for value in result.record.values} <= HEVA_LABELS


def run_validator(*arguments: str) -> subprocess.CompletedProcess[str]:
    """Run the validator through the same module entry point used by scripts."""

    return subprocess.run(
        [
            sys.executable,
            "-m",
            "heva.workflow.validate_records",
            *arguments,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_commandline_accepts_repository_examples() -> None:
    completed = run_validator("--all")

    assert completed.returncode == 0
    assert completed.stdout.count("VALID:") == 4
    assert completed.stderr == ""


def test_commandline_returns_one_for_semantic_issues(tmp_path: Path) -> None:
    record = representative_record()
    record["values"] = ["invented"]
    source = tmp_path / "invalid-record.json"
    source.write_text(json.dumps([record]), encoding="utf-8")

    completed = run_validator("--file", str(source))

    assert completed.returncode == 1
    assert "INVALID:" in completed.stdout
    assert "unknown_label $.values[0]" in completed.stdout
    assert completed.stderr == ""


def test_commandline_flags_bio_and_categorical_disagreement(tmp_path: Path) -> None:
    record = representative_record()
    record["ner_tags"] = ["O", "O", "O", "O", "O", "O"]
    source = tmp_path / "contradictory-bio.json"
    source.write_text(json.dumps([record]), encoding="utf-8")

    completed = run_validator("--file", str(source))

    assert completed.returncode == 1
    assert "bio_value_mismatch $.ner_tags" in completed.stdout


def test_commandline_returns_two_for_malformed_json(tmp_path: Path) -> None:
    source = tmp_path / "malformed.json"
    source.write_text('[{"sentence_id": 1,}]', encoding="utf-8")

    completed = run_validator("--file", str(source))

    assert completed.returncode == 2
    assert "PARSE ERROR:" in completed.stdout
    assert "line 1" in completed.stdout
    assert completed.stderr == ""


def test_commandline_reports_missing_file_without_traceback(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"

    completed = run_validator("--file", str(missing))

    assert completed.returncode == 2
    assert "INPUT ERROR:" in completed.stdout
    assert str(missing) in completed.stdout
    assert "Traceback" not in completed.stdout + completed.stderr
