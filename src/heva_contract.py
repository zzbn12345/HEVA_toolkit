"""Typed, versioned validation contract for extracted HEVA sentence records.

The module deliberately does not write files or change annotations.  It converts an
existing extractor record into immutable typed values and reports structural and semantic
problems with stable codes and JSON-style paths.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence


HEVA_LABELS = frozenset(
    {
        "social",
        "economic",
        "political",
        "historic",
        "aesthetical",
        "scientific",
        "age",
        "ecological",
    }
)
CURRENT_SCHEMA_VERSION = "1.0"
LEGACY_SCHEMA_VERSION = "0.1"
HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


@dataclass(frozen=True)
class ContractIssue:
    """One localizable violation of the canonical record contract."""

    code: str
    path: str
    message: str


@dataclass(frozen=True)
class MappingProvenance:
    """Human or automatic origin of a document's color-to-label mapping."""

    method: str
    status: str
    config_id: str | None = None


@dataclass(frozen=True)
class Entity:
    """One labeled character span in a sentence."""

    start: int
    end: int
    text: str
    label: str
    color: str | None = None


@dataclass(frozen=True)
class CanonicalRecord:
    """Immutable typed representation of one canonical HEVA sentence record."""

    sentence_id: int
    page: int
    sentence: str
    tokens: tuple[str, ...]
    values: tuple[str, ...]
    entities: tuple[Entity, ...]
    ner_tags: tuple[str, ...]
    schema_version: str = LEGACY_SCHEMA_VERSION
    mapping_provenance: MappingProvenance | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable record without discarding optional evidence."""

        descriptor = asdict(self)
        descriptor["tokens"] = list(self.tokens)
        descriptor["values"] = list(self.values)
        descriptor["entities"] = [asdict(entity) for entity in self.entities]
        descriptor["ner_tags"] = list(self.ner_tags)
        if self.mapping_provenance is None:
            descriptor.pop("mapping_provenance")
        for entity in descriptor["entities"]:
            if entity["color"] is None:
                entity.pop("color")
        return descriptor


@dataclass(frozen=True)
class ValidationResult:
    """Typed record plus every issue found while validating its input."""

    record: CanonicalRecord | None
    issues: tuple[ContractIssue, ...]

    @property
    def valid(self) -> bool:
        """Return true only when a typed record exists and no issue was reported."""

        return self.record is not None and not self.issues


class ContractParseError(ValueError):
    """Raised when an input file cannot be parsed as JSON records."""

    code = "invalid_json"

    def __init__(self, path: Path, error: json.JSONDecodeError):
        self.path = path
        self.line = error.lineno
        self.column = error.colno
        super().__init__(
            f"{path}: invalid JSON at line {self.line}, column {self.column}: {error.msg}"
        )


def _issue(code: str, path: str, message: str) -> ContractIssue:
    return ContractIssue(code=code, path=path, message=message)


def _list_of_strings(value: Any, path: str, issues: list[ContractIssue]) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        issues.append(_issue("invalid_type", path, "Expected an array of strings."))
        return ()
    return tuple(value)


def _positive_integer(value: Any, path: str, issues: list[ContractIssue]) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        issues.append(_issue("invalid_type", path, "Expected an integer greater than zero."))
        return 0
    return value


def _parse_mapping(value: Any, issues: list[ContractIssue]) -> MappingProvenance | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        issues.append(
            _issue("invalid_type", "$.mapping_provenance", "Expected a mapping object.")
        )
        return None
    method = value.get("method")
    status = value.get("status")
    config_id = value.get("config_id")
    if not isinstance(method, str) or not method:
        issues.append(_issue("invalid_type", "$.mapping_provenance.method", "Expected text."))
    if status not in {"pending_review", "approved"}:
        issues.append(
            _issue(
                "invalid_mapping_status",
                "$.mapping_provenance.status",
                "Expected pending_review or approved.",
            )
        )
    if config_id is not None and not isinstance(config_id, str):
        issues.append(_issue("invalid_type", "$.mapping_provenance.config_id", "Expected text."))
    if not isinstance(method, str) or not method or not isinstance(status, str):
        return None
    return MappingProvenance(method=method, status=status, config_id=config_id)


def _parse_entities(
    value: Any, sentence: str, issues: list[ContractIssue]
) -> tuple[Entity, ...]:
    if not isinstance(value, list):
        issues.append(_issue("invalid_type", "$.entities", "Expected an array of entities."))
        return ()
    entities: list[Entity] = []
    for index, candidate in enumerate(value):
        path = f"$.entities[{index}]"
        if not isinstance(candidate, Mapping):
            issues.append(_issue("invalid_type", path, "Expected an entity object."))
            continue
        start = candidate.get("start")
        end = candidate.get("end")
        text = candidate.get("text")
        label = candidate.get("label")
        color = candidate.get("color")
        if isinstance(start, bool) or not isinstance(start, int):
            issues.append(_issue("invalid_type", f"{path}.start", "Expected an integer."))
        if isinstance(end, bool) or not isinstance(end, int):
            issues.append(_issue("invalid_type", f"{path}.end", "Expected an integer."))
        if not isinstance(text, str):
            issues.append(_issue("invalid_type", f"{path}.text", "Expected text."))
        if not isinstance(label, str):
            issues.append(_issue("invalid_type", f"{path}.label", "Expected text."))
        elif label not in HEVA_LABELS:
            issues.append(_issue("unknown_label", f"{path}.label", f"Unknown HEVA label: {label}"))
        if color is not None and (not isinstance(color, str) or not HEX_COLOR.fullmatch(color)):
            issues.append(
                _issue("invalid_color", f"{path}.color", "Expected a six-digit #RRGGBB color.")
            )
        if not all(
            [
                isinstance(start, int) and not isinstance(start, bool),
                isinstance(end, int) and not isinstance(end, bool),
                isinstance(text, str),
                isinstance(label, str),
            ]
        ):
            continue
        if start < 0 or end <= start or end > len(sentence):
            issues.append(_issue("invalid_entity_offset", path, "Entity offsets are out of range."))
        elif sentence[start:end] != text:
            issues.append(
                _issue(
                    "entity_text_mismatch",
                    path,
                    "Entity text does not equal the sentence slice at start:end.",
                )
            )
        entities.append(Entity(start=start, end=end, text=text, label=label, color=color))
    return tuple(entities)


def _validate_bio(tags: Sequence[str], issues: list[ContractIssue]) -> None:
    previous_prefix = "O"
    previous_label: str | None = None
    for index, tag in enumerate(tags):
        path = f"$.ner_tags[{index}]"
        if tag == "O":
            previous_prefix, previous_label = "O", None
            continue
        if "-" not in tag:
            issues.append(_issue("invalid_bio_tag", path, f"Invalid BIO tag: {tag}"))
            previous_prefix, previous_label = "O", None
            continue
        prefix, label = tag.split("-", 1)
        if prefix not in {"B", "I"} or label not in HEVA_LABELS:
            issues.append(_issue("invalid_bio_tag", path, f"Invalid BIO tag: {tag}"))
        elif prefix == "I" and (previous_prefix not in {"B", "I"} or previous_label != label):
            issues.append(
                _issue(
                    "invalid_bio_transition",
                    path,
                    f"{tag} must follow B-{label} or I-{label}.",
                )
            )
        previous_prefix, previous_label = prefix, label


def validate_record(value: Any) -> ValidationResult:
    """Validate one decoded JSON value and return typed data plus stable issues."""

    if not isinstance(value, Mapping):
        return ValidationResult(
            record=None,
            issues=(_issue("invalid_type", "$", "Expected a HEVA record object."),),
        )
    issues: list[ContractIssue] = []
    sentence_id = _positive_integer(value.get("sentence_id"), "$.sentence_id", issues)
    page = _positive_integer(value.get("page"), "$.page", issues)
    sentence_value = value.get("sentence")
    if not isinstance(sentence_value, str):
        issues.append(_issue("invalid_type", "$.sentence", "Expected text."))
        sentence = ""
    else:
        sentence = sentence_value
    tokens = _list_of_strings(value.get("tokens"), "$.tokens", issues)
    values = _list_of_strings(value.get("values"), "$.values", issues)
    ner_tags = _list_of_strings(value.get("ner_tags"), "$.ner_tags", issues)
    entities = _parse_entities(value.get("entities"), sentence, issues)
    schema_version = value.get("schema_version", LEGACY_SCHEMA_VERSION)
    if not isinstance(schema_version, str) or schema_version not in {
        LEGACY_SCHEMA_VERSION,
        CURRENT_SCHEMA_VERSION,
    }:
        issues.append(
            _issue("unsupported_schema_version", "$.schema_version", "Unsupported schema version.")
        )
        schema_version = LEGACY_SCHEMA_VERSION
    mapping = _parse_mapping(value.get("mapping_provenance"), issues)

    for index, label in enumerate(values):
        if label not in HEVA_LABELS:
            issues.append(_issue("unknown_label", f"$.values[{index}]", f"Unknown HEVA label: {label}"))
    if len(tokens) != len(ner_tags):
        issues.append(
            _issue(
                "token_tag_length_mismatch",
                "$.ner_tags",
                f"Found {len(tokens)} tokens and {len(ner_tags)} BIO tags.",
            )
        )
    _validate_bio(ner_tags, issues)
    entity_labels = {entity.label for entity in entities}
    if set(values) != entity_labels:
        issues.append(
            _issue(
                "value_entity_mismatch",
                "$.values",
                "Values must equal the unique labels represented by entities.",
            )
        )

    record = CanonicalRecord(
        sentence_id=sentence_id,
        page=page,
        sentence=sentence,
        tokens=tokens,
        values=values,
        entities=entities,
        ner_tags=ner_tags,
        schema_version=schema_version,
        mapping_provenance=mapping,
    )
    return ValidationResult(record=record, issues=tuple(issues))


def load_records(path: str | Path) -> list[ValidationResult]:
    """Load a JSON array and validate every HEVA record without modifying the source."""

    source = Path(path)
    try:
        decoded = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ContractParseError(source, error) from error
    if not isinstance(decoded, list):
        return [
            ValidationResult(
                record=None,
                issues=(_issue("invalid_document", "$", "Expected an array of HEVA records."),),
            )
        ]
    return [validate_record(value) for value in decoded]
