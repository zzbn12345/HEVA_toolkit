"""Safe per-document authorization and distribution-rights persistence."""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from heva.curation.document_metadata import (
    PackageMetadata,
    RightsMetadata,
    save_package_metadata,
)
from heva.curation.project_registry import (
    DEFAULT_REGISTRY_PATH,
    DocumentEntry,
    ProjectRegistry,
)


class DocumentRightsError(ValueError):
    """Raised when rights cannot be loaded or changed within workflow rules."""


def _metadata_entry(
    project_root: str | Path,
    document_id: str,
) -> tuple[Path, DocumentEntry, PackageMetadata]:
    """Resolve one registered document and its existing package metadata."""

    root = Path(project_root).resolve()
    try:
        registry = ProjectRegistry.model_validate_json(
            (root / DEFAULT_REGISTRY_PATH).read_text(encoding="utf-8")
        )
    except (OSError, ValidationError) as error:
        raise DocumentRightsError(f"Cannot load project registry: {error}") from error
    entry = next(
        (item for item in registry.documents if item.document_id == document_id),
        None,
    )
    if entry is None:
        raise DocumentRightsError(f"Document {document_id} is not registered.")
    metadata_path = root / (
        entry.metadata_path or f"{entry.package_path}/metadata.json"
    )
    try:
        metadata = PackageMetadata.model_validate_json(
            metadata_path.read_text(encoding="utf-8")
        )
    except (OSError, ValidationError) as error:
        raise DocumentRightsError(f"Cannot load document metadata: {error}") from error
    return root, entry, metadata


def load_document_rights(
    project_root: str | Path,
    document_id: str,
) -> RightsMetadata:
    """Load the schema-validated rights record for one registered document."""

    _, _, metadata = _metadata_entry(project_root, document_id)
    return metadata.rights


def save_document_rights(
    project_root: str | Path,
    document_id: str,
    rights: RightsMetadata,
) -> RightsMetadata:
    """Persist rights without rewriting other document metadata."""

    root, _, metadata = _metadata_entry(project_root, document_id)
    metadata.rights = rights
    try:
        save_package_metadata(root, metadata)
    except (OSError, ValueError) as error:
        raise DocumentRightsError(f"Cannot save document rights: {error}") from error
    return rights
