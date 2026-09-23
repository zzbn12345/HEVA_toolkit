"""Document queue, source preview, and sentence decision routes."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import ValidationError

from heva.curation.annotator_registry import (
    AnnotatorRegistryError,
    load_annotator_registry,
)
from heva.curation.people_registry import PeopleRegistryError, load_people_registry
from heva.curation.package_validator import (
    PackageValidationError,
    validate_document_package,
)
from heva.curation.project_registry import (
    RegistryError,
    register_discovered_sources,
    scan_project_sources,
)
from heva.curation.review_queue import (
    ReviewQueueError,
    list_review_queue,
    load_review_document,
    registered_source_path,
)
from heva.curation.review_state import (
    ReviewError,
    accept_quality_warning,
    record_decisions,
    replace_sentence_record,
)


def create_review_router(
    root: Path,
    template: Callable[[str], str],
) -> APIRouter:
    router = APIRouter()

    def active_reviewer_name() -> str:
        """Resolve the active curator, retaining legacy-project compatibility."""

        curator = load_people_registry(root).active_curator()
        if curator is not None:
            return curator.name
        legacy = load_annotator_registry(root).active()
        if legacy is not None and legacy.name:
            return legacy.name
        raise ValueError(
            "Select an active curator in People and roles before changing review data."
        )

    @router.get("/review", response_class=HTMLResponse)
    def review_queue_page() -> str:
        return template("review_queue.html")

    @router.get("/review/{document_id}", response_class=HTMLResponse)
    def review_document_page(document_id: str, embedded: bool = False) -> str:
        """Render standalone navigation or only review content for the document workflow."""

        return (
            template("review_document.html")
            .replace("DOCUMENT_ID_PLACEHOLDER", document_id)
            .replace("EMBEDDED_CLASS_PLACEHOLDER", "embedded-review" if embedded else "")
        )

    @router.get("/api/review-queue")
    def review_queue():
        try:
            scan = scan_project_sources(root.require())
            added_document_ids = (
                register_discovered_sources(root.require(), scan.discovered)
                if scan.discovered
                else ()
            )
            items = list_review_queue(root)
        except (RegistryError, ReviewQueueError, ValidationError) as error:
            return JSONResponse(
                {
                    "code": "review_queue_unavailable",
                    "message": "The document review queue cannot be loaded.",
                    "action": str(error),
                },
                status_code=422,
            )
        return {
            "documents": [item.model_dump(mode="json") for item in items],
            "added_document_ids": list(added_document_ids),
        }

    @router.get("/api/review/{document_id}")
    def review_document(document_id: str):
        try:
            return load_review_document(root, document_id)
        except (ReviewQueueError, ValidationError) as error:
            return JSONResponse(
                {
                    "code": "document_review_unavailable",
                    "message": "This document cannot be opened for review.",
                    "action": str(error),
                },
                status_code=422,
            )

    @router.post("/api/review/{document_id}/validate")
    def validate_review_document(document_id: str):
        """Run the shared read-only HEVA validator for the active document."""

        try:
            report = validate_document_package(root, document_id)
        except (OSError, ValueError, ValidationError, PackageValidationError) as error:
            return JSONResponse(
                {
                    "code": "document_validation_unavailable",
                    "message": "This document could not be validated.",
                    "action": str(error),
                },
                status_code=422,
            )
        return {
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "document": report.model_dump(mode="json"),
        }

    @router.get("/api/review/{document_id}/source")
    def review_source(document_id: str):
        try:
            source = registered_source_path(root, document_id)
        except ReviewQueueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        if source.suffix.lower() != ".pdf":
            raise HTTPException(
                status_code=415,
                detail="Side-by-side browser preview currently supports PDF sources.",
            )
        return FileResponse(
            source,
            media_type="application/pdf",
            filename=source.name,
            content_disposition_type="inline",
        )

    @router.put("/api/review/{document_id}/decisions")
    def save_review_decisions(document_id: str, payload: dict):
        sentence_ids = payload.get("sentence_ids")
        status = payload.get("status")
        comment = payload.get("comment")
        if (
            not isinstance(sentence_ids, list)
            or not sentence_ids
            or not all(isinstance(item, int) for item in sentence_ids)
            or status not in {"approved", "needs_correction", "excluded"}
        ):
            raise HTTPException(
                status_code=422,
                detail="Select sentences and choose an approved review decision.",
            )
        try:
            reviewer = active_reviewer_name()
            record_decisions(
                root,
                document_id,
                sentence_ids,
                status=status,
                reviewer=reviewer,
                comment=comment if isinstance(comment, str) else None,
            )
            return load_review_document(root, document_id)
        except (
            OSError,
            ValueError,
            ValidationError,
            AnnotatorRegistryError,
            PeopleRegistryError,
            ReviewError,
            ReviewQueueError,
        ) as error:
            return JSONResponse(
                {
                    "code": "review_decision_not_saved",
                    "message": "The review decision was not saved.",
                    "action": str(error),
                },
                status_code=422,
            )

    @router.put("/api/review/{document_id}/sentences/{sentence_id}")
    def save_sentence_correction(
        document_id: str,
        sentence_id: int,
        payload: dict,
    ):
        replacement = payload.get("record")
        if not isinstance(replacement, dict):
            raise HTTPException(
                status_code=422,
                detail="Provide the corrected sentence fields.",
            )
        if replacement.get("sentence_id") != sentence_id:
            raise HTTPException(
                status_code=422,
                detail="The sentence identifier cannot be changed.",
            )
        try:
            reviewer = active_reviewer_name()
            replace_sentence_record(
                root,
                document_id,
                sentence_id,
                replacement,
                editor=reviewer,
                excluded_entity_indices=payload.get("excluded_entity_indices", ()),
            )
            return load_review_document(root, document_id)
        except (
            OSError,
            ValueError,
            ValidationError,
            AnnotatorRegistryError,
            ReviewError,
            ReviewQueueError,
        ) as error:
            return JSONResponse(
                {
                    "code": "sentence_correction_not_saved",
                    "message": "The sentence correction was not saved.",
                    "action": str(error),
                },
                status_code=422,
            )

    @router.put("/api/review/{document_id}/sentences/{sentence_id}/warnings/{code}")
    def accept_sentence_warning(
        document_id: str,
        sentence_id: int,
        code: str,
        payload: dict,
    ):
        """Record a curator's explicit acceptance of one automated warning."""

        comment = payload.get("comment")
        if comment is not None and not isinstance(comment, str):
            raise HTTPException(status_code=422, detail="Warning comment must be text.")
        try:
            accept_quality_warning(
                root,
                document_id,
                sentence_id,
                code,
                reviewer=active_reviewer_name(),
                comment=comment,
            )
            return load_review_document(root, document_id)
        except (
            OSError,
            ValueError,
            ValidationError,
            AnnotatorRegistryError,
            PeopleRegistryError,
            ReviewError,
            ReviewQueueError,
        ) as error:
            return JSONResponse(
                {
                    "code": "warning_disposition_not_saved",
                    "message": "The warning was not accepted.",
                    "action": str(error),
                },
                status_code=422,
            )
    return router
