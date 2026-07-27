"""Project setup, annotator, status, and validation routes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import ValidationError

from management.heva_management.document_metadata import AnnotatorMetadata
from management.heva_management.package_validator import (
    PackageValidationError,
    validate_project,
)
from management.heva_management.project_registry import DEFAULT_REGISTRY_PATH, ProjectRegistry


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

    @router.get("/api/annotator")
    def annotator_status():
        path = root / "data" / "annotator.json"
        if not path.exists():
            return {"configured": False, "annotator": {"name": None, "orcid": None}}
        try:
            annotator = AnnotatorMetadata.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except (OSError, ValidationError) as error:
            return JSONResponse(
                {
                    "code": "invalid_annotator_profile",
                    "message": "The saved annotator profile cannot be read.",
                    "action": "Correct or replace data/annotator.json.",
                    "detail": str(error),
                },
                status_code=422,
            )
        return {
            "configured": bool(annotator.name),
            "annotator": annotator.model_dump(mode="json"),
        }

    @router.put("/api/annotator")
    def save_annotator(annotator: AnnotatorMetadata):
        if not annotator.name or not annotator.name.strip():
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "missing_annotator_name",
                    "message": "Enter the annotator’s name.",
                    "action": "Provide the person responsible for reviewing these annotations.",
                },
            )
        normalized = annotator.model_copy(update={"name": annotator.name.strip()})
        path = root / "data" / "annotator.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(normalized.model_dump(mode="json"), indent=2, ensure_ascii=False)
            + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
        return {"configured": True, "annotator": normalized.model_dump(mode="json")}

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
