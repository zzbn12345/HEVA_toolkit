"""Reproducible accuracy and performance scoring for curator-approved HEVA cases."""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
from typing import Any, Iterable, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from heva.workflow.contract import validate_record


EVALUATION_VERSION = "1.0"
REQUIRED_CATEGORIES = frozenset(
    {
        "structured_annotations",
        "flattened_highlights",
        "colored_fonts",
        "mixed_conventions",
        "decorations",
        "malformed_pdf",
        "unsupported_scan",
    }
)


class EvaluationCase(BaseModel):
    """One approved input/result pair in an evaluation corpus."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    category: Literal[
        "structured_annotations",
        "flattened_highlights",
        "colored_fonts",
        "mixed_conventions",
        "decorations",
        "malformed_pdf",
        "unsupported_scan",
    ]
    source_reference: str
    expected_path: str | None = None
    observed_path: str
    expected_support: bool = True
    expected_error_code: str | None = None


class EvaluationManifest(BaseModel):
    """Human approval and membership for a versioned evaluation corpus."""

    model_config = ConfigDict(extra="forbid")

    evaluation_version: str = EVALUATION_VERSION
    approved_by: str = Field(min_length=1)
    approved_at: date
    cases: list[EvaluationCase] = Field(min_length=1)


class RatioMetric(BaseModel):
    """A named numerator/denominator ratio with an explicit empty-set result."""

    model_config = ConfigDict(extra="forbid")

    numerator: int
    denominator: int
    value: float | None


class CaseEvaluation(BaseModel):
    """Accuracy, correction, and resource evidence for one corpus case."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    category: str
    passed: bool
    expected_support: bool
    observed_error_code: str | None = None
    record_precision: RatioMetric | None = None
    record_recall: RatioMetric | None = None
    span_precision: RatioMetric | None = None
    span_recall: RatioMetric | None = None
    label_accuracy: RatioMetric | None = None
    failures_by_label: dict[str, int] = Field(default_factory=dict)
    correction_rate: RatioMetric | None = None
    abstention_rate: RatioMetric | None = None
    time_saved_seconds: float | None = None
    duration_seconds: float | None = None
    peak_memory_mb: float | None = None
    issues: list[str] = Field(default_factory=list)


class EvaluationReport(BaseModel):
    """Machine-readable evidence report that never combines unlike metrics."""

    model_config = ConfigDict(extra="forbid")

    evaluation_version: str = EVALUATION_VERSION
    corpus_approved_by: str
    corpus_approved_at: date
    coverage_complete: bool
    missing_categories: list[str]
    passed: bool
    cases: list[CaseEvaluation]


class EvaluationError(ValueError):
    """Raised when evaluation evidence is missing, unsafe, or malformed."""


def _ratio(numerator: int, denominator: int) -> RatioMetric:
    return RatioMetric(
        numerator=numerator,
        denominator=denominator,
        value=(numerator / denominator if denominator else None),
    )


def _safe_relative(root: Path, value: str) -> Path:
    path = (root / value).resolve()
    try:
        path.relative_to(root)
    except ValueError as error:
        raise EvaluationError(f"Evaluation path leaves the corpus: {value}") from error
    return path


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EvaluationError(f"Cannot read evaluation evidence {path}: {error}") from error


def _records(value: Any, context: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise EvaluationError(f"{context} must contain a JSON array of HEVA records.")
    records: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        result = validate_record(item)
        if not result.valid or result.record is None:
            codes = ", ".join(issue.code for issue in result.issues)
            raise EvaluationError(f"{context}[{index}] is invalid: {codes}")
        records.append(result.record.to_dict())
    return records


def _record_key(record: dict[str, Any]) -> str:
    return json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _span_key(record: dict[str, Any], entity: dict[str, Any]) -> tuple[Any, ...]:
    return (
        record["sentence_id"],
        record["page"],
        entity["start"],
        entity["end"],
        entity["text"],
    )


def _supported_case(
    case: EvaluationCase,
    expected: list[dict[str, Any]],
    observed: dict[str, Any],
) -> CaseEvaluation:
    observed_records = _records(observed.get("records"), f"{case.case_id}.observed.records")
    expected_records = {_record_key(record) for record in expected}
    actual_records = {_record_key(record) for record in observed_records}
    record_matches = len(expected_records & actual_records)

    expected_spans = {
        _span_key(record, entity): entity["label"]
        for record in expected
        for entity in record["entities"]
    }
    actual_spans = {
        _span_key(record, entity): entity["label"]
        for record in observed_records
        for entity in record["entities"]
    }
    matched_spans = set(expected_spans) & set(actual_spans)
    correct_labels = sum(
        expected_spans[key] == actual_spans[key] for key in matched_spans
    )
    failures: dict[str, int] = {}
    for key, label in expected_spans.items():
        if key not in actual_spans or actual_spans[key] != label:
            failures[label] = failures.get(label, 0) + 1

    proposals = int(observed.get("ollama_proposals", 0))
    corrections = int(observed.get("curator_corrections", 0))
    abstentions = int(observed.get("ollama_abstentions", 0))
    issues = []
    if record_matches != len(expected_records) or record_matches != len(actual_records):
        issues.append("Observed records do not exactly match the approved gold records.")
    if correct_labels != len(matched_spans):
        issues.append("One or more matched spans have an incorrect controlled label.")
    passed = not issues
    return CaseEvaluation(
        case_id=case.case_id,
        category=case.category,
        passed=passed,
        expected_support=True,
        record_precision=_ratio(record_matches, len(actual_records)),
        record_recall=_ratio(record_matches, len(expected_records)),
        span_precision=_ratio(len(matched_spans), len(actual_spans)),
        span_recall=_ratio(len(matched_spans), len(expected_spans)),
        label_accuracy=_ratio(correct_labels, len(matched_spans)),
        failures_by_label=failures,
        correction_rate=_ratio(corrections, proposals) if proposals else None,
        abstention_rate=_ratio(abstentions, proposals + abstentions)
        if proposals + abstentions
        else None,
        time_saved_seconds=observed.get("time_saved_seconds"),
        duration_seconds=observed.get("duration_seconds"),
        peak_memory_mb=observed.get("peak_memory_mb"),
        issues=issues,
    )


def evaluate_manifest(manifest_path: str | Path) -> EvaluationReport:
    """Score approved observed results and require all EDD input categories."""

    path = Path(manifest_path).resolve()
    try:
        manifest = EvaluationManifest.model_validate(_read_json(path))
    except ValidationError as error:
        raise EvaluationError(f"Evaluation manifest is invalid: {error}") from error
    root = path.parent
    categories = {case.category for case in manifest.cases}
    missing = sorted(REQUIRED_CATEGORIES - categories)
    results: list[CaseEvaluation] = []
    for case in sorted(manifest.cases, key=lambda item: item.case_id):
        observed = _read_json(_safe_relative(root, case.observed_path))
        if not isinstance(observed, dict):
            raise EvaluationError(f"{case.case_id} observed evidence must be a JSON object.")
        if not case.expected_support:
            observed_error = observed.get("error_code")
            passed = bool(
                case.expected_error_code
                and observed_error == case.expected_error_code
            )
            results.append(
                CaseEvaluation(
                    case_id=case.case_id,
                    category=case.category,
                    passed=passed,
                    expected_support=False,
                    observed_error_code=observed_error,
                    duration_seconds=observed.get("duration_seconds"),
                    peak_memory_mb=observed.get("peak_memory_mb"),
                    issues=[] if passed else ["Expected unsupported-input error was not observed."],
                )
            )
            continue
        if not case.expected_path:
            raise EvaluationError(f"{case.case_id} requires expected_path.")
        expected = _records(
            _read_json(_safe_relative(root, case.expected_path)),
            f"{case.case_id}.expected",
        )
        results.append(_supported_case(case, expected, observed))
    coverage_complete = not missing
    return EvaluationReport(
        corpus_approved_by=manifest.approved_by,
        corpus_approved_at=manifest.approved_at,
        coverage_complete=coverage_complete,
        missing_categories=missing,
        passed=coverage_complete and all(case.passed for case in results),
        cases=results,
    )


def main(argv: Iterable[str] | None = None) -> int:
    """Run the evidence scorer from scripts or a command line."""

    parser = argparse.ArgumentParser(description="Score approved HEVA evaluation evidence.")
    parser.add_argument("manifest")
    parser.add_argument("--report")
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        report = evaluate_manifest(args.manifest)
    except EvaluationError as error:
        print(f"EVALUATION ERROR: {error}")
        return 1
    rendered = json.dumps(
        report.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    if args.report:
        target = Path(args.report)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
