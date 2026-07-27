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

from pydantic import BaseModel, ConfigDict, StrictInt, StrictStr, ValidationError


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


class MappingProvenanceInput(BaseModel):
    """Strict input shape for mapping provenance before semantic checks."""

    model_config = ConfigDict(extra="forbid", strict=True)

    method: StrictStr
    status: StrictStr
    config_id: StrictStr | None = None


class EntityInput(BaseModel):
    """Strict input shape for one entity span before semantic checks."""

    model_config = ConfigDict(extra="forbid", strict=True)

    start: StrictInt
    end: StrictInt
    text: StrictStr
    label: StrictStr
    color: StrictStr | None = None


class RecordInput(BaseModel):
    """Strict input shape for a HEVA record before semantic checks."""

    model_config = ConfigDict(extra="forbid", strict=True)

    sentence_id: StrictInt
    page: StrictInt
    sentence: StrictStr
    tokens: list[StrictStr]
    values: list[StrictStr]
    entities: list[EntityInput]
    ner_tags: list[StrictStr]
    schema_version: StrictStr = LEGACY_SCHEMA_VERSION
    mapping_provenance: MappingProvenanceInput | None = None


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


def _path_from_loc(loc: tuple[Any, ...]) -> str:
    """Convert pydantic error locations to JSON-style paths."""

    path = "$"
    for part in loc:
        if isinstance(part, int):
            path += f"[{part}]"
        else:
            path += f".{part}"
    return path


def _parse_structural_record(value: Any) -> tuple[RecordInput | None, list[ContractIssue]]:
    """Parse strict structure with pydantic and map errors to stable contract issues."""

    if not isinstance(value, Mapping):
        return None, [_issue("invalid_type", "$", "Expected a HEVA record object.")]

    try:
        return RecordInput.model_validate(value), []
    except ValidationError as error:
        issues: list[ContractIssue] = []
        for item in error.errors():
            issues.append(
                _issue(
                    "invalid_type",
                    _path_from_loc(item.get("loc", ())),
                    item.get("msg", "Invalid type."),
                )
            )
        return None, issues


def _parse_mapping(
    value: MappingProvenanceInput | None, issues: list[ContractIssue]
) -> MappingProvenance | None:
    if value is None:
        return None
    if not value.method:
        issues.append(_issue("invalid_type", "$.mapping_provenance.method", "Expected text."))
    if value.status not in {"pending_review", "approved"}:
        issues.append(
            _issue(
                "invalid_mapping_status",
                "$.mapping_provenance.status",
                "Expected pending_review or approved.",
            )
        )
    return MappingProvenance(
        method=value.method,
        status=value.status,
        config_id=value.config_id,
    )


def _parse_entities(
    value: Sequence[EntityInput], sentence: str, issues: list[ContractIssue]
) -> tuple[Entity, ...]:
    entities: list[Entity] = []
    for index, candidate in enumerate(value):
        path = f"$.entities[{index}]"
        if candidate.label not in HEVA_LABELS:
            issues.append(
                _issue("unknown_label", f"{path}.label", f"Unknown HEVA label: {candidate.label}")
            )
        if candidate.color is not None and not HEX_COLOR.fullmatch(candidate.color):
            issues.append(
                _issue("invalid_color", f"{path}.color", "Expected a six-digit #RRGGBB color.")
            )
        if candidate.start < 0 or candidate.end <= candidate.start or candidate.end > len(sentence):
            issues.append(_issue("invalid_entity_offset", path, "Entity offsets are out of range."))
        elif sentence[candidate.start : candidate.end] != candidate.text:
            issues.append(
                _issue(
                    "entity_text_mismatch",
                    path,
                    "Entity text does not equal the sentence slice at start:end.",
                )
            )
        entities.append(
            Entity(
                start=candidate.start,
                end=candidate.end,
                text=candidate.text,
                label=candidate.label,
                color=candidate.color,
            )
        )
    return tuple(entities)


def _validate_bio(tags: Sequence[str], issues: list[ContractIssue]) -> set[str]:
    """Validate BIO syntax and return the controlled labels represented by the tags."""

    previous_prefix = "O"
    previous_label: str | None = None
    represented_labels: set[str] = set()
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
        else:
            represented_labels.add(label)
            if prefix == "I" and (
                previous_prefix not in {"B", "I"} or previous_label != label
            ):
                issues.append(
                    _issue(
                        "invalid_bio_transition",
                        path,
                        f"{tag} must follow B-{label} or I-{label}.",
                    )
                )
        previous_prefix, previous_label = prefix, label
    return represented_labels


def validate_record(value: Any) -> ValidationResult:
    """Validate one decoded JSON value and return typed data plus stable issues."""

    parsed, structural_issues = _parse_structural_record(value)
    if parsed is None:
        return ValidationResult(record=None, issues=tuple(structural_issues))

    issues: list[ContractIssue] = []
    sentence_id = parsed.sentence_id
    page = parsed.page
    sentence = parsed.sentence
    tokens = tuple(parsed.tokens)
    values = tuple(parsed.values)
    ner_tags = tuple(parsed.ner_tags)
    entities = _parse_entities(parsed.entities, sentence, issues)
    schema_version = parsed.schema_version
    if sentence_id < 1:
        issues.append(_issue("invalid_type", "$.sentence_id", "Expected an integer greater than zero."))
    if page < 1:
        issues.append(_issue("invalid_type", "$.page", "Expected an integer greater than zero."))
    if not isinstance(schema_version, str) or schema_version not in {
        LEGACY_SCHEMA_VERSION,
        CURRENT_SCHEMA_VERSION,
    }:
        issues.append(
            _issue("unsupported_schema_version", "$.schema_version", "Unsupported schema version.")
        )
        schema_version = LEGACY_SCHEMA_VERSION
    mapping = _parse_mapping(parsed.mapping_provenance, issues)

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
    bio_labels = _validate_bio(ner_tags, issues)
    entity_labels = {entity.label for entity in entities}
    if set(values) != entity_labels:
        issues.append(
            _issue(
                "value_entity_mismatch",
                "$.values",
                "Values must equal the unique labels represented by entities.",
            )
        )
    if set(values) != bio_labels:
        issues.append(
            _issue(
                "bio_value_mismatch",
                "$.ner_tags",
                "BIO tags and categorical values must represent the same HEVA labels.",
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
