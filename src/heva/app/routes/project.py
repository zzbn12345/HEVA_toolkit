"""Project setup, annotator, status, and validation routes."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import ValidationError

from heva.workflow.annotator_registry import (
    AnnotatorRegistryError,
    activate_annotator,
    add_annotator,
    load_annotator_registry,
    remove_annotator,
    update_annotator,
)
from heva.workflow.document_metadata import AnnotatorMetadata
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
from heva.workflow.project_registry import DEFAULT_REGISTRY_PATH, ProjectRegistry
from heva.workflow.review_queue import (
    ReviewQueueError,
    registered_source_path,
)


def create_project_router(
    root: Path,
    template: Callable[[str], str],
) -> APIRouter:
    router = APIRouter()

    @router.get("/", response_class=HTMLResponse)
    def home() -> str:
        return template("home.html")

    @router.get("/validate", response_class=HTMLResponse)
    def validation_page() -> str:
        return template("validate.html")

    @router.get("/create", response_class=HTMLResponse)
    def creation_page() -> str:
        return template("create.html")

    @router.get("/annotator", response_class=HTMLResponse)
    def annotator_page() -> str:
        return template("annotator.html")

    @router.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/api/project")
    def project_status():
        registry_path = root / DEFAULT_REGISTRY_PATH
        try:
            registry = ProjectRegistry.model_validate_json(
                registry_path.read_text(encoding="utf-8")
            )
        except FileNotFoundError:
            return JSONResponse(
                {
                    "code": "project_not_initialized",
                    "message": "This folder is not a HEVA project yet.",
                    "action": "Choose Create package to register the project documents.",
                },
                status_code=404,
            )
        except (OSError, ValidationError) as error:
            return JSONResponse(
                {
                    "code": "invalid_project_registry",
                    "message": "The project registry cannot be read.",
                    "action": "Restore or correct data/project-registry.json.",
                    "detail": str(error),
                },
                status_code=422,
            )
        return {
            "project_root": str(root),
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
            registry = ProjectRegistry.model_validate_json(
                (root / DEFAULT_REGISTRY_PATH).read_text(encoding="utf-8")
            )
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

    @router.get("/api/annotator")
    def annotator_status():
        try:
            registry = load_annotator_registry(root)
        except AnnotatorRegistryError as error:
            return JSONResponse(
                {
                    "code": "invalid_annotator_profile",
                    "message": str(error),
                    "action": "Correct or replace data/annotators.json.",
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
        return JSONResponse(payload, status_code=200 if report.valid else 422)

    return router
