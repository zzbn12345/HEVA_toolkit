"""Project setup, annotator, status, and validation routes."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
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
from heva.workflow.document_metadata import AnnotatorMetadata, citation_is_valid
from heva.workflow.color_mapping import (
    apply_shared_color_mapping,
    ColorMappingError,
    load_color_configuration,
    review_and_confirm_color_configuration,
)
from heva.workflow.contract import HEVA_LABELS
from heva.workflow.document_citation import (
    CitationDraft,
    CitationError,
    confirm_document_citation,
    load_document_citation,
    save_document_citation,
)
from heva.workflow.package_validator import (
    PackageValidationError,
    validate_project,
)
from heva.workflow.extraction_session import (
    ExtractionSessionError,
    load_extraction_checkpoint_status,
    run_registered_extraction,
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
from heva.app.project_context import ProjectContext
from heva.app.folder_picker import FolderPickerUnavailable, select_local_folder, select_local_source_file


class ColorDecisionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hex: str
    label: str | None = None
    ignore_reason: str | None = None


class ColorReviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decisions: list[ColorDecisionInput]


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


def create_project_router(
    root: ProjectContext,
    template: Callable[[str], str],
) -> APIRouter:
    router = APIRouter()

    @router.get("/", response_class=HTMLResponse)
    def home() -> str:
        return template("home.html")

    @router.get("/validate", response_class=HTMLResponse)
    def validation_page() -> str:
        return template("validate.html")

    @router.get("/curation", response_class=HTMLResponse)
    def curation_page() -> str:
        return template("curation.html")

    @router.get("/create", response_class=HTMLResponse)
    def creation_page() -> str:
        return template("create.html")

    @router.get("/annotator", response_class=HTMLResponse)
    def annotator_page() -> str:
        return template("annotator.html")

    @router.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

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
            active = load_annotator_registry(root).active()
            return confirm_document_citation(
                root,
                document_id,
                citation,
                confirmed_by=active.name if active and active.name else "",
            ).model_dump(mode="json")
        except (AnnotatorRegistryError, CitationError) as error:
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
        try:
            active = load_annotator_registry(root).active()
            configuration = review_and_confirm_color_configuration(
                root,
                document_id,
                [decision.model_dump() for decision in payload.decisions],
                confirmed_by=active.name if active and active.name else "",
            )
        except (AnnotatorRegistryError, ColorMappingError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return configuration.model_dump(mode="json")

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
            "source_confirmed": citation_is_valid(source),
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
            active = load_annotator_registry(root).active()
            applied = apply_shared_color_mapping(
                root,
                document_id,
                payload.document_ids,
                confirmed_by=active.name if active and active.name else "",
            )
        except (AnnotatorRegistryError, ColorMappingError) as error:
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
        return {
            "document_id": status.document_id,
            "state": status.state,
            "record_count": status.record_count,
            "completed_at": status.completed_at,
            "mapping_status": status.mapping_status,
            "warnings": list(status.warnings),
            "stale_reasons": list(status.stale_reasons),
        }

    @router.post("/api/documents/{document_id}/extract")
    def extract_document(document_id: str, force: bool = False):
        try:
            result = run_registered_extraction(root, document_id, force=force)
        except (ColorMappingError, ExtractionSessionError, OSError, ValidationError) as error:
            return JSONResponse(
                {
                    "code": getattr(error, "code", "extraction_failed"),
                    "message": "Annotations were not extracted.",
                    "action": str(error),
                },
                status_code=422,
            )
        return {
            "document_id": result.document_id,
            "record_count": result.record_count,
            "reused_checkpoint": result.reused_checkpoint,
            "warnings": list(result.warnings),
        }

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

    return router
