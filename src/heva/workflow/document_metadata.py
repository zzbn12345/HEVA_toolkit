"""Document provenance, citation, annotator, and rights metadata for HEVA.

Typical use:

1. Load a reusable annotator profile with :func:`load_annotator`.
2. Construct :class:`PackageMetadata` for a registered document.
3. Check it with :func:`validate_review_readiness`.
4. Persist it with :func:`save_package_metadata`.

See ``docs/DOCUMENT_METADATA.md`` for complete examples and field guidance.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import json
from pathlib import Path
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    ValidationError,
    field_validator,
)

from heva.workflow.contract import HEX_COLOR, HEVA_LABELS
from heva.workflow.project_registry import DEFAULT_REGISTRY_PATH, ProjectRegistry


METADATA_VERSION = "1.0"


class SourceMetadata(BaseModel):
    """Bibliographic provenance for the document being annotated."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    creators: list[str] = Field(default_factory=list)
    citation: str | None = None
    reference: str | None = None
    not_findable_reason: str | None = None
    human_confirmed: StrictBool = False
    confirmed_by: str | None = None
    confirmed_at: datetime | None = None


class AnnotatorMetadata(BaseModel):
    """Identity of the person responsible for the HEVA annotations."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(
        default=None,
        min_length=1,
        title="Annotator name",
        description="Person responsible for reviewing these annotations.",
    )
    affiliation: str | None = Field(
        default=None,
        title="Affiliation",
        description="Organization or research group associated with the annotator.",
    )
    email: str | None = Field(
        default=None,
        title="Email",
        description="Optional contact address.",
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
        json_schema_extra={"format": "email"},
    )
    orcid: str | None = Field(
        default=None,
        title="ORCID",
        description="Optional persistent researcher identifier.",
        examples=["0000-0002-1825-0097"],
        pattern=r"^\d{4}-\d{4}-\d{4}-[\dX]{4}$",
    )

    @field_validator("name", "affiliation", "email", "orcid", mode="before")
    @classmethod
    def normalize_optional_text(cls, value):
        """Trim form input and treat blank fields as absent."""

        if isinstance(value, str):
            return value.strip() or None
        return value


class RightsMetadata(BaseModel):
    """Per-document access, authorization, and distribution decisions."""

    model_config = ConfigDict(extra="forbid")

    access_level: Literal["public", "restricted", "private"] | None = None
    authorization_status: Literal["authorized", "pending", "unknown", "denied"] | None = None
    authorization_date: date | None = None
    authorized_by: str | None = None
    evidence_reference: str | None = None
    source_distribution_allowed: StrictBool | None = None
    extracted_text_distribution_allowed: StrictBool | None = None
    annotation_distribution_allowed: StrictBool | None = None
    license: str | None = None
    embargo_until: date | None = None


class ReviewMetadata(BaseModel):
    """Human review state for the extracted annotation resource."""

    model_config = ConfigDict(extra="forbid")

    all_sentences_require_approval: StrictBool = True
    completed: StrictBool = False
    reviewed_at: datetime | None = None


class AnnotationProcessMetadata(BaseModel):
    """Provenance for the process that produced the HEVA annotations."""

    model_config = ConfigDict(extra="forbid")

    method: Literal["manual", "automatic", "hybrid"] | None = None
    extractor: str | None = None
    extractor_version: str | None = None
    performed_at: datetime | None = None
    review: ReviewMetadata = Field(default_factory=ReviewMetadata)


class ColorMappingMetadata(BaseModel):
    """One observed document color and its supervised HEVA interpretation."""

    model_config = ConfigDict(extra="forbid")

    hex: str
    color_name: str | None = None
    text_color: Literal["#000000", "#FFFFFF"] | None = None
    suggested_label: str | None = None
    label: str | None = None
    display_name: str | None = None
    method: Literal["document_legend", "manual", "ollama", "generic_convention"] = "manual"
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    status: Literal["pending_review", "approved", "ignored"] = "pending_review"
    reasoning: str | None = None
    ignore_reason: str | None = None
    source_mechanism: Literal[
        "pdf_highlight",
        "pdf_text_color",
        "word_highlight",
        "word_font_color",
        "unknown",
    ] = "unknown"

    @field_validator("hex")
    @classmethod
    def validate_hex(cls, value: str) -> str:
        if not HEX_COLOR.fullmatch(value):
            raise ValueError("Expected a six-digit #RRGGBB color.")
        return value.upper()

    @field_validator("label", "suggested_label")
    @classmethod
    def validate_label(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value not in HEVA_LABELS:
            raise ValueError(f"Expected a controlled HEVA label; received {value!r}.")
        return value


class ColorConfigurationMetadata(BaseModel):
    """Document-local color configuration and its human confirmation state."""

    model_config = ConfigDict(extra="forbid")

    detection_method: Literal["document_legend", "manual", "automatic"] | None = None
    document_consistency: Literal["consistent", "mixed", "unknown"] = "unknown"
    human_confirmed: StrictBool = False
    confirmed_by: str | None = None
    confirmed_at: datetime | None = None
    use_for_extraction: StrictBool = False
    extraction_authorized_by: str | None = None
    extraction_authorized_at: datetime | None = None
    shared_from_document_id: str | None = None
    colors: list[ColorMappingMetadata] = Field(default_factory=list)


class ResourceMetadata(BaseModel):
    """A data resource contained in or referenced by this document package."""

    model_config = ConfigDict(extra="forbid")

    name: str
    path: str
    format: Literal["json"]
    record_count: StrictInt = Field(ge=0)

    @field_validator("path")
    @classmethod
    def require_package_relative_path(cls, value: str) -> str:
        path = Path(value)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("Resource path must stay inside the document package.")
        return path.as_posix()


class PackageMetadata(BaseModel):
    """Versioned description of one registered HEVA document package."""

    model_config = ConfigDict(extra="forbid")

    metadata_version: str = METADATA_VERSION
    document_id: str
    source: SourceMetadata = Field(default_factory=SourceMetadata)
    annotator: AnnotatorMetadata = Field(default_factory=AnnotatorMetadata)
    rights: RightsMetadata = Field(default_factory=RightsMetadata)
    annotation_process: AnnotationProcessMetadata = Field(
        default_factory=AnnotationProcessMetadata
    )
    color_configuration: ColorConfigurationMetadata = Field(
        default_factory=ColorConfigurationMetadata
    )
    resources: list[ResourceMetadata] = Field(default_factory=list)


@dataclass(frozen=True)
class ReadinessIssue:
    """One blocking error or visible warning in document metadata."""

    code: str
    severity: Literal["error", "warning"]
    path: str
    message: str


@dataclass(frozen=True)
class ReadinessReport:
    """Review-readiness result for one document metadata record."""

    issues: tuple[ReadinessIssue, ...]

    @property
    def blocking_issues(self) -> tuple[ReadinessIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == "error")

    @property
    def ready(self) -> bool:
        return not self.blocking_issues


class MetadataError(ValueError):
    """Raised when metadata cannot be loaded or linked to a registered document."""


def _issue(
    code: str,
    path: str,
    message: str,
    severity: Literal["error", "warning"] = "error",
) -> ReadinessIssue:
    return ReadinessIssue(code=code, severity=severity, path=path, message=message)


def validate_review_readiness(metadata: PackageMetadata) -> ReadinessReport:
    """Check whether provenance and rights are explicit enough for curator review."""

    issues: list[ReadinessIssue] = []
    source = metadata.source
    rights = metadata.rights
    if not source.title:
        issues.append(_issue("missing_source_title", "$.source.title", "Source title is required."))
    if not source.creators:
        issues.append(
            _issue("missing_source_creator", "$.source.creators", "At least one creator is required.")
        )
    if not source.citation:
        issues.append(_issue("missing_citation", "$.source.citation", "A citation is required."))
    if not source.reference and not source.not_findable_reason:
        issues.append(
            _issue(
                "missing_findability",
                "$.source.reference",
                "Provide a DOI/URL or explain why the source is not findable.",
            )
        )
    elif not source.reference:
        issues.append(
            _issue(
                "source_not_findable",
                "$.source.not_findable_reason",
                "The source is not publicly findable; the explanation is recorded.",
                severity="warning",
            )
        )
    if not metadata.annotator.name:
        issues.append(
            _issue("missing_annotator", "$.annotator.name", "Annotator name is required.")
        )
    if rights.access_level is None:
        issues.append(
            _issue("missing_access_level", "$.rights.access_level", "Access level is required.")
        )
    if rights.authorization_status != "authorized":
        issues.append(
            _issue(
                "source_not_authorized",
                "$.rights.authorization_status",
                "Document authorization must be confirmed before review.",
            )
        )
    if rights.authorization_date is None:
        issues.append(
            _issue(
                "missing_authorization_date",
                "$.rights.authorization_date",
                "Authorization date is required.",
            )
        )
    if not rights.authorized_by:
        issues.append(
            _issue("missing_authorized_by", "$.rights.authorized_by", "Authorizing party is required.")
        )
    if not rights.evidence_reference:
        issues.append(
            _issue(
                "missing_authorization_evidence",
                "$.rights.evidence_reference",
                "A reference to authorization evidence is required.",
            )
        )
    distribution_fields = (
        (
            "source_distribution_allowed",
            "missing_source_distribution_right",
            "Source-document distribution permission must be explicit.",
        ),
        (
            "extracted_text_distribution_allowed",
            "missing_extracted_text_distribution_right",
            "Extracted-text distribution permission must be explicit.",
        ),
        (
            "annotation_distribution_allowed",
            "missing_annotation_distribution_right",
            "Annotation distribution permission must be explicit.",
        ),
    )
    for field_name, code, message in distribution_fields:
        if getattr(rights, field_name) is None:
            issues.append(_issue(code, f"$.rights.{field_name}", message))
    if not rights.license:
        issues.append(_issue("missing_license", "$.rights.license", "License is required."))

    process = metadata.annotation_process
    process_fields = (
        ("method", "missing_extraction_method", "Extraction method is required."),
        ("extractor", "missing_extractor", "Extractor name is required."),
        (
            "extractor_version",
            "missing_extractor_version",
            "Extractor version is required.",
        ),
        ("performed_at", "missing_extraction_date", "Extraction date is required."),
    )
    for field_name, code, message in process_fields:
        if getattr(process, field_name) is None:
            issues.append(_issue(code, f"$.annotation_process.{field_name}", message))
    if not process.review.all_sentences_require_approval:
        issues.append(
            _issue(
                "sentence_approval_not_required",
                "$.annotation_process.review.all_sentences_require_approval",
                "Every extracted sentence must require annotator approval.",
            )
        )
    if not process.review.completed:
        issues.append(
            _issue(
                "annotation_review_incomplete",
                "$.annotation_process.review.completed",
                "Sentence review must be completed before curator review.",
            )
        )
    if process.review.completed and process.review.reviewed_at is None:
        issues.append(
            _issue(
                "missing_review_date",
                "$.annotation_process.review.reviewed_at",
                "Review completion date is required.",
            )
        )

    colors = metadata.color_configuration
    if colors.detection_method is None:
        issues.append(
            _issue(
                "missing_color_detection_method",
                "$.color_configuration.detection_method",
                "Color detection method is required.",
            )
        )
    if not colors.colors:
        issues.append(
            _issue(
                "missing_color_mapping",
                "$.color_configuration.colors",
                "At least one document color must be mapped to a HEVA label.",
            )
        )
    for index, color in enumerate(colors.colors):
        if color.status == "pending_review":
            issues.append(
                _issue(
                    "color_pending_review",
                    f"$.color_configuration.colors[{index}].status",
                    f"Color {color.hex} still requires a human decision.",
                )
            )
        elif color.status == "approved" and color.label is None:
            issues.append(
                _issue(
                    "approved_color_missing_label",
                    f"$.color_configuration.colors[{index}].label",
                    f"Approved color {color.hex} requires a HEVA label.",
                )
            )
        elif color.status == "ignored" and not color.ignore_reason:
            issues.append(
                _issue(
                    "ignored_color_missing_reason",
                    f"$.color_configuration.colors[{index}].ignore_reason",
                    f"Ignored color {color.hex} requires an explanation.",
                )
            )
    if not colors.human_confirmed:
        issues.append(
            _issue(
                "color_mapping_unconfirmed",
                "$.color_configuration.human_confirmed",
                "The document color mapping requires human confirmation.",
            )
        )
    if colors.human_confirmed and not colors.confirmed_by:
        issues.append(
            _issue(
                "missing_color_confirmation_person",
                "$.color_configuration.confirmed_by",
                "Record who confirmed the color mapping.",
            )
        )
    if colors.human_confirmed and colors.confirmed_at is None:
        issues.append(
            _issue(
                "missing_color_confirmation_date",
                "$.color_configuration.confirmed_at",
                "Record when the color mapping was confirmed.",
            )
        )

    annotation_resources = [
        resource for resource in metadata.resources if resource.name == "annotations"
    ]
    if not annotation_resources:
        issues.append(
            _issue(
                "missing_annotations_resource",
                "$.resources",
                "The package must describe its separate annotations JSON resource.",
            )
        )
    return ReadinessReport(issues=tuple(issues))


def load_annotator(path: str | Path) -> AnnotatorMetadata:
    """Load reusable annotator identity from a JSON file."""

    source = Path(path)
    try:
        if source.suffix.lower() != ".json":
            raise MetadataError("Annotator metadata must use .json.")
        text = source.read_text(encoding="utf-8")
        decoded = json.loads(text)
        return AnnotatorMetadata.model_validate(decoded)
    except (OSError, json.JSONDecodeError, ValidationError) as error:
        raise MetadataError(f"Cannot load annotator metadata from {source}: {error}") from error


def _write_json(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def save_package_metadata(
    project_root: str | Path,
    metadata: PackageMetadata,
    *,
    registry_path: str | Path = DEFAULT_REGISTRY_PATH,
) -> Path:
    """Persist metadata inside its registered package and link it from the registry."""

    root = Path(project_root).resolve()
    registry_file = root / Path(registry_path)
    try:
        registry = ProjectRegistry.model_validate_json(registry_file.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as error:
        raise MetadataError(f"Cannot load project registry {registry_file}: {error}") from error
    matches = [entry for entry in registry.documents if entry.document_id == metadata.document_id]
    if not matches:
        raise MetadataError(f"Document {metadata.document_id} is not registered in this project.")
    entry = matches[0]
    metadata_relative = f"{entry.package_path}/package-metadata.json"
    metadata_file = root / metadata_relative
    _write_json(metadata_file, metadata.model_dump(mode="json"))
    entry.metadata_path = metadata_relative
    _write_json(registry_file, registry.model_dump(mode="json"))
    return metadata_file
