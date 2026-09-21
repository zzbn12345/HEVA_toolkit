"""Deterministic quality flags for extracted HEVA sentence records."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
from typing import Any, Iterable, Literal, Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field

from heva.curation.contract import validate_record
from heva.curation.project_registry import (
    DEFAULT_REGISTRY_PATH,
    ProjectRegistry,
    document_workspace_directory,
)


class QualityThresholds(BaseModel):
    """Configurable data thresholds, independent of any future interface."""

    model_config = ConfigDict(extra="forbid")

    minimum_characters: int = Field(default=15, ge=0)
    maximum_characters: int = Field(default=500, ge=1)
    maximum_tokens: int = Field(default=100, ge=1)


@dataclass(frozen=True)
class QualityFlag:
    code: str
    severity: Literal["warning", "error"]
    message: str
    evidence: dict[str, Any]


_SUSPICIOUS = re.compile(r"[\u0000-\u0008\u000B\u000C\u000E-\u001F\uFFFD]")


def assess_record(
    record: Mapping[str, Any],
    thresholds: QualityThresholds | None = None,
) -> tuple[QualityFlag, ...]:
    """Return flags without modifying, relabeling, or excluding the record."""

    config = thresholds or QualityThresholds()
    flags: list[QualityFlag] = []
    sentence = record.get("curated_sentence") or record.get("sentence")
    tokens = record.get("tokens")
    if not isinstance(sentence, str) or not sentence.strip():
        flags.append(
            QualityFlag("empty_sentence", "error", "Sentence text is empty.", {})
        )
    else:
        length = len(sentence.strip())
        if length < config.minimum_characters:
            flags.append(
                QualityFlag(
                    "unusually_short_sentence",
                    "warning",
                    "Sentence is shorter than the configured threshold.",
                    {"characters": length, "minimum": config.minimum_characters},
                )
            )
        if length > config.maximum_characters:
            flags.append(
                QualityFlag(
                    "unusually_long_sentence",
                    "warning",
                    "Sentence is longer than the configured threshold.",
                    {"characters": length, "maximum": config.maximum_characters},
                )
            )
        suspicious = sorted(set(_SUSPICIOUS.findall(sentence)))
        if suspicious:
            flags.append(
                QualityFlag(
                    "suspicious_character",
                    "warning",
                    "Sentence contains replacement or control characters.",
                    {"characters": suspicious},
                )
            )
        if sentence.strip()[-1] not in ".!?;:":
            flags.append(
                QualityFlag(
                    "likely_sentence_boundary_error",
                    "warning",
                    "Sentence has no terminal punctuation.",
                    {"ending": sentence.strip()[-10:]},
                )
            )
    if isinstance(tokens, list):
        word_tokens = [token for token in tokens if isinstance(token, str) and token.isalnum()]
        if len(word_tokens) <= 1:
            flags.append(
                QualityFlag(
                    "single_word_sentence",
                    "warning",
                    "Sentence contains at most one word token.",
                    {"word_tokens": len(word_tokens)},
                )
            )
        if len(tokens) > config.maximum_tokens:
            flags.append(
                QualityFlag(
                    "too_many_tokens",
                    "warning",
                    "Token count exceeds the configured threshold.",
                    {"tokens": len(tokens), "maximum": config.maximum_tokens},
                )
            )
    for issue in validate_record(record).issues:
        flags.append(
            QualityFlag(
                code=issue.code,
                severity="error",
                message=issue.message,
                evidence={"path": issue.path},
            )
        )
    provenance = record.get("mapping_provenance")
    entities = record.get("entities", [])
    if (
        isinstance(provenance, Mapping)
        and provenance.get("status") == "pending_review"
    ) or any(
        isinstance(entity, Mapping)
        and isinstance(entity.get("label"), str)
        and entity["label"].startswith("#")
        for entity in entities
    ):
        flags.append(
            QualityFlag(
                "unresolved_color_mapping",
                "warning",
                "Record uses a color mapping that still requires review.",
                {},
            )
        )
    return tuple(flags)


def build_quality_report(
    project_root: str | Path,
    document_id: str,
    *,
    thresholds: QualityThresholds | None = None,
) -> Path:
    """Write deterministic flags beside one package's annotations."""

    root = Path(project_root).resolve()
    registry = ProjectRegistry.model_validate_json(
        (root / DEFAULT_REGISTRY_PATH).read_text(encoding="utf-8")
    )
    matches = [entry for entry in registry.documents if entry.document_id == document_id]
    if not matches:
        raise ValueError(f"Document {document_id} is not registered.")
    package = root / matches[0].package_path
    records = json.loads((package / "annotations.json").read_text(encoding="utf-8"))
    findings = []
    for index, record in enumerate(records):
        flags = assess_record(record, thresholds)
        findings.append(
            {
                "record_index": index,
                "sentence_id": record.get("sentence_id"),
                "flags": [asdict(flag) for flag in flags],
            }
        )
    report = {
        "quality_report_version": "1.0",
        "document_id": document_id,
        "record_count": len(records),
        "flagged_record_count": sum(bool(item["flags"]) for item in findings),
        "findings": findings,
    }
    target = document_workspace_directory(root, document_id) / "quality-report.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(target)
    return target


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build HEVA sentence quality flags.")
    parser.add_argument("project_root", nargs="?", default=".")
    parser.add_argument("--document-id", required=True)
    args = parser.parse_args(list(argv) if argv is not None else None)
    target = build_quality_report(args.project_root, args.document_id)
    print(f"HEVA quality report written to {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
