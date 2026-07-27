"""Document queue, source preview, and sentence decision routes."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import ValidationError

from heva.workflow.document_metadata import AnnotatorMetadata
from heva.workflow.review_queue import (
    ReviewQueueError,
    list_review_queue,
    load_review_document,
    registered_source_path,
)
from heva.workflow.review_state import ReviewError, record_decisions


def create_review_router(
    root: Path,
    template: Callable[[str], str],
) -> APIRouter:
    router = APIRouter()

    @router.get("/review", response_class=HTMLResponse)
    def review_queue_page() -> str:
        return template("review_queue.html")

    @router.get("/review/{document_id}", response_class=HTMLResponse)
    def review_document_page(document_id: str) -> str:
        return template("review_document.html").replace(
            "DOCUMENT_ID_PLACEHOLDER",
            document_id,
        )

    @router.get("/api/review-queue")
    def review_queue():
        try:
            items = list_review_queue(root)
        except (ReviewQueueError, ValidationError) as error:
            return JSONResponse(
                {
                    "code": "review_queue_unavailable",
                    "message": "The document review queue cannot be loaded.",
                    "action": str(error),
                },
                status_code=422,
            )
        return {"documents": [item.model_dump(mode="json") for item in items]}

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
            annotator = AnnotatorMetadata.model_validate_json(
                (root / "data" / "annotator.json").read_text(encoding="utf-8")
            )
            if not annotator.name:
                raise ValueError("Annotator name is empty.")
            record_decisions(
                root,
                document_id,
                sentence_ids,
                status=status,
                reviewer=annotator.name,
                comment=comment if isinstance(comment, str) else None,
            )
            return load_review_document(root, document_id)
        except (OSError, ValueError, ValidationError, ReviewError, ReviewQueueError) as error:
            return JSONResponse(
                {
                    "code": "review_decision_not_saved",
                    "message": "The review decision was not saved.",
                    "action": str(error),
                },
                status_code=422,
            )

    return router
