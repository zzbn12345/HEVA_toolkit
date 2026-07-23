"""Document-local color proposals and the human confirmation gate."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from pydantic import ValidationError

from src.document_metadata import (
    ColorConfigurationMetadata,
    ColorMappingMetadata,
    PackageMetadata,
)
from src.project_registry import DEFAULT_REGISTRY_PATH, ProjectRegistry


class ColorMappingError(ValueError):
    """Raised when a color decision cannot safely pass the supervision gate."""


@dataclass(frozen=True)
class BatchMappingIssue:
    """One reason a color map cannot be silently shared across a batch."""

    code: str
    document_id: str | None
    message: str


@dataclass(frozen=True)
class BatchMappingReport:
    """Safety result for applying one mapping to multiple documents."""

    issues: tuple[BatchMappingIssue, ...]

    @property
    def allowed(self) -> bool:
        return not self.issues


_COLOR_NAMES = {
    "#000000": "Black",
    "#000080": "Navy",
    "#0000FF": "Blue",
    "#008000": "Green",
    "#00FF00": "Bright green",
    "#00FFFF": "Turquoise",
    "#800000": "Dark red",
    "#800080": "Violet",
    "#FF0000": "Red",
    "#FF00FF": "Magenta",
    "#FFFF00": "Yellow",
    "#FFFFFF": "White",
}


def _normalize_hex(value: str) -> str:
    """Normalize through the package model so invalid colors are rejected consistently."""

    return ColorMappingMetadata(hex=value).hex


def _color_name(value: str) -> str:
    if value in _COLOR_NAMES:
        return _COLOR_NAMES[value]
    red, green, blue = (int(value[index : index + 2], 16) for index in (1, 3, 5))
    nearest = min(
        _COLOR_NAMES,
        key=lambda candidate: sum(
            (
                red - int(candidate[1:3], 16),
                green - int(candidate[3:5], 16),
                blue - int(candidate[5:7], 16),
            )[channel]
            ** 2
            for channel in range(3)
        ),
    )
    return f"Near {_COLOR_NAMES[nearest].lower()}"


def _contrasting_text(value: str) -> str:
    red, green, blue = (int(value[index : index + 2], 16) for index in (1, 3, 5))
    luminance = (0.299 * red) + (0.587 * green) + (0.114 * blue)
    return "#000000" if luminance >= 150 else "#FFFFFF"


def _normalized_mapping(values: Mapping[str, str] | None) -> dict[str, str]:
    return {_normalize_hex(color): label for color, label in (values or {}).items()}


def observed_colors_from_records(records: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
    """Collect raw hex evidence from an extractor run performed without a color map."""

    colors: set[str] = set()
    for record in records:
        for entity in record.get("entities", []):
            candidate = entity.get("color") or entity.get("label")
            if isinstance(candidate, str) and candidate.startswith("#"):
                colors.add(_normalize_hex(candidate))
    return tuple(sorted(colors))


def propose_color_configuration(
    observed_colors: list[str] | tuple[str, ...] | set[str],
    *,
    legend_mapping: Mapping[str, str] | None = None,
    ollama_suggestions: Mapping[str, str] | None = None,
    ollama_confidence: Mapping[str, float] | None = None,
    generic_suggestions: Mapping[str, str] | None = None,
) -> ColorConfigurationMetadata:
    """Create pending proposals, preferring document evidence over inferred conventions."""

    legend = _normalized_mapping(legend_mapping)
    ollama = _normalized_mapping(ollama_suggestions)
    generic = _normalized_mapping(generic_suggestions)
    confidence = {
        _normalize_hex(color): value for color, value in (ollama_confidence or {}).items()
    }
    normalized_colors = sorted({_normalize_hex(color) for color in observed_colors})
    proposals: list[ColorMappingMetadata] = []
    for color in normalized_colors:
        method = "manual"
        suggested_label = None
        suggested_confidence = None
        if color in legend:
            method = "document_legend"
            suggested_label = legend[color]
            suggested_confidence = 1.0
        elif color in ollama:
            method = "ollama"
            suggested_label = ollama[color]
            suggested_confidence = confidence.get(color)
        elif color in generic:
            method = "generic_convention"
            suggested_label = generic[color]
        proposals.append(
            ColorMappingMetadata(
                hex=color,
                color_name=_color_name(color),
                text_color=_contrasting_text(color),
                suggested_label=suggested_label,
                method=method,
                confidence=suggested_confidence,
                status="pending_review",
            )
        )
    if legend:
        detection_method = "document_legend"
    elif ollama or generic:
        detection_method = "automatic"
    else:
        detection_method = "manual"
    return ColorConfigurationMetadata(
        detection_method=detection_method,
        colors=proposals,
    )


def resolve_color(
    configuration: ColorConfigurationMetadata,
    color: str,
    *,
    label: str | None = None,
    ignore_reason: str | None = None,
) -> ColorConfigurationMetadata:
    """Return a copy with one color explicitly approved or ignored by a person."""

    if (label is None) == (ignore_reason is None):
        raise ColorMappingError("Provide either an approved label or an ignore reason.")
    normalized = _normalize_hex(color)
    updated = configuration.model_copy(deep=True)
    matches = [entry for entry in updated.colors if entry.hex == normalized]
    if not matches:
        raise ColorMappingError(f"Color {normalized} is not present in this document.")
    entry = matches[0]
    if label is not None:
        validated = ColorMappingMetadata(hex=normalized, label=label)
        entry.label = validated.label
        entry.status = "approved"
        entry.ignore_reason = None
    else:
        entry.label = None
        entry.status = "ignored"
        entry.ignore_reason = ignore_reason.strip() if ignore_reason else None
    updated.human_confirmed = False
    updated.confirmed_by = None
    updated.confirmed_at = None
    return updated


def confirm_color_configuration(
    configuration: ColorConfigurationMetadata,
    *,
    confirmed_by: str,
    confirmed_at: datetime | None = None,
) -> ColorConfigurationMetadata:
    """Confirm a configuration only after every observed color has a human decision."""

    if not confirmed_by.strip():
        raise ColorMappingError("The person confirming the mapping is required.")
    if not configuration.colors:
        raise ColorMappingError("No observed colors are available to confirm.")
    pending = [entry.hex for entry in configuration.colors if entry.status == "pending_review"]
    if pending:
        raise ColorMappingError(f"These colors are still pending review: {', '.join(pending)}.")
    for entry in configuration.colors:
        if entry.status == "approved" and entry.label is None:
            raise ColorMappingError(f"Approved color {entry.hex} has no HEVA label.")
        if entry.status == "ignored" and not entry.ignore_reason:
            raise ColorMappingError(f"Ignored color {entry.hex} requires an ignore reason.")
    updated = configuration.model_copy(deep=True)
    updated.human_confirmed = True
    updated.confirmed_by = confirmed_by.strip()
    updated.confirmed_at = confirmed_at or datetime.now(timezone.utc)
    return updated


def validate_shared_batch_mapping(
    configurations: Mapping[str, ColorConfigurationMetadata],
) -> BatchMappingReport:
    """Require identical palettes and explicit confirmation for every batch document."""

    issues: list[BatchMappingIssue] = []
    palettes = {
        document_id: frozenset(entry.hex for entry in configuration.colors)
        for document_id, configuration in configurations.items()
    }
    if len(set(palettes.values())) > 1:
        issues.append(
            BatchMappingIssue(
                code="batch_palette_mismatch",
                document_id=None,
                message="Documents have different color palettes; use per-document mappings.",
            )
        )
    for document_id, configuration in configurations.items():
        if not configuration.human_confirmed:
            issues.append(
                BatchMappingIssue(
                    code="shared_mapping_unconfirmed",
                    document_id=document_id,
                    message="Shared mapping requires confirmation for this document.",
                )
            )
    return BatchMappingReport(issues=tuple(issues))


def save_color_configuration(
    project_root: str | Path,
    document_id: str,
    configuration: ColorConfigurationMetadata,
    *,
    registry_path: str | Path = DEFAULT_REGISTRY_PATH,
) -> Path:
    """Persist a document-local configuration inside its existing package metadata."""

    root = Path(project_root).resolve()
    registry_file = root / Path(registry_path)
    try:
        registry = ProjectRegistry.model_validate_json(registry_file.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as error:
        raise ColorMappingError(f"Cannot load project registry {registry_file}: {error}") from error
    matches = [entry for entry in registry.documents if entry.document_id == document_id]
    if not matches:
        raise ColorMappingError(f"Document {document_id} is not registered in this project.")
    entry = matches[0]
    if entry.metadata_path is None:
        raise ColorMappingError(f"Document {document_id} has no package metadata path.")
    metadata_file = root / entry.metadata_path
    try:
        metadata = PackageMetadata.model_validate_json(metadata_file.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as error:
        raise ColorMappingError(f"Cannot load package metadata {metadata_file}: {error}") from error
    metadata.color_configuration = configuration
    temporary = metadata_file.with_suffix(metadata_file.suffix + ".tmp")
    temporary.write_text(
        json.dumps(metadata.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(metadata_file)
    return metadata_file


def load_confirmed_color_mapping(
    project_root: str | Path,
    document_id: str,
    *,
    registry_path: str | Path = DEFAULT_REGISTRY_PATH,
) -> dict[str, str]:
    """Load only approved color decisions from a human-confirmed document package."""

    root = Path(project_root).resolve()
    registry_file = root / Path(registry_path)
    try:
        registry = ProjectRegistry.model_validate_json(registry_file.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as error:
        raise ColorMappingError(f"Cannot load project registry {registry_file}: {error}") from error
    matches = [entry for entry in registry.documents if entry.document_id == document_id]
    if not matches:
        raise ColorMappingError(f"Document {document_id} is not registered in this project.")
    metadata_path = matches[0].metadata_path
    if metadata_path is None:
        raise ColorMappingError(f"Document {document_id} has no package metadata path.")
    metadata_file = root / metadata_path
    try:
        metadata = PackageMetadata.model_validate_json(metadata_file.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as error:
        raise ColorMappingError(f"Cannot load package metadata {metadata_file}: {error}") from error
    configuration = metadata.color_configuration
    if not configuration.human_confirmed:
        raise ColorMappingError(
            f"Document {document_id} color mapping has not been confirmed by a person."
        )
    mapping = {
        entry.hex: entry.label
        for entry in configuration.colors
        if entry.status == "approved" and entry.label is not None
    }
    if not mapping:
        raise ColorMappingError(f"Document {document_id} has no approved color mappings.")
    return mapping
