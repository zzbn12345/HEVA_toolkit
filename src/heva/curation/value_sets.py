"""Immutable project value sets that name the categories colors can be mapped to.

HEVA ships one built-in value set: the eight heritage values in ``HEVA_LABELS``. A curator
may define additional value sets for other kinds of datasets, for example a health study
with ``physical``, ``mental`` and ``social-support`` values. Value sets are versioned in the
same way as project palettes: every change appends a version, and earlier versions remain
reproducible. A palette version names the exact value set version its colors map to.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Sequence

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from heva.curation.contract import HEVA_LABELS
from heva.curation.people_registry import load_people_registry


VALUE_SETS_PATH = Path(".heva/value-sets.json")
HERITAGE_VALUE_SET_ID = "heva-heritage-values"
HERITAGE_VALUE_SET_VERSION = 1
VALUE_LABEL_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"

_HERITAGE_CREATED_AT = datetime(2026, 1, 1, tzinfo=timezone.utc)


class ValueSetError(ValueError):
    """Raised when a value set cannot be read, created, or resolved safely."""


class ValueDefinition(BaseModel):
    """One named value that annotated colors may be assigned to."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(pattern=VALUE_LABEL_PATTERN)
    description: str | None = None

    @field_validator("label", "description", mode="before")
    @classmethod
    def normalize_text(cls, value: object) -> object:
        """Trim entered text and treat a blank description as absent."""

        if isinstance(value, str):
            return value.strip() or None
        return value


class ProjectValueSet(BaseModel):
    """One immutable, attributable version of a named set of values."""

    model_config = ConfigDict(extra="forbid")

    value_set_id: str = Field(pattern=VALUE_LABEL_PATTERN)
    version: int = Field(ge=1)
    name: str = Field(min_length=1)
    description: str | None = None
    values: list[ValueDefinition] = Field(min_length=1)
    created_by: str = Field(pattern=r"^(PERSON-[A-Z0-9]+|HEVA)$")
    created_at: datetime

    @field_validator("name", "description", mode="before")
    @classmethod
    def normalize_text(cls, value: object) -> object:
        """Trim imported/display text and normalize optional blanks."""

        if isinstance(value, str):
            return value.strip() or None
        return value

    @field_validator("values")
    @classmethod
    def unique_labels(cls, values: list[ValueDefinition]) -> list[ValueDefinition]:
        """Prevent one label from being defined twice in the same version."""

        labels = [value.label for value in values]
        duplicates = sorted({label for label in labels if labels.count(label) > 1})
        if duplicates:
            raise ValueError(f"Each value must be unique; repeated: {', '.join(duplicates)}.")
        return values

    @property
    def labels(self) -> frozenset[str]:
        """Return the labels annotations may use under this version."""

        return frozenset(value.label for value in self.values)

    @property
    def built_in(self) -> bool:
        """Report whether this is the repository-owned HEVA heritage value set."""

        return self.value_set_id == HERITAGE_VALUE_SET_ID


class ValueSetRegistry(BaseModel):
    """All curator-defined value set versions of one project."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    value_sets: list[ProjectValueSet] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_versions(self) -> "ValueSetRegistry":
        """Reject duplicate versions and redefinitions of the built-in value set."""

        keys = [(item.value_set_id, item.version) for item in self.value_sets]
        if len(keys) != len(set(keys)):
            raise ValueError("Every value set version must be unique.")
        if any(item.built_in for item in self.value_sets):
            raise ValueError(f"{HERITAGE_VALUE_SET_ID} is built into HEVA and cannot be redefined.")
        if any(not item.created_by.startswith("PERSON-") for item in self.value_sets):
            raise ValueError("Every project value set must be attributed to a project person.")
        return self


def heritage_value_set() -> ProjectValueSet:
    """Return the built-in HEVA heritage value set, which is never persisted."""

    return ProjectValueSet(
        value_set_id=HERITAGE_VALUE_SET_ID,
        version=HERITAGE_VALUE_SET_VERSION,
        name="HEVA heritage values",
        description="The controlled HEVA heritage value vocabulary.",
        values=[ValueDefinition(label=label) for label in sorted(HEVA_LABELS)],
        created_by="HEVA",
        created_at=_HERITAGE_CREATED_AT,
    )


def _write(path: Path, registry: ValueSetRegistry) -> None:
    """Atomically persist registry state without rewriting existing versions."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(registry.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def load_value_set_registry(project_root: str | Path) -> ValueSetRegistry:
    """Load the project value sets or return an empty non-persisted registry."""

    path = Path(project_root) / VALUE_SETS_PATH
    try:
        return ValueSetRegistry.model_validate_json(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return ValueSetRegistry()
    except (OSError, ValidationError) as error:
        raise ValueSetError("The project value-set registry cannot be read.") from error


def list_value_sets(project_root: str | Path) -> list[ProjectValueSet]:
    """Return the built-in heritage value set followed by every project version."""

    return [heritage_value_set(), *load_value_set_registry(project_root).value_sets]


def _active_curator_id(project_root: str | Path) -> str:
    """Require accountable curator identity for version creation."""

    curator = load_people_registry(project_root).active_curator()
    if curator is None:
        raise ValueSetError("Select an active curator before creating project value sets.")
    return curator.person_id


def create_value_set_version(
    project_root: str | Path,
    *,
    value_set_id: str,
    name: str,
    values: Sequence[ValueDefinition | dict[str, object]],
    description: str | None = None,
) -> ProjectValueSet:
    """Append the next immutable version of a named project value set."""

    if value_set_id == HERITAGE_VALUE_SET_ID:
        raise ValueSetError(
            f"{HERITAGE_VALUE_SET_ID} is built into HEVA; choose another value set ID."
        )
    root = Path(project_root)
    registry = load_value_set_registry(root)
    version = max(
        (item.version for item in registry.value_sets if item.value_set_id == value_set_id),
        default=0,
    ) + 1
    value_set = ProjectValueSet(
        value_set_id=value_set_id,
        version=version,
        name=name,
        description=description,
        values=[ValueDefinition.model_validate(item) for item in values],
        created_by=_active_curator_id(root),
        created_at=datetime.now(timezone.utc),
    )
    registry.value_sets.append(value_set)
    _write(root / VALUE_SETS_PATH, registry)
    return value_set


def get_value_set(
    project_root: str | Path,
    value_set_id: str | None,
    version: int | None,
) -> ProjectValueSet:
    """Load one exact value set version; no reference means the heritage value set."""

    if value_set_id is None or value_set_id == HERITAGE_VALUE_SET_ID:
        if version not in (None, HERITAGE_VALUE_SET_VERSION):
            raise ValueSetError(
                f"Value set {HERITAGE_VALUE_SET_ID} version {version} does not exist."
            )
        return heritage_value_set()
    value_set = next(
        (
            item
            for item in load_value_set_registry(project_root).value_sets
            if item.value_set_id == value_set_id and item.version == version
        ),
        None,
    )
    if value_set is None:
        raise ValueSetError(f"Value set {value_set_id} version {version} does not exist.")
    return value_set


def project_label_vocabulary(project_root: str | Path) -> frozenset[str]:
    """Return every label any value set of this project defines, heritage included.

    This coarse vocabulary is used while project files are read. Validation then checks
    each document against the exact value set of its palette.
    """

    labels = set(HEVA_LABELS)
    for value_set in load_value_set_registry(project_root).value_sets:
        labels.update(value_set.labels)
    return frozenset(labels)


def label_validation_context(project_root: str | Path) -> dict[str, Any]:
    """Return the pydantic validation context that accepts this project's labels."""

    try:
        labels = project_label_vocabulary(project_root)
    except ValueSetError:
        # An unreadable value-set registry is reported on the Value sets page; reading
        # other project files must still work and falls back to the heritage values.
        labels = HEVA_LABELS
    return {"labels": labels}
