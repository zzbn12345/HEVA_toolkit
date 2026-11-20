"""Immutable project color configurations selected for repeatable document mapping."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Sequence

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)

from heva.curation.color_mapping import (
    ColorMappingError,
    confirm_color_configuration,
    load_color_configuration,
    save_color_configuration,
)
from heva.curation.contract import HEVA_LABELS
from heva.curation.document_metadata import (
    ColorConfigurationMetadata,
    ColorMappingMetadata,
)
from heva.curation.people_registry import load_people_registry
from heva.curation.value_sets import (
    HERITAGE_VALUE_SET_ID,
    HERITAGE_VALUE_SET_VERSION,
    ProjectValueSet,
    ValueSetError,
    get_value_set,
    label_validation_context,
)


COLOR_CONFIGURATIONS_PATH = Path(".heva/color-configurations.json")


class ProjectColorMapping(BaseModel):
    """One value-set category represented by one or more source hex values."""

    model_config = ConfigDict(extra="forbid")

    label: str
    hexes: list[str] = Field(min_length=1)

    @field_validator("label")
    @classmethod
    def controlled_label(cls, label: str, info: ValidationInfo) -> str:
        """Reject mappings outside the vocabulary; heritage values unless a context is given."""

        if label not in (info.context or {}).get("labels", HEVA_LABELS):
            raise ValueError(f"Expected a controlled HEVA label; received {label!r}.")
        return label

    @field_validator("hexes")
    @classmethod
    def normalized_hexes(cls, hexes: list[str]) -> list[str]:
        """Normalize, deduplicate, and sort hex values within a category."""

        values = sorted({ColorMappingMetadata(hex=value).hex for value in hexes})
        if not values:
            raise ValueError("Map at least one hex value to this category.")
        return values


class ProjectColorConfiguration(BaseModel):
    """One immutable, attributable version of a reusable semantic color convention."""

    model_config = ConfigDict(extra="forbid")

    configuration_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    version: int = Field(ge=1)
    name: str = Field(min_length=1)
    description: str | None = None
    mappings: list[ProjectColorMapping] = Field(min_length=1)
    created_by: str = Field(pattern=r"^PERSON-[A-Z0-9]+$")
    created_at: datetime
    # No value-set reference means the built-in HEVA heritage values, so palettes saved
    # before value sets existed keep their meaning.
    value_set_id: str | None = None
    value_set_version: int | None = Field(default=None, ge=1)

    @field_validator("name", "description", mode="before")
    @classmethod
    def normalize_text(cls, value: object) -> object:
        """Trim imported/display text and normalize optional blanks."""

        if isinstance(value, str):
            return value.strip() or None
        return value

    @field_validator("mappings")
    @classmethod
    def unambiguous_hexes(
        cls,
        mappings: list[ProjectColorMapping],
    ) -> list[ProjectColorMapping]:
        """Prevent one hex from acquiring two meanings in the same version."""

        assigned: dict[str, str] = {}
        for mapping in mappings:
            for color in mapping.hexes:
                previous = assigned.get(color)
                if previous is not None and previous != mapping.label:
                    raise ValueError(
                        f"Hex {color} is assigned to both {previous!r} and {mapping.label!r}."
                    )
                assigned[color] = mapping.label
        return mappings

    @property
    def value_set_reference(self) -> tuple[str, int]:
        """Return the exact value set version this palette maps colors to."""

        if self.value_set_id is None:
            return HERITAGE_VALUE_SET_ID, HERITAGE_VALUE_SET_VERSION
        return self.value_set_id, self.value_set_version or HERITAGE_VALUE_SET_VERSION

    @property
    def values(self) -> dict[str, str]:
        """Return the normalized extraction map represented by this version."""

        return {
            color: mapping.label
            for mapping in self.mappings
            for color in mapping.hexes
        }


class SelectedColorConfiguration(BaseModel):
    """The immutable version currently selected for this project."""

    model_config = ConfigDict(extra="forbid")

    configuration_id: str
    version: int
    selected_by: str
    selected_at: datetime


class ColorConfigurationRegistry(BaseModel):
    """All immutable versions and the project-level active selection."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    selected: SelectedColorConfiguration | None = None
    configurations: list[ProjectColorConfiguration] = Field(default_factory=list)

    @model_validator(mode="after")
    def consistent_versions_and_selection(self) -> "ColorConfigurationRegistry":
        """Reject duplicate versions and selections that cannot be reproduced."""

        keys = [
            (item.configuration_id, item.version)
            for item in self.configurations
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("Every color configuration version must be unique.")
        if self.selected is not None and (
            self.selected.configuration_id,
            self.selected.version,
        ) not in keys:
            raise ValueError("The selected color configuration version does not exist.")
        return self


class ProjectColorConfigurationError(ValueError):
    """Raised when reusable color semantics would become ambiguous or mutable."""


def _write(path: Path, registry: ColorConfigurationRegistry) -> None:
    """Atomically persist registry state without rewriting existing versions."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(registry.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def load_color_configuration_registry(
    project_root: str | Path,
) -> ColorConfigurationRegistry:
    """Load the project registry or return an empty non-persisted registry."""

    path = Path(project_root) / COLOR_CONFIGURATIONS_PATH
    try:
        return ColorConfigurationRegistry.model_validate_json(
            path.read_text(encoding="utf-8"),
            context=label_validation_context(project_root),
        )
    except FileNotFoundError:
        return ColorConfigurationRegistry()
    except (OSError, ValidationError) as error:
        raise ProjectColorConfigurationError(
            "The project color-configuration registry cannot be read."
        ) from error


def _active_curator_id(project_root: str | Path) -> str:
    """Require accountable curator identity for version creation and selection."""

    curator = load_people_registry(project_root).active_curator()
    if curator is None:
        raise ProjectColorConfigurationError(
            "Select an active curator before changing project color configurations."
        )
    return curator.person_id


def create_color_configuration_version(
    project_root: str | Path,
    *,
    configuration_id: str,
    name: str,
    mappings: Sequence[ProjectColorMapping | dict[str, object]],
    description: str | None = None,
    value_set_id: str | None = None,
    value_set_version: int | None = None,
) -> ProjectColorConfiguration:
    """Append the next immutable version of a named project configuration.

    The mappings may only use labels of the named value set; without one, the HEVA
    heritage values apply.
    """

    root = Path(project_root)
    try:
        value_set = get_value_set(root, value_set_id, value_set_version)
    except ValueSetError as error:
        raise ProjectColorConfigurationError(str(error)) from error
    registry = load_color_configuration_registry(root)
    versions = [
        item.version
        for item in registry.configurations
        if item.configuration_id == configuration_id
    ]
    version = max(versions, default=0) + 1
    configuration = ProjectColorConfiguration(
        configuration_id=configuration_id,
        version=version,
        name=name,
        description=description,
        mappings=[
            ProjectColorMapping.model_validate(
                item.model_dump() if isinstance(item, ProjectColorMapping) else item,
                context={"labels": value_set.labels},
            )
            for item in mappings
        ],
        created_by=_active_curator_id(root),
        created_at=datetime.now(timezone.utc),
        value_set_id=None if value_set.built_in else value_set.value_set_id,
        value_set_version=None if value_set.built_in else value_set.version,
    )
    registry.configurations.append(configuration)
    _write(root / COLOR_CONFIGURATIONS_PATH, registry)
    return configuration


def get_color_configuration(
    project_root: str | Path,
    configuration_id: str,
    version: int,
) -> ProjectColorConfiguration:
    """Load one exact immutable version or fail with a localizable reference."""

    registry = load_color_configuration_registry(project_root)
    configuration = next(
        (
            item
            for item in registry.configurations
            if item.configuration_id == configuration_id and item.version == version
        ),
        None,
    )
    if configuration is None:
        raise ProjectColorConfigurationError(
            f"Color configuration {configuration_id} version {version} does not exist."
        )
    return configuration


def select_color_configuration(
    project_root: str | Path,
    configuration_id: str,
    version: int,
) -> ProjectColorConfiguration:
    """Select one exact version as the project default without editing its content."""

    root = Path(project_root)
    registry = load_color_configuration_registry(root)
    configuration = get_color_configuration(root, configuration_id, version)
    registry.selected = SelectedColorConfiguration(
        configuration_id=configuration_id,
        version=version,
        selected_by=_active_curator_id(root),
        selected_at=datetime.now(timezone.utc),
    )
    _write(root / COLOR_CONFIGURATIONS_PATH, registry)
    return configuration


def selected_color_configuration(
    project_root: str | Path,
) -> ProjectColorConfiguration:
    """Resolve the project selection to its exact immutable configuration."""

    registry = load_color_configuration_registry(project_root)
    if registry.selected is None:
        raise ProjectColorConfigurationError(
            "Select a project color configuration before mapping document colors."
        )
    return get_color_configuration(
        project_root,
        registry.selected.configuration_id,
        registry.selected.version,
    )


def apply_selected_configuration_to_document(
    project_root: str | Path,
    document_id: str,
) -> None:
    """Resolve all observed document colors using the selected project version."""

    root = Path(project_root)
    selected = selected_color_configuration(root)
    values = selected.values
    document = load_color_configuration(root, document_id)
    unresolved = [
        color.hex
        for color in document.colors
        if color.status != "ignored" and color.hex not in values
    ]
    if unresolved:
        raise ProjectColorConfigurationError(
            "The selected configuration does not define these observed colors: "
            + ", ".join(sorted(unresolved))
        )
    updated = document.model_copy(deep=True)
    for color in updated.colors:
        if color.status == "ignored":
            continue
        color.suggested_label = values[color.hex]
        color.label = values[color.hex]
        color.method = "manual"
        color.status = "approved"
        color.ignore_reason = None
    updated.configuration_id = selected.configuration_id
    updated.configuration_version = selected.version
    updated.shared_from_document_id = None
    curator = load_people_registry(root).active_curator()
    if curator is None:  # Protected by selection, retained for corrupted registries.
        raise ProjectColorConfigurationError("Select an active curator first.")
    try:
        updated = confirm_color_configuration(updated, confirmed_by=curator.name)
        save_color_configuration(root, document_id, updated)
    except ColorMappingError as error:
        raise ProjectColorConfigurationError(str(error)) from error


def palette_value_set(
    project_root: str | Path,
    configuration: ProjectColorConfiguration,
) -> ProjectValueSet:
    """Resolve the exact value set version a palette maps colors to."""

    value_set_id, version = configuration.value_set_reference
    try:
        return get_value_set(project_root, value_set_id, version)
    except ValueSetError as error:
        raise ProjectColorConfigurationError(str(error)) from error


def selected_value_set(project_root: str | Path) -> ProjectValueSet:
    """Return the value set of the selected palette, or the heritage values if none is selected."""

    registry = load_color_configuration_registry(project_root)
    if registry.selected is None:
        return get_value_set(project_root, None, None)
    return palette_value_set(project_root, selected_color_configuration(project_root))


def document_value_set(
    project_root: str | Path,
    configuration: ColorConfigurationMetadata,
) -> ProjectValueSet:
    """Return the value set of the palette a document was mapped with.

    Documents mapped before value sets existed, or not yet mapped with a project palette,
    use the HEVA heritage values.
    """

    if configuration.configuration_id is None or configuration.configuration_version is None:
        return get_value_set(project_root, None, None)
    palette = get_color_configuration(
        project_root,
        configuration.configuration_id,
        configuration.configuration_version,
    )
    return palette_value_set(project_root, palette)


def document_label_vocabulary(project_root: str | Path, document_id: str) -> frozenset[str]:
    """Return the labels a registered document's records may use.

    When the document's palette cannot be resolved, every label known to the project is
    accepted here so that the dedicated validation finding explains the problem instead.
    """

    try:
        configuration = load_color_configuration(project_root, document_id)
        return document_value_set(project_root, configuration).labels
    except (ColorMappingError, ProjectColorConfigurationError, ValueSetError):
        return label_validation_context(project_root)["labels"]
