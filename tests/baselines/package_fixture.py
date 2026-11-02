"""A synthetic HEVA Data Package, so baseline tests never depend on real annotations."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from heva.baselines.labels import VALUES

PACKAGE_RECORDS = 96
NOUNS = ["warehouse", "market", "harbour", "church", "garden", "bastion", "quay", "gallery"]


def package_records(count: int = PACKAGE_RECORDS) -> list[dict]:
    """Records of two documents; every value occurs, and every fourth record has two."""
    records = []
    for index in range(count):
        values = [VALUES[index % len(VALUES)]]
        if index % 4 == 0:
            values.append(VALUES[(index + 3) % len(VALUES)])
        tokens = ["Record", str(index), "describes", "the"]
        tags = ["O", "O", "O", "O"]
        entities = []
        for value in values:
            words = ["old", NOUNS[(index + len(entities)) % len(NOUNS)]]
            if entities:
                tokens.append("and")
                tags.append("O")
            start = len(" ".join(tokens)) + 1
            tokens.extend(words)
            tags.extend([f"B-{value}", f"I-{value}"])
            text = " ".join(words)
            entities.append({"start": start, "end": start + len(text), "text": text,
                             "label": value, "color": "#FF40FF"})
        tokens.append(".")
        tags.append("O")
        records.append({
            "document_id": f"HEVA-TEST-{index % 2 + 1:03d}",
            "sentence_id": index // 2 + 1,
            "page": 1,
            "sentence": " ".join(tokens),
            "curated_sentence": None,
            "values": values,
            "tokens": tokens,
            "entities": entities,
            "ner_tags": tags,
            "schema_version": "1.0",
        })
    return records


def write_package_json(directory: Path, records: list[dict] | None = None) -> Path:
    records = package_records() if records is None else records
    documents = {}
    for record in records:
        documents.setdefault(record["document_id"], []).append(
            {key: value for key, value in record.items() if key != "document_id"}
        )
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "heva-annotations.json"
    path.write_text(json.dumps({"documents": [
        {"document_id": document_id, "records": document_records}
        for document_id, document_records in documents.items()
    ]}), encoding="utf-8")
    return path


def write_package_csv(directory: Path, records: list[dict] | None = None) -> Path:
    """The flat CSV the toolkit releases, with JSON-encoded list columns."""
    records = package_records() if records is None else records
    columns = ["document_id", "sentence_id", "page", "sentence", "curated_sentence",
               "values", "tokens", "entities", "ner_tags", "schema_version"]
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "heva-annotations.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for record in records:
            writer.writerow({
                column: json.dumps(record[column])
                if column in ("values", "tokens", "entities", "ner_tags")
                else (record[column] if record[column] is not None else "")
                for column in columns
            })
    return path
