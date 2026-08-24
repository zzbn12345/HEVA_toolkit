"""Project setup, annotator, status, and validation routes."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Callable
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    StreamingResponse,
)
from pydantic import BaseModel, ConfigDict, StrictBool, ValidationError

from heva.workflow.annotator_registry import (
    AnnotatorRegistryError,
    activate_annotator,
    add_annotator,
    load_annotator_registry,
    remove_annotator,
    update_annotator,
)
from heva.workflow.automatic_color_proposal import (
    AutomaticColorProposalError,
    generate_automatic_color_proposals,
)
from heva.workflow.document_metadata import (
    AnnotatorMetadata,
    RightsMetadata,
)
from heva.workflow.document_contributors import (
    DocumentContributorError,
    assign_document_annotators,
    load_document_annotators,
)
from heva.workflow.document_rights import (
    DocumentRightsError,
    load_document_rights,
    save_document_rights,
)
from heva.workflow.color_mapping import (
    apply_shared_color_mapping,
    ColorMappingError,
    load_color_configuration,
    review_and_confirm_color_configuration,
    save_color_configuration,
)
from heva.workflow.color_configuration_registry import (
    ProjectColorConfigurationError,
    create_color_configuration_version,
    load_color_configuration_registry,
    select_color_configuration,
)
from heva.workflow.contract import HEVA_LABELS
from heva.workflow.document_citation import (
    CitationDraft,
    CitationError,
    confirm_document_citation,
    load_document_citation,
    save_document_citation,
)
from heva.workflow.dataset_metadata import (
    DatasetMetadataError,
    load_dataset_metadata,
    save_dataset_metadata,
)
from heva.workflow.package_validator import (
    DatasetReleaseMetadata,
    PackageValidationError,
    build_release,
    validate_project,
)
from heva.workflow.people_registry import (
    PeopleRegistryError,
    PersonRecord,
    activate_curator,
    add_person,
    load_people_registry,
    remove_person,
    update_person,
)
from heva.workflow.people_import import PeopleImportError, import_people_csv
from heva.workflow.extraction_session import (
    ExtractionSessionError,
    load_extraction_checkpoint_status,
    run_registered_extraction,
)
from heva.workflow.extraction_draft import (
    ExtractionDraftError,
    load_extraction_draft,
    promote_extraction_draft,
    run_registered_raw_extraction,
)
from heva.workflow.project_registry import (
    DEFAULT_REGISTRY_PATH,
    LEGACY_REGISTRY_PATH,
    SUPPORTED_SUFFIXES,
    ProjectRegistry,
    RegistryError,
    load_project_registry,
    relocate_project_root_to_sources,
    register_discovered_sources,
    register_external_source,
    scan_project_sources,
    sync_registry,
)
from heva.workflow.review_queue import (
    ReviewQueueError,
    registered_source_path,
)

RELEASE_FILENAMES = frozenset(
    {
        "build-log.json",
        "datapackage.json",
        "heva-annotations.csv",
        "heva-annotations.json",
    }
)
from heva.app.project_context import ProjectContext
from heva.app.extraction_jobs import ExtractionJobRegistry
from heva.app.folder_picker import (
    FolderPickerUnavailable,
    select_local_csv_file,
    select_local_folder,
    select_local_source_file,
)


class ColorDecisionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hex: str
    label: str | None = None
    ignore_reason: str | None = None


class ColorReviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decisions: list[ColorDecisionInput]


class DocumentAnnotatorAssignment(BaseModel):
    """Explicit project-person references assigned to one source document."""

    model_config = ConfigDict(extra="forbid")

    person_ids: list[str]


class ProjectFolderInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str


class BatchColorApplyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_ids: list[str]
    confirmed: StrictBool


class DiscoveredSourcesInput(BaseModel):
    """Explicit session decision for source files found while opening a project."""

    model_config = ConfigDict(extra="forbid")

    source_paths: list[str]


class ProjectPaletteMappingInput(BaseModel):
    """One safe form row in a reusable project palette."""

    model_config = ConfigDict(extra="forbid")

    label: str
    hexes: list[str]


class ProjectPaletteInput(BaseModel):
    """Fields required to append one immutable project palette version."""

    model_config = ConfigDict(extra="forbid")

    configuration_id: str
    name: str
    description: str | None = None
    mappings: list[ProjectPaletteMappingInput]


class ProjectPaletteSelectionInput(BaseModel):
    """Reference to one exact immutable palette version."""

    model_config = ConfigDict(extra="forbid")

    configuration_id: str
    version: int


def create_project_router(
    root: ProjectContext,
    template: Callable[[str], str],
) -> APIRouter:
    router = APIRouter()
    extraction_jobs = ExtractionJobRegistry()

    def active_curator_name() -> str:
        """Prefer the explicit people registry while retaining legacy-project fallback."""

        curator = load_people_registry(root).active_curator()
        if curator is not None:
            return curator.name
        legacy = load_annotator_registry(root).active()
        return legacy.name if legacy and legacy.name else ""

    @router.get("/", response_class=HTMLResponse)
    def home():
        if root.selected:
            return RedirectResponse("/review", status_code=303)
        return template("home.html")

    @router.get("/validate", response_class=HTMLResponse)
    def validation_page() -> str:
        return template("validate.html")

    @router.get("/create", response_class=HTMLResponse)
    def creation_page() -> str:
        return template("create.html")

    @router.get("/annotator", response_class=HTMLResponse)
    def annotator_page() -> str:
        return template("people.html")

    @router.get("/people", response_class=HTMLResponse)
    def people_page() -> str:
        return template("people.html")

    @router.get("/project-colors", response_class=HTMLResponse)
    def project_colors_page() -> str:
        return template("project_colors.html")

    @router.get("/dataset-metadata", response_class=HTMLResponse)
    def dataset_metadata_page() -> str:
        return template("dataset_metadata.html")

    @router.get("/documents/{document_id}/rights", response_class=HTMLResponse)
    def document_rights_page(document_id: str) -> str:
        return template("document_rights.html").replace(
            "DOCUMENT_ID_PLACEHOLDER",
            document_id,
        )

    @router.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @router.post("/api/app/shutdown")
    def shutdown_app(request: Request, background_tasks: BackgroundTasks):
        """Gracefully stop only a locally bound HEVA server after sending the response."""

        client_host = request.client.host if request.client else None
        if client_host not in {"127.0.0.1", "::1", "testclient"}:
            raise HTTPException(status_code=403, detail="HEVA can only be stopped locally.")
        handler = getattr(request.app.state, "shutdown_handler", None)
        if handler is None:
            raise HTTPException(
                status_code=501,
                detail="Use Ctrl+C in the HEVA terminal to stop this server.",
            )
        background_tasks.add_task(handler)
        return {"stopping": True, "message": "HEVA is stopping safely."}

    @router.post("/api/folders/select")
    def select_folder() -> dict[str, str | bool]:
        """Open a native chooser without uploading or copying project files."""

        try:
            selected = select_local_folder("Choose a HEVA project folder")
        except FolderPickerUnavailable as error:
            raise HTTPException(status_code=501, detail=str(error)) from error
        if selected is None:
            return {"selected": False, "path": ""}
        return {"selected": True, "path": selected}

    @router.post("/api/files/select-source")
    def select_source_file() -> dict[str, str | bool]:
        """Choose and register an external source without copying it into the dataset."""

        try:
            selected = select_local_source_file("Choose an annotated PDF or DOCX")
        except FolderPickerUnavailable as error:
            raise HTTPException(status_code=501, detail=str(error)) from error
        if selected is None:
            return {"selected": False, "document_id": "", "filename": ""}
        try:
            document_id = register_external_source(root.require(), selected)
        except RegistryError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return {"selected": True, "document_id": document_id, "filename": Path(selected).name}

    def validated_folder(value: str) -> Path:
        candidate = Path(value).expanduser().resolve()
        if not candidate.exists() or not candidate.is_dir():
            raise HTTPException(
                status_code=422,
                detail="Choose an existing local folder.",
            )
        return candidate

    def existing_project_root(candidate: Path) -> Path:
        """Open the selected source folder, relocating a former parent-root project."""

        if (candidate / DEFAULT_REGISTRY_PATH).is_file() or (
            candidate / LEGACY_REGISTRY_PATH
        ).is_file():
            return candidate
        parent = candidate.parent
        if (parent / DEFAULT_REGISTRY_PATH).is_file() or (
            parent / LEGACY_REGISTRY_PATH
        ).is_file():
            registry = load_project_registry(parent)
            recorded_sources = (parent / registry.source_directory).resolve()
            if recorded_sources == candidate:
                return relocate_project_root_to_sources(parent, registry.source_directory)
        return candidate

    @router.post("/api/projects/open")
    def open_project(payload: ProjectFolderInput):
        try:
            candidate = existing_project_root(validated_folder(payload.path))
        except RegistryError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        if not (candidate / DEFAULT_REGISTRY_PATH).is_file() and not (
            candidate / LEGACY_REGISTRY_PATH
        ).is_file():
            raise HTTPException(
                status_code=422,
                detail="This folder is not a HEVA project. Create it from source data first.",
            )
        try:
            registry = load_project_registry(candidate)
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=422,
                detail="This folder is not a HEVA project. Create it from source data first.",
            ) from error
        except (OSError, ValidationError, RegistryError) as error:
            raise HTTPException(
                status_code=422,
                detail=f"The HEVA project registry is invalid: {error}",
            ) from error
        root.select(candidate)
        scan = scan_project_sources(candidate)
        return {
            "project_name": candidate.name,
            "source_directory": registry.source_directory,
            "document_count": registry.summary.total,
            "source_scan": {
                "discovered": list(scan.discovered),
                "changed": list(scan.changed),
                "missing": list(scan.missing),
            },
        }

    @router.get("/api/projects/source-scan")
    def source_scan():
        scan = scan_project_sources(root.require())
        return {
            "discovered": [
                path for path in scan.discovered if path not in root.dismissed_sources
            ],
            "changed": list(scan.changed),
            "missing": list(scan.missing),
        }

    @router.post("/api/projects/source-scan/accept")
    def accept_discovered_sources(payload: DiscoveredSourcesInput):
        try:
            document_ids = register_discovered_sources(root.require(), payload.source_paths)
        except RegistryError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return {"registered_document_ids": list(document_ids)}

    @router.post("/api/projects/source-scan/dismiss")
    def dismiss_discovered_sources(payload: DiscoveredSourcesInput):
        scan = scan_project_sources(root.require())
        invalid = sorted(set(payload.source_paths) - set(scan.discovered))
        if invalid:
            raise HTTPException(status_code=422, detail="Only newly discovered sources can be dismissed.")
        root.dismiss_sources(payload.source_paths)
        return {"dismissed": payload.source_paths, "scope": "current_session"}

    @router.post("/api/projects/create")
    def create_project(payload: ProjectFolderInput):
        candidate = validated_folder(payload.path)
        parent = candidate.parent
        if (parent / DEFAULT_REGISTRY_PATH).is_file() or (
            parent / LEGACY_REGISTRY_PATH
        ).is_file():
            try:
                parent_registry = load_project_registry(parent)
            except RegistryError as error:
                raise HTTPException(status_code=422, detail=str(error)) from error
            if (parent / parent_registry.source_directory).resolve() == candidate:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "This folder already contains the sources of a HEVA project. "
                        "Open it to move the workspace into this folder safely."
                    ),
                )
        if (candidate / DEFAULT_REGISTRY_PATH).exists() or (
            candidate / LEGACY_REGISTRY_PATH
        ).exists():
            raise HTTPException(
                status_code=409,
                detail="This folder already contains a HEVA project. Open it instead.",
            )
        has_sources = any(
            path.is_file()
            and path.suffix.lower() in SUPPORTED_SUFFIXES
            and not path.name.startswith("~$")
            for path in candidate.rglob("*")
        )
        if not has_sources:
            raise HTTPException(
                status_code=422,
                detail="No PDF or DOCX source documents were found in this folder.",
            )
        try:
            report = sync_registry(candidate, source_dir=".")
        except RegistryError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        root.select(candidate)
        return {
            "project_name": candidate.name,
            "source_directory": ".",
            "document_count": report.total,
        }

    @router.post("/api/projects/close")
    def close_project():
        root.close()
        return {"closed": True}

    @router.get("/api/project")
    def project_status():
        if not root.selected:
            return JSONResponse(
                {
                    "code": "no_active_project",
                    "message": "No HEVA project is open.",
                    "action": "Open an existing project or create one from a source folder.",
                },
                status_code=404,
            )
        try:
            registry = load_project_registry(root.require())
        except (FileNotFoundError, RegistryError):
            return JSONResponse(
                {
                    "code": "project_not_initialized",
                    "message": "This folder is not a HEVA project yet.",
                    "action": "Choose Create project to register the source documents.",
                },
                status_code=404,
            )
        except (OSError, ValidationError) as error:
            return JSONResponse(
                {
                    "code": "invalid_project_registry",
                    "message": "The project registry cannot be read.",
                    "action": "Restore or correct .heva/project.json.",
                    "detail": str(error),
                },
                status_code=422,
            )
        return {
            "project_name": root.require().name,
            "source_directory": registry.source_directory,
            "summary": registry.summary.model_dump(mode="json"),
            "documents": [
                {
                    "document_id": item.document_id,
                    "source_path": item.source_path,
                    "status": item.status,
                    "source_state": item.source_state,
                }
                for item in registry.documents
            ],
        }

    @router.get("/api/documents/{document_id}")
    def document_status(document_id: str):
        try:
            registry = load_project_registry(root.require())
        except (OSError, ValidationError) as error:
            raise HTTPException(
                status_code=422,
                detail="The project registry cannot be read.",
            ) from error
        entry = next(
            (item for item in registry.documents if item.document_id == document_id),
            None,
        )
        if entry is None:
            raise HTTPException(status_code=404, detail="Document is not registered.")
        return {
            "document_id": entry.document_id,
            "source_path": entry.source_path,
            "filename": Path(entry.source_path).name,
            "source_format": Path(entry.source_path).suffix.lower().lstrip("."),
            "status": entry.status,
            "source_state": entry.source_state,
            "preview_available": Path(entry.source_path).suffix.lower() == ".pdf",
        }

    @router.get("/api/documents/{document_id}/source")
    def document_source(document_id: str):
        try:
            source = registered_source_path(root, document_id)
        except ReviewQueueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        if source.suffix.lower() != ".pdf":
            raise HTTPException(
                status_code=415,
                detail="Inline preview currently supports PDF sources only.",
            )
        return FileResponse(
            source,
            media_type="application/pdf",
            filename=source.name,
            content_disposition_type="inline",
        )

    @router.get("/api/documents/{document_id}/annotators")
    def document_annotators(document_id: str):
        """Return eligible project people and explicit assignments for a document."""

        try:
            people = load_people_registry(root)
            assigned = load_document_annotators(root, document_id)
        except (PeopleRegistryError, DocumentContributorError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return {
            "assigned_person_ids": [item.person_id for item in assigned],
            "annotators": [
                person.model_dump(mode="json")
                for person in people.people
                if "annotator" in person.roles
            ],
        }

    @router.put("/api/documents/{document_id}/annotators")
    def replace_document_annotators(
        document_id: str,
        assignment: DocumentAnnotatorAssignment,
    ):
        """Persist explicit original-annotator references and public snapshots."""

        try:
            assigned = assign_document_annotators(
                root,
                document_id,
                assignment.person_ids,
            )
        except (PeopleRegistryError, DocumentContributorError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return {
            "assigned_person_ids": [item.person_id for item in assigned],
            "original_annotators": [item.model_dump(mode="json") for item in assigned],
        }

    @router.get("/api/documents/{document_id}/citation/schema")
    def citation_schema(document_id: str):
        # Resolve the record first so schemas are not exposed for unknown documents.
        try:
            load_document_citation(root, document_id)
        except CitationError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return CitationDraft.model_json_schema()

    @router.get("/api/documents/{document_id}/citation")
    def citation_status(document_id: str):
        try:
            return load_document_citation(root, document_id).model_dump(mode="json")
        except CitationError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @router.put("/api/documents/{document_id}/citation")
    def save_citation(document_id: str, citation: CitationDraft):
        try:
            return save_document_citation(root, document_id, citation).model_dump(
                mode="json"
            )
        except CitationError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.post("/api/documents/{document_id}/citation/confirm")
    def confirm_citation(document_id: str, citation: CitationDraft):
        try:
            return confirm_document_citation(
                root,
                document_id,
                citation,
                confirmed_by=active_curator_name(),
            ).model_dump(mode="json")
        except (AnnotatorRegistryError, PeopleRegistryError, CitationError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.get("/api/documents/{document_id}/colors")
    def color_status(document_id: str):
        try:
            configuration = load_color_configuration(root, document_id)
        except ColorMappingError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return {
            "document_id": document_id,
            "labels": sorted(HEVA_LABELS),
            "configuration": configuration.model_dump(mode="json"),
            "automatic_proposal_available": (
                not configuration.human_confirmed
                and any(
                    color.status == "pending_review"
                    and color.suggested_label is None
                    for color in configuration.colors
                )
            ),
        }

    @router.post("/api/documents/{document_id}/colors/discover")
    def discover_colors(document_id: str):
        """Extract raw evidence and populate the document-local color review."""

        try:
            run_registered_raw_extraction(root, document_id)
            draft = load_extraction_draft(root, document_id)
            configuration = load_color_configuration(root, document_id)
        except ModuleNotFoundError as error:
            dependency = error.name or "an extraction dependency"
            return JSONResponse(
                {
                    "code": "extraction_dependency_missing",
                    "message": "Color discovery is not fully installed.",
                    "action": (
                        f"The required Python package '{dependency}' is missing. "
                        "Install HEVA with its extraction dependencies and restart the server."
                    ),
                },
                status_code=503,
            )
        except (
            ColorMappingError,
            ExtractionDraftError,
            PeopleRegistryError,
            RegistryError,
            OSError,
            ValidationError,
        ) as error:
            return JSONResponse(
                {
                    "code": getattr(error, "code", "color_discovery_failed"),
                    "message": "Colors could not be discovered from this document.",
                    "action": str(error),
                },
                status_code=422,
            )
        return {
            "document_id": document_id,
            "color_count": len(configuration.colors),
            "sentence_count": len(draft.sentences),
            "message": "Observed colors are ready for human review.",
        }

    @router.post("/api/documents/{document_id}/colors/propose")
    def propose_colors(document_id: str):
        try:
            proposed = generate_automatic_color_proposals(root, document_id)
        except AutomaticColorProposalError as error:
            return JSONResponse(
                {
                    "code": "automatic_color_proposal_failed",
                    "message": "Automatic color proposals were not created.",
                    "action": str(error),
                },
                status_code=422,
            )
        return {
            "document_id": document_id,
            "proposed_color_count": proposed,
            "message": "Automatic suggestions are ready for human review.",
        }

    @router.post("/api/documents/{document_id}/colors/confirm")
    def confirm_colors(document_id: str, payload: ColorReviewInput):
        """Confirm color semantics and immediately promote any saved raw evidence."""

        try:
            configuration = review_and_confirm_color_configuration(
                root,
                document_id,
                [decision.model_dump() for decision in payload.decisions],
                confirmed_by=active_curator_name(),
            )
            values = {
                color.hex: color.label
                for color in configuration.colors
                if color.status == "approved" and color.label is not None
            }
            project_registry = load_color_configuration_registry(root)
            reusable = next(
                (item for item in project_registry.configurations if item.values == values),
                None,
            )
            if reusable is None:
                by_label: dict[str, list[str]] = {}
                for color, label in values.items():
                    by_label.setdefault(label, []).append(color)
                reusable = create_color_configuration_version(
                    root,
                    configuration_id="project-palette",
                    name="Project palette",
                    description="Created from a curator-confirmed document color configuration.",
                    mappings=[
                        {"label": label, "hexes": hexes}
                        for label, hexes in sorted(by_label.items())
                    ],
                )
            select_color_configuration(root, reusable.configuration_id, reusable.version)
            configuration.configuration_id = reusable.configuration_id
            configuration.configuration_version = reusable.version
            save_color_configuration(root, document_id, configuration)
        except (AnnotatorRegistryError, PeopleRegistryError, ColorMappingError, ProjectColorConfigurationError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        response = configuration.model_dump(mode="json")
        try:
            draft = load_extraction_draft(root, document_id)
        except ExtractionDraftError:
            draft = None
        if draft is not None and draft.sentences:
            try:
                compiled = promote_extraction_draft(root, document_id)
                response["canonical_annotations"] = {
                    "status": "canonical_saved",
                    "record_count": compiled.record_count,
                    "warnings": list(compiled.warnings),
                }
            except (
                ColorMappingError,
                ProjectColorConfigurationError,
                ExtractionDraftError,
                ExtractionSessionError,
                PeopleRegistryError,
                RegistryError,
                OSError,
                ValidationError,
            ) as error:
                response["canonical_annotations"] = {
                    "status": "failed",
                    "record_count": 0,
                    "warnings": [str(error)],
                }
        else:
            response["canonical_annotations"] = {
                "status": "not_available",
                "record_count": 0,
                "warnings": [],
            }
        return response

    @router.get("/api/documents/{document_id}/colors/batch")
    def batch_color_candidates(document_id: str):
        try:
            source = load_color_configuration(root, document_id)
            registry = load_project_registry(root.require())
        except (ColorMappingError, OSError, ValidationError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        source_palette = {color.hex for color in source.colors}
        candidates = []
        for entry in registry.documents:
            if entry.document_id == document_id:
                continue
            try:
                target = load_color_configuration(root, entry.document_id)
                palette_matches = {
                    color.hex for color in target.colors
                } == source_palette
                eligible = (
                    source.human_confirmed
                    and palette_matches
                    and not target.human_confirmed
                )
                if target.human_confirmed:
                    reason = "This document already has its own confirmed mapping."
                elif not palette_matches:
                    reason = "Palette mismatch; review this document independently."
                elif not source.human_confirmed:
                    reason = "Confirm the source mapping before sharing it."
                else:
                    reason = "Exact palette match; eligible for supervised reuse."
            except ColorMappingError as error:
                palette_matches = False
                eligible = False
                reason = str(error)
            candidates.append(
                {
                    "document_id": entry.document_id,
                    "source_path": entry.source_path,
                    "palette_matches": palette_matches,
                    "eligible": eligible,
                    "reason": reason,
                }
            )
        return {
            "source_document_id": document_id,
            "source_confirmed": source.human_confirmed,
            "candidates": candidates,
        }

    @router.post("/api/documents/{document_id}/colors/batch")
    def apply_batch_colors(document_id: str, payload: BatchColorApplyInput):
        if not payload.confirmed:
            raise HTTPException(
                status_code=422,
                detail="Confirm that the selected documents share the inspected palette.",
            )
        try:
            applied = apply_shared_color_mapping(
                root,
                document_id,
                payload.document_ids,
                confirmed_by=active_curator_name(),
            )
        except (AnnotatorRegistryError, PeopleRegistryError, ColorMappingError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return {
            "source_document_id": document_id,
            "applied_document_ids": list(applied),
        }

    @router.get("/api/documents/{document_id}/extraction")
    def extraction_status(document_id: str):
        try:
            status = load_extraction_checkpoint_status(root, document_id)
        except ExtractionSessionError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        try:
            draft = load_extraction_draft(root, document_id)
            draft_count = len(draft.sentences)
        except ExtractionDraftError:
            draft_count = 0
        return {
            "document_id": status.document_id,
            "state": status.state,
            "record_count": status.record_count,
            "completed_at": status.completed_at,
            "mapping_status": status.mapping_status,
            "warnings": list(status.warnings),
            "stale_reasons": list(status.stale_reasons),
            "draft_record_count": draft_count,
        }

    @router.get("/api/documents/{document_id}/extraction/progress")
    def extraction_progress(document_id: str):
        """Report live stages for extraction started by this application process."""

        job = extraction_jobs.get(document_id)
        if job is None:
            return {
                "document_id": document_id,
                "state": "idle",
                "stage": "idle",
                "message": "No extraction is currently running.",
                "completed_steps": 0,
                "total_steps": 3,
                "result": None,
                "error": None,
            }
        return job

    @router.post("/api/documents/{document_id}/annotations/compile")
    def compile_document_annotations(document_id: str):
        """Promote saved raw evidence without rerunning the source extractor."""

        try:
            result = promote_extraction_draft(root, document_id)
        except (
            ColorMappingError,
            ProjectColorConfigurationError,
            ExtractionDraftError,
            ExtractionSessionError,
            PeopleRegistryError,
            RegistryError,
            OSError,
            ValidationError,
        ) as error:
            return JSONResponse(
                {
                    "code": "annotation_compilation_failed",
                    "message": "Canonical annotations were not created.",
                    "action": str(error),
                },
                status_code=422,
            )
        return {
            "document_id": result.document_id,
            "record_count": result.record_count,
            "warnings": list(result.warnings),
            "status": "canonical_saved",
        }

    def run_extraction_job(document_id: str) -> None:
        """Run extraction off the request path while publishing honest stage changes."""

        try:
            extraction_jobs.update(
                document_id,
                state="running",
                stage="extracting",
                message="Reading the source and extracting colored text.",
                completed_steps=0,
            )
            run_registered_raw_extraction(root, document_id)
            extraction_jobs.update(
                document_id,
                stage="compiling",
                message="Raw evidence is saved. Building canonical HEVA annotations.",
                completed_steps=1,
            )
            try:
                result = promote_extraction_draft(root, document_id)
            except (
                ColorMappingError,
                ProjectColorConfigurationError,
                ExtractionDraftError,
                ExtractionSessionError,
            ):
                extraction_jobs.update(
                    document_id,
                    state="draft_saved",
                    stage="waiting_for_color_configuration",
                    message=(
                        "Raw extraction evidence was saved. Confirm Color config to "
                        "build canonical HEVA annotations and unlock sentence editing."
                    ),
                    completed_steps=2,
                    result={
                        "document_id": document_id,
                        "status": "draft_saved",
                        "record_count": None,
                    },
                )
                return
        except ModuleNotFoundError as error:
            dependency = error.name or "an extraction dependency"
            extraction_jobs.update(
                document_id,
                state="failed",
                stage="failed",
                message="The extraction service is not fully installed.",
                error={
                    "code": "extraction_dependency_missing",
                    "action": (
                        f"The required Python package '{dependency}' is missing. "
                        "Install HEVA with its extraction dependencies and restart the server."
                    ),
                },
            )
            return
        except (
            ColorMappingError,
            ExtractionDraftError,
            ExtractionSessionError,
            PeopleRegistryError,
            RegistryError,
            OSError,
            ValidationError,
        ) as error:
            extraction_jobs.update(
                document_id,
                state="failed",
                stage="failed",
                message="Annotations were not extracted.",
                error={
                    "code": getattr(error, "code", "extraction_failed"),
                    "action": str(error),
                },
            )
            return
        extraction_jobs.update(
            document_id,
            state="completed",
            stage="completed",
            message=f"Created {result.record_count} canonical annotation records.",
            completed_steps=3,
            result={
                "document_id": result.document_id,
                "record_count": result.record_count,
                "reused_checkpoint": result.reused_checkpoint,
                "warnings": list(result.warnings),
                "status": "canonical_saved",
            },
        )

    @router.post("/api/documents/{document_id}/extract", status_code=202)
    def extract_document(
        document_id: str,
        background_tasks: BackgroundTasks,
        force: bool = False,
    ):
        """Queue extraction and return immediately so clients can observe progress."""

        job = extraction_jobs.start(document_id)
        if job is None:
            return JSONResponse(
                {
                    "code": "extraction_already_running",
                    "message": "Extraction is already running for this document.",
                    "action": "Keep this page open to follow its current status.",
                },
                status_code=409,
            )
        background_tasks.add_task(run_extraction_job, document_id)
        return job

    @router.get("/api/annotator")
    def annotator_status():
        try:
            registry = load_annotator_registry(root)
        except AnnotatorRegistryError as error:
            return JSONResponse(
                {
                    "code": "invalid_annotator_profile",
                    "message": str(error),
                    "action": "Correct or replace .heva/annotators.json.",
                    "detail": str(error),
                },
                status_code=422,
            )
        annotator = registry.active()
        if annotator is None:
            return {
                "configured": False,
                "message": "No active annotator has been selected for this project.",
                "action": "Add or select the person responsible for reviewing the annotations.",
                "annotator": {
                    "name": None,
                    "orcid": None,
                    "affiliation": None,
                    "email": None,
                },
            }
        return {
            "configured": bool(annotator.name),
            "annotator": annotator.model_dump(mode="json"),
        }

    @router.get("/api/people/schema")
    def people_schema():
        """Expose the same person schema used for safe form validation."""

        schema = PersonRecord.model_json_schema()
        schema["required"] = ["name", "roles"]
        return {"schema": schema, "role_labels": {
            "annotator": "Original annotator",
            "curator": "Curator",
            "data_owner": "Data owner",
        }}

    @router.get("/api/people")
    def list_people():
        try:
            return load_people_registry(root).model_dump(mode="json")
        except PeopleRegistryError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.post("/api/people", status_code=201)
    def create_person(person: PersonRecord):
        try:
            return add_person(root, person).model_dump(mode="json")
        except PeopleRegistryError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.post("/api/people/import-csv")
    def import_people_spreadsheet():
        """Choose and atomically import one authoritative local people CSV."""

        try:
            selected = select_local_csv_file("Choose the authoritative HEVA people CSV")
        except FolderPickerUnavailable as error:
            raise HTTPException(status_code=501, detail=str(error)) from error
        if selected is None:
            return {"selected": False}
        try:
            registry = import_people_csv(root, selected)
        except PeopleImportError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return {
            "selected": True,
            "imported": len(registry.people),
            "registry": registry.model_dump(mode="json"),
        }

    @router.put("/api/people/{person_id}")
    def replace_person(person_id: str, person: PersonRecord):
        try:
            return update_person(root, person_id, person).model_dump(mode="json")
        except PeopleRegistryError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.post("/api/people/{person_id}/activate-curator")
    def select_active_curator(person_id: str):
        try:
            person = activate_curator(root, person_id)
            return {"active_curator_id": person.person_id}
        except PeopleRegistryError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.delete("/api/people/{person_id}")
    def delete_person(person_id: str):
        try:
            return remove_person(root, person_id).model_dump(mode="json")
        except PeopleRegistryError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.get("/api/project-colors")
    def project_color_versions():
        """List immutable palette versions and the exact active selection."""

        try:
            return load_color_configuration_registry(root).model_dump(mode="json")
        except ProjectColorConfigurationError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.post("/api/project-colors", status_code=201)
    def create_project_color_version(payload: ProjectPaletteInput):
        """Append a curator-attributed palette version without editing prior versions."""

        try:
            return create_color_configuration_version(
                root,
                configuration_id=payload.configuration_id,
                name=payload.name,
                description=payload.description,
                mappings=[mapping.model_dump() for mapping in payload.mappings],
            ).model_dump(mode="json")
        except (ValueError, ProjectColorConfigurationError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.post("/api/project-colors/select")
    def select_project_color_version(payload: ProjectPaletteSelectionInput):
        """Select one existing version without changing its semantic content."""

        try:
            selected = select_color_configuration(
                root, payload.configuration_id, payload.version
            )
            return selected.model_dump(mode="json")
        except ProjectColorConfigurationError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.put("/api/annotator")
    def save_annotator(annotator: AnnotatorMetadata):
        try:
            registry = load_annotator_registry(root)
            active = registry.active()
            saved = (
                update_annotator(root, active.annotator_id, annotator)
                if active
                else add_annotator(root, annotator)
            )
            activate_annotator(root, saved.annotator_id)
        except AnnotatorRegistryError as error:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "missing_annotator_name",
                    "message": str(error),
                    "action": "Provide the person responsible for reviewing these annotations.",
                },
            ) from error
        return {"configured": True, "annotator": saved.model_dump(mode="json")}

    @router.get("/api/annotators/schema")
    def annotator_schema():
        schema = AnnotatorMetadata.model_json_schema()
        schema["required"] = ["name"]
        return {
            "schema": schema,
            "ui_schema": {
                "type": "VerticalLayout",
                "elements": [
                    {"type": "Control", "scope": "#/properties/name"},
                    {"type": "Control", "scope": "#/properties/affiliation"},
                    {"type": "Control", "scope": "#/properties/email"},
                    {"type": "Control", "scope": "#/properties/orcid"},
                ],
            },
        }

    @router.get("/api/annotators")
    def list_annotators():
        try:
            registry = load_annotator_registry(root)
        except AnnotatorRegistryError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return registry.model_dump(mode="json")

    @router.post("/api/annotators", status_code=201)
    def create_annotator(annotator: AnnotatorMetadata):
        try:
            record = add_annotator(root, annotator)
        except AnnotatorRegistryError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return record.model_dump(mode="json")

    @router.put("/api/annotators/{annotator_id}")
    def replace_annotator(annotator_id: str, annotator: AnnotatorMetadata):
        try:
            record = update_annotator(root, annotator_id, annotator)
        except AnnotatorRegistryError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return record.model_dump(mode="json")

    @router.post("/api/annotators/{annotator_id}/activate")
    def select_annotator(annotator_id: str):
        try:
            record = activate_annotator(root, annotator_id)
        except AnnotatorRegistryError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return {"active_annotator_id": record.annotator_id}

    @router.delete("/api/annotators/{annotator_id}")
    def delete_annotator(annotator_id: str):
        try:
            registry = remove_annotator(root, annotator_id)
        except AnnotatorRegistryError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return registry.model_dump(mode="json")

    @router.post("/api/validate")
    def validate_current_project():
        try:
            report = validate_project(root)
        except PackageValidationError as error:
            return JSONResponse(
                {
                    "code": "project_validation_unavailable",
                    "message": "The project cannot be validated yet.",
                    "action": str(error),
                },
                status_code=422,
            )
        payload = report.model_dump(mode="json")
        return JSONResponse(payload, status_code=200)

    @router.get("/api/documents/{document_id}/rights")
    def get_document_rights(document_id: str):
        """Return one validated rights record for safe form editing."""

        try:
            rights = load_document_rights(root, document_id)
        except DocumentRightsError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return rights.model_dump(mode="json")

    @router.put("/api/documents/{document_id}/rights")
    def put_document_rights(document_id: str, rights: RightsMetadata):
        """Persist explicit source and derivative distribution decisions."""

        try:
            saved = save_document_rights(root, document_id, rights)
        except DocumentRightsError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return saved.model_dump(mode="json")

    @router.get("/api/dataset-metadata")
    def get_dataset_metadata():
        """Return validated dataset identity without exposing a raw JSON editor."""

        try:
            metadata = load_dataset_metadata(root)
        except DatasetMetadataError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return {
            "configured": metadata is not None,
            "metadata": metadata.model_dump(mode="json") if metadata else None,
        }

    @router.put("/api/dataset-metadata")
    def put_dataset_metadata(metadata: DatasetReleaseMetadata):
        """Validate and persist dataset-level citation and release guidance."""

        try:
            saved = save_dataset_metadata(root, metadata)
        except DatasetMetadataError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return {"configured": True, "metadata": saved.model_dump(mode="json")}

    @router.post("/api/release")
    def generate_release():
        """Build the validated annotation-only Data Package for the active project."""

        try:
            target = build_release(root)
        except (OSError, ValidationError, PackageValidationError) as error:
            return JSONResponse(
                {
                    "code": "release_not_generated",
                    "message": str(error),
                    "action": (
                        "Resolve this release requirement, then generate the Data Package "
                        "again."
                    ),
                },
                status_code=422,
            )
        files = sorted(
            path.name
            for path in target.iterdir()
            if path.is_file() and path.name in RELEASE_FILENAMES
        )
        return {"generated": True, "files": files, "download": "/api/release/download"}

    @router.get("/api/release/download")
    def download_release():
        """Rebuild and stream a deterministic ZIP without exposing local paths."""

        try:
            target = build_release(root)
        except (OSError, ValidationError, PackageValidationError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        archive = io.BytesIO()
        with ZipFile(archive, mode="w", compression=ZIP_DEFLATED) as bundle:
            for path in sorted(target.iterdir(), key=lambda item: item.name):
                if not path.is_file() or path.name not in RELEASE_FILENAMES:
                    continue
                info = ZipInfo(f"heva-data-package/{path.name}")
                info.date_time = (1980, 1, 1, 0, 0, 0)
                info.compress_type = ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                bundle.writestr(info, path.read_bytes())
        archive.seek(0)
        return StreamingResponse(
            archive,
            media_type="application/zip",
            headers={"Content-Disposition": 'attachment; filename="heva-data-package.zip"'},
        )

    return router
