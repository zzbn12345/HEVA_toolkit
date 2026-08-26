"""Initialize and synchronize the file-based HEVA project registry."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shutil
from typing import Iterable, Literal

from pydantic import BaseModel, ConfigDict, ValidationError


REGISTRY_VERSION = "1.0"
DEFAULT_REGISTRY_PATH = Path(".heva/project.json")
LEGACY_REGISTRY_PATH = Path("data/project-registry.json")
DATA_DOCUMENTS_DIRECTORY = Path("documents")
WORKSPACE_DOCUMENTS_DIRECTORY = Path(".heva/documents")
LOCAL_SOURCES_PATH = Path(".heva/local-sources.json")
SUPPORTED_SUFFIXES = frozenset({".pdf", ".docx"})
WORKFLOW_FILENAMES = frozenset(
    {
        "extraction-session.json",
        "review-state.json",
        "curation-state.json",
        "quality-report.json",
        "data-owner-approval.json",
    }
)


class DocumentEntry(BaseModel):
    """Persistent identity and source state for one HEVA document."""

    model_config = ConfigDict(extra="forbid")

    document_id: str
    source_path: str
    package_path: str
    metadata_path: str | None = None
    checksum_sha256: str
    observed_checksum_sha256: str | None = None
    status: Literal["backlog", "in_progress", "in_review", "done"] = "backlog"
    source_state: Literal["present", "changed", "missing"] = "present"
    source_binding: Literal["project", "external"] = "project"


class RegistrySummary(BaseModel):
    """Precomputed counts used to load a project dashboard quickly."""

    model_config = ConfigDict(extra="forbid")

    total: int
    backlog: int
    in_progress: int
    in_review: int
    done: int
    changed: int
    missing: int


class ProjectRegistry(BaseModel):
    """Versioned collection of registered HEVA source documents."""

    model_config = ConfigDict(extra="forbid")

    registry_version: str = REGISTRY_VERSION
    source_directory: str
    documents: list[DocumentEntry]
    summary: RegistrySummary


@dataclass(frozen=True)
class SyncReport:
    """Summary of changes observed during one registry synchronization."""

    registry_path: str
    added: int
    unchanged: int
    changed: tuple[str, ...]
    missing: tuple[str, ...]
    total: int

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable summary for scripts and later interfaces."""

        return {
            "registry_path": self.registry_path,
            "added": self.added,
            "unchanged": self.unchanged,
            "changed": list(self.changed),
            "missing": list(self.missing),
            "total": self.total,
        }


@dataclass(frozen=True)
class SourceScanReport:
    """Non-mutating comparison between registered documents and source files on disk."""

    discovered: tuple[str, ...]
    changed: tuple[str, ...]
    missing: tuple[str, ...]


@dataclass(frozen=True)
class ManagedImportResult:
    """Outcome of copying one PDF into project-managed source storage."""

    document_id: str
    source_path: str
    checksum_sha256: str
    created: bool


def scan_project_sources(project_root: str | Path) -> SourceScanReport:
    """Inspect configured sources without registering or rewriting project state."""

    root = Path(project_root).resolve()
    registry = load_project_registry(root)
    source_root = root / registry.source_directory
    discovered = {
        _relative_posix(path, root): path for path in _discover_sources(source_root)
    }
    existing = {
        entry.source_path: entry
        for entry in registry.documents
        if entry.source_binding == "project"
    }
    new_paths = sorted(set(discovered) - set(existing))
    missing = sorted(set(existing) - set(discovered))
    changed = sorted(
        path for path in set(existing) & set(discovered)
        if _checksum(discovered[path]) != existing[path].checksum_sha256
    )
    for entry in registry.documents:
        if entry.source_binding != "external":
            continue
        try:
            bound = resolve_document_source(root, entry)
        except RegistryError:
            missing.append(entry.source_path)
            continue
        if not bound.is_file():
            missing.append(entry.source_path)
        elif _checksum(bound) != entry.checksum_sha256:
            changed.append(entry.source_path)
    return SourceScanReport(
        tuple(new_paths), tuple(sorted(changed)), tuple(sorted(missing))
    )


def require_current_document_source(project_root: str | Path, entry: DocumentEntry) -> Path:
    """Resolve one source and reject a missing or checksum-changed local binding."""

    source = resolve_document_source(project_root, entry)
    if not source.is_file():
        raise RegistryError(f"Source for {entry.document_id} is missing.")
    if _checksum(source) != entry.checksum_sha256:
        raise RegistryError(f"Source for {entry.document_id} changed since registration.")
    return source


def register_discovered_sources(
    project_root: str | Path,
    source_paths: Iterable[str],
) -> tuple[str, ...]:
    """Register an explicit subset of currently discovered source paths."""

    root = Path(project_root).resolve()
    registry = load_project_registry(root)
    requested = tuple(dict.fromkeys(source_paths))
    scan = scan_project_sources(root)
    unavailable = sorted(set(requested) - set(scan.discovered))
    if unavailable:
        raise RegistryError(
            "These sources are not currently available for registration: "
            + ", ".join(unavailable)
        )
    occupied = {entry.document_id: entry.source_path for entry in registry.documents}
    added_ids: list[str] = []
    for source_path in requested:
        physical_path = root / source_path
        document_id = _new_document_id(source_path, occupied)
        occupied[document_id] = source_path
        registry.documents.append(
            DocumentEntry(
                document_id=document_id,
                source_path=source_path,
                package_path=f"{DATA_DOCUMENTS_DIRECTORY.as_posix()}/{document_id}",
                checksum_sha256=_checksum(physical_path),
            )
        )
        added_ids.append(document_id)
    registry.documents.sort(key=lambda entry: entry.source_path)
    registry.summary = _summarize(registry.documents)
    _create_package_directories(root, registry.documents)
    _write_registry(root / DEFAULT_REGISTRY_PATH, registry)
    return tuple(added_ids)


def _local_source_bindings(root: Path) -> dict[str, str]:
    """Load machine-local external paths that must never enter version control."""

    path = root / LOCAL_SOURCES_PATH
    try:
        decoded = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as error:
        raise RegistryError("The local external-source bindings cannot be read.") from error
    if not isinstance(decoded, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in decoded.items()
    ):
        raise RegistryError("The local external-source bindings are invalid.")
    return decoded


def _write_local_source_bindings(root: Path, bindings: dict[str, str]) -> None:
    path = root / LOCAL_SOURCES_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(bindings, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def resolve_document_source(project_root: str | Path, entry: DocumentEntry) -> Path:
    """Resolve a project-relative or machine-local external source path."""

    root = Path(project_root).resolve()
    if entry.source_binding == "project":
        return (root / entry.source_path).resolve()
    binding = _local_source_bindings(root).get(entry.document_id)
    if binding is None:
        raise RegistryError(
            f"External source for {entry.document_id} is not bound on this computer."
        )
    return Path(binding).expanduser().resolve()


def register_external_source(project_root: str | Path, source_file: str | Path) -> str:
    """Register one external PDF/DOCX while keeping its absolute path machine-local."""

    root = Path(project_root).resolve()
    source = Path(source_file).expanduser().resolve()
    if not source.is_file() or source.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise RegistryError("Choose an existing PDF or DOCX source file.")
    registry = load_project_registry(root)
    checksum = _checksum(source)
    for entry in registry.documents:
        if entry.source_binding == "external" and entry.checksum_sha256 == checksum:
            bindings = _local_source_bindings(root)
            bindings[entry.document_id] = str(source)
            _write_local_source_bindings(root, bindings)
            return entry.document_id
    logical = f"external/{source.name}"
    occupied_paths = {entry.source_path for entry in registry.documents}
    if logical in occupied_paths:
        logical = f"external/{checksum[:12]}-{source.name}"
    occupied = {entry.document_id: entry.source_path for entry in registry.documents}
    document_id = _new_document_id(logical, occupied)
    registry.documents.append(
        DocumentEntry(
            document_id=document_id,
            source_path=logical,
            package_path=f"{DATA_DOCUMENTS_DIRECTORY.as_posix()}/{document_id}",
            checksum_sha256=checksum,
            source_binding="external",
        )
    )
    registry.documents.sort(key=lambda entry: entry.source_path)
    registry.summary = _summarize(registry.documents)
    _create_package_directories(root, registry.documents)
    _write_registry(root / DEFAULT_REGISTRY_PATH, registry)
    bindings = _local_source_bindings(root)
    bindings[document_id] = str(source)
    _write_local_source_bindings(root, bindings)
    return document_id


def import_managed_pdf(
    project_root: str | Path,
    source_file: str | Path,
) -> ManagedImportResult:
    """Copy one PDF into managed storage and atomically register its verified bytes.

    Identical content resolves to the existing document. A same-name file with different
    bytes receives a checksum-prefixed name and is never allowed to overwrite silently.
    The incoming absolute path is used only for this operation and is not persisted.
    """

    root = Path(project_root).resolve()
    source = Path(source_file).expanduser().resolve()
    if not source.is_file() or source.suffix.lower() != ".pdf":
        raise RegistryError("Choose an existing PDF file to import into this project.")
    try:
        with source.open("rb") as stream:
            header = stream.read(1024)
    except OSError as error:
        raise RegistryError(f"The selected PDF cannot be read: {error}") from error
    if b"%PDF-" not in header:
        raise RegistryError("The selected file does not contain a valid PDF header.")

    registry = load_project_registry(root)
    checksum = _checksum(source)
    for entry in registry.documents:
        if entry.checksum_sha256 == checksum:
            return ManagedImportResult(
                document_id=entry.document_id,
                source_path=entry.source_path,
                checksum_sha256=checksum,
                created=False,
            )

    configured_root = Path(registry.source_directory)
    managed_directory = configured_root / "sources"
    destination_relative = managed_directory / source.name
    destination = root / destination_relative
    occupied_paths = {entry.source_path for entry in registry.documents}
    if destination_relative.as_posix() in occupied_paths or destination.exists():
        destination_relative = managed_directory / f"{checksum[:12]}-{source.name}"
        destination = root / destination_relative
    if destination.exists():
        raise RegistryError(
            f"Managed destination already exists and will not be overwritten: {destination_relative.as_posix()}"
        )

    logical = destination_relative.as_posix()
    occupied = {entry.document_id: entry.source_path for entry in registry.documents}
    document_id = _new_document_id(logical, occupied)
    entry = DocumentEntry(
        document_id=document_id,
        source_path=logical,
        package_path=f"{DATA_DOCUMENTS_DIRECTORY.as_posix()}/{document_id}",
        checksum_sha256=checksum,
        source_binding="project",
    )
    package_directory = document_data_directory(root, document_id)
    temporary = destination.with_name(f".{destination.name}.heva-import")
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, temporary)
        if _checksum(temporary) != checksum:
            raise RegistryError("The managed PDF copy failed checksum verification.")
        temporary.replace(destination)
        registry.documents.append(entry)
        registry.documents.sort(key=lambda item: item.source_path)
        registry.summary = _summarize(registry.documents)
        _create_package_directories(root, [entry])
        _write_registry(root / DEFAULT_REGISTRY_PATH, registry)
    except (OSError, RegistryError) as error:
        temporary.unlink(missing_ok=True)
        destination.unlink(missing_ok=True)
        if package_directory.exists():
            shutil.rmtree(package_directory)
        if isinstance(error, RegistryError):
            raise
        raise RegistryError(f"The PDF could not be imported into the project: {error}") from error

    return ManagedImportResult(
        document_id=document_id,
        source_path=logical,
        checksum_sha256=checksum,
        created=True,
    )


class RegistryError(ValueError):
    """Raised when a project registry or source configuration is unusable."""


def document_data_directory(project_root: str | Path, document_id: str) -> Path:
    """Return the canonical analytical-data directory for one document."""

    return Path(project_root).resolve() / DATA_DOCUMENTS_DIRECTORY / document_id


def document_workspace_directory(project_root: str | Path, document_id: str) -> Path:
    """Return the hidden application-workflow directory for one document."""

    return Path(project_root).resolve() / WORKSPACE_DOCUMENTS_DIRECTORY / document_id


def migrate_project_layout(project_root: str | Path) -> bool:
    """Upgrade a legacy mixed package layout without overwriting existing data.

    Returns ``True`` when the legacy registry or any document file was moved. The
    migration keeps analytical metadata and annotations under ``documents`` and
    moves application-only state under ``.heva/documents``.
    """

    root = Path(project_root).resolve()
    legacy_registry = root / LEGACY_REGISTRY_PATH
    registry_path = root / DEFAULT_REGISTRY_PATH
    if not legacy_registry.exists():
        return False
    if registry_path.exists():
        raise RegistryError(
            "Both legacy and current HEVA project registries exist; remove the duplicate "
            "only after confirming which registry is authoritative."
        )
    try:
        decoded = json.loads(legacy_registry.read_text(encoding="utf-8"))
        registry = ProjectRegistry.model_validate(decoded)
    except (OSError, json.JSONDecodeError, ValidationError) as error:
        raise RegistryError(f"Cannot migrate legacy registry {legacy_registry}: {error}") from error

    planned_moves: list[tuple[Path, Path]] = []
    legacy_directories: list[Path] = []
    for entry in registry.documents:
        legacy_directory = root / entry.package_path
        data_directory = document_data_directory(root, entry.document_id)
        workspace_directory = document_workspace_directory(root, entry.document_id)
        legacy_directories.append(legacy_directory)
        document_moves = [
            (legacy_directory / "package-metadata.json", data_directory / "metadata.json"),
            (legacy_directory / "annotations.json", data_directory / "annotations.json"),
        ]
        document_moves.extend(
            (legacy_directory / filename, workspace_directory / filename)
            for filename in WORKFLOW_FILENAMES
        )
        for source, target in document_moves:
            if not source.exists():
                continue
            if target.exists():
                raise RegistryError(
                    f"Cannot migrate {entry.document_id}: {target.name} already exists."
                )
            planned_moves.append((source, target))
        entry.package_path = f"{DATA_DOCUMENTS_DIRECTORY.as_posix()}/{entry.document_id}"
        entry.metadata_path = f"{entry.package_path}/metadata.json"

    completed_moves: list[tuple[Path, Path]] = []
    try:
        for source, target in planned_moves:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(target))
            completed_moves.append((source, target))
        _write_registry(registry_path, registry)
    except OSError as error:
        for source, target in reversed(completed_moves):
            source.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(target), str(source))
        raise RegistryError(f"Cannot migrate legacy HEVA project: {error}") from error

    legacy_registry.unlink()
    for legacy_directory in legacy_directories:
        if legacy_directory.exists() and not any(legacy_directory.iterdir()):
            legacy_directory.rmdir()
    legacy_packages = root / "data/packages"
    if legacy_packages.exists() and not any(legacy_packages.iterdir()):
        legacy_packages.rmdir()
    return True


def load_project_registry(project_root: str | Path) -> ProjectRegistry:
    """Load the current registry, migrating a legacy project when necessary."""

    root = Path(project_root).resolve()
    migrate_project_layout(root)
    try:
        return ProjectRegistry.model_validate_json(
            (root / DEFAULT_REGISTRY_PATH).read_text(encoding="utf-8")
        )
    except (OSError, ValidationError) as error:
        raise RegistryError(f"Cannot load project registry: {error}") from error


def relocate_project_root_to_sources(
    project_root: str | Path,
    source_directory: str | Path,
) -> Path:
    """Make the source-document directory the project root without changing IDs.

    Durable analytical data and hidden workflow JSON move with the project. Source paths,
    document-data paths, and metadata paths are rewritten relative to the new root. Any
    destination conflict is rejected before files move.
    """

    root = Path(project_root).resolve()
    migrate_project_layout(root)
    source_relative = Path(source_directory)
    if source_relative.is_absolute() or source_relative == Path("."):
        raise RegistryError("Choose a source directory inside the current project root.")
    target_root = (root / source_relative).resolve()
    if not target_root.is_dir():
        raise RegistryError(f"Source directory does not exist: {target_root}")
    registry_path = root / DEFAULT_REGISTRY_PATH
    original_registry = registry_path.read_bytes()
    try:
        registry = ProjectRegistry.model_validate_json(original_registry)
    except ValidationError as error:
        raise RegistryError(f"Cannot relocate invalid project registry: {error}") from error
    if Path(registry.source_directory) != source_relative:
        raise RegistryError(
            "The selected folder does not match the source directory recorded by the project."
        )

    moves: list[tuple[Path, Path]] = []
    for entry in registry.documents:
        try:
            entry.source_path = Path(entry.source_path).relative_to(source_relative).as_posix()
        except ValueError as error:
            raise RegistryError(
                f"Document {entry.document_id} is outside the selected source directory."
            ) from error
        source_data = root / entry.package_path
        target_data = target_root / "documents" / entry.document_id
        if source_data.resolve() != target_data.resolve():
            moves.append((source_data, target_data))
        entry.package_path = f"documents/{entry.document_id}"
        entry.metadata_path = f"{entry.package_path}/metadata.json"
    registry.source_directory = "."
    moves.append((root / ".heva", target_root / ".heva"))
    source_exports = root / "exports"
    if source_exports.exists():
        moves.append((source_exports, target_root / "exports"))

    for source, target in moves:
        if not source.exists():
            continue
        if target.exists():
            raise RegistryError(f"Cannot relocate project: {target} already exists.")

    completed: list[tuple[Path, Path]] = []
    try:
        for source, target in moves:
            if not source.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(target))
            completed.append((source, target))
        _write_registry(target_root / DEFAULT_REGISTRY_PATH, registry)
    except OSError as error:
        target_registry = target_root / DEFAULT_REGISTRY_PATH
        if target_registry.exists():
            target_registry.write_bytes(original_registry)
        for source, target in reversed(completed):
            source.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(target), str(source))
        raise RegistryError(f"Cannot relocate HEVA project: {error}") from error
    return target_root


def _checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative_posix(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _new_document_id(source_path: str, occupied: dict[str, str]) -> str:
    digest = hashlib.sha256(source_path.encode("utf-8")).hexdigest().upper()
    length = 12
    while True:
        candidate = f"HEVA-{digest[:length]}"
        owner = occupied.get(candidate)
        if owner is None or owner == source_path:
            return candidate
        length += 4
        if length > len(digest):
            raise RegistryError(f"Could not assign a unique document ID for {source_path}")


def _read_registry(path: Path, source_directory: str) -> ProjectRegistry:
    if not path.exists():
        return ProjectRegistry(
            source_directory=source_directory,
            documents=[],
            summary=RegistrySummary(
                total=0,
                backlog=0,
                in_progress=0,
                in_review=0,
                done=0,
                changed=0,
                missing=0,
            ),
        )
    try:
        decoded = json.loads(path.read_text(encoding="utf-8"))
        registry = ProjectRegistry.model_validate(decoded)
    except (OSError, json.JSONDecodeError, ValidationError) as error:
        raise RegistryError(f"Cannot read registry {path}: {error}") from error
    if registry.registry_version != REGISTRY_VERSION:
        raise RegistryError(
            f"Unsupported registry version {registry.registry_version}; expected {REGISTRY_VERSION}."
        )
    if registry.source_directory != source_directory:
        raise RegistryError(
            "The configured source directory does not match the existing registry: "
            f"{source_directory!r} != {registry.source_directory!r}."
        )
    return registry


def _write_registry(path: Path, registry: ProjectRegistry) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(registry.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _create_package_directories(root: Path, documents: list[DocumentEntry]) -> None:
    """Create canonical document-data directories and metadata templates."""

    # Imported here to avoid coupling registry model import-time initialization to the
    # richer package contract. Synchronization is the point at which both are needed.
    from heva.workflow.document_metadata import PackageMetadata

    for entry in documents:
        package_directory = root / entry.package_path
        package_directory.mkdir(parents=True, exist_ok=True)
        metadata_relative = f"{entry.package_path}/metadata.json"
        metadata_file = root / metadata_relative
        entry.metadata_path = metadata_relative
        if metadata_file.exists():
            continue
        metadata = PackageMetadata(document_id=entry.document_id)
        metadata_file.write_text(
            json.dumps(metadata.model_dump(mode="json"), indent=2, ensure_ascii=False)
            + "\n",
            encoding="utf-8",
        )


def _discover_sources(source_root: Path) -> list[Path]:
    if not source_root.exists() or not source_root.is_dir():
        raise RegistryError(f"Source directory does not exist: {source_root}")
    return sorted(
        (
            path
            for path in source_root.rglob("*")
            if path.is_file()
            and path.suffix.lower() in SUPPORTED_SUFFIXES
            and not path.name.startswith("~$")
        ),
        key=lambda path: path.as_posix(),
    )


def _summarize(documents: list[DocumentEntry]) -> RegistrySummary:
    return RegistrySummary(
        total=len(documents),
        backlog=sum(entry.status == "backlog" for entry in documents),
        in_progress=sum(entry.status == "in_progress" for entry in documents),
        in_review=sum(entry.status == "in_review" for entry in documents),
        done=sum(entry.status == "done" for entry in documents),
        changed=sum(entry.source_state == "changed" for entry in documents),
        missing=sum(entry.source_state == "missing" for entry in documents),
    )


def sync_registry(
    project_root: str | Path,
    *,
    source_dir: str | Path = ".",
    registry_path: str | Path = DEFAULT_REGISTRY_PATH,
) -> SyncReport:
    """Create or synchronize a registry without renaming or modifying source files."""

    root = Path(project_root).resolve()
    source_relative = Path(source_dir)
    if source_relative.is_absolute():
        raise RegistryError("source_dir must be relative to the project root.")
    source_name = source_relative.as_posix()
    source_root = root / source_relative
    registry_relative = Path(registry_path)
    if registry_relative.is_absolute():
        raise RegistryError("registry_path must be relative to the project root.")
    if registry_relative == DEFAULT_REGISTRY_PATH:
        migrate_project_layout(root)
    registry_file = root / registry_relative

    registry = _read_registry(registry_file, source_name)
    external_entries = [entry for entry in registry.documents if entry.source_binding == "external"]
    existing = {
        entry.source_path: entry
        for entry in registry.documents
        if entry.source_binding == "project"
    }
    occupied = {entry.document_id: entry.source_path for entry in registry.documents}
    discovered = {
        _relative_posix(path, root): path for path in _discover_sources(source_root)
    }

    added = 0
    unchanged = 0
    changed: list[str] = []
    documents: list[DocumentEntry] = list(external_entries)

    for source_path, physical_path in discovered.items():
        observed_checksum = _checksum(physical_path)
        entry = existing.get(source_path)
        if entry is None:
            document_id = _new_document_id(source_path, occupied)
            occupied[document_id] = source_path
            documents.append(
                DocumentEntry(
                    document_id=document_id,
                    source_path=source_path,
                    package_path=f"{DATA_DOCUMENTS_DIRECTORY.as_posix()}/{document_id}",
                    checksum_sha256=observed_checksum,
                )
            )
            added += 1
        elif entry.checksum_sha256 == observed_checksum:
            documents.append(
                entry.model_copy(
                    update={"source_state": "present", "observed_checksum_sha256": None}
                )
            )
            unchanged += 1
        else:
            documents.append(
                entry.model_copy(
                    update={
                        "source_state": "changed",
                        "observed_checksum_sha256": observed_checksum,
                    }
                )
            )
            changed.append(source_path)

    missing = sorted(set(existing) - set(discovered))
    for source_path in missing:
        documents.append(
            existing[source_path].model_copy(
                update={"source_state": "missing", "observed_checksum_sha256": None}
            )
        )

    documents.sort(key=lambda entry: entry.source_path)
    updated = ProjectRegistry(
        registry_version=REGISTRY_VERSION,
        source_directory=source_name,
        documents=documents,
        summary=_summarize(documents),
    )
    _create_package_directories(root, documents)
    _write_registry(registry_file, updated)
    return SyncReport(
        registry_path=registry_relative.as_posix(),
        added=added,
        unchanged=unchanged,
        changed=tuple(sorted(changed)),
        missing=tuple(missing),
        total=len(documents),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Initialize or synchronize a HEVA registry.")
    parser.add_argument("project_root", nargs="?", default=".")
    parser.add_argument("--source-dir", default="data")
    parser.add_argument("--registry", default=DEFAULT_REGISTRY_PATH.as_posix())
    parser.add_argument("--json", action="store_true", help="Print the summary as JSON.")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    """Synchronize a project and return a script-friendly exit status."""

    args = _build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        report = sync_registry(
            args.project_root,
            source_dir=args.source_dir,
            registry_path=args.registry,
        )
    except RegistryError as error:
        print(f"REGISTRY ERROR: {error}")
        return 1
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(
            "HEVA registry: "
            f"{report.added} added, {report.unchanged} unchanged, "
            f"{len(report.changed)} changed, {len(report.missing)} missing, "
            f"{report.total} total."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
