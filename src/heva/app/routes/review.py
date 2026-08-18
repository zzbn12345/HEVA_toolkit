"""Document queue, source preview, and sentence decision routes."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import ValidationError

from heva.workflow.annotator_registry import (
    AnnotatorRegistryError,
    load_annotator_registry,
)
from heva.workflow.curation_state import (
    CurationError,
    load_curation_state,
    record_curator_decision,
)
from heva.workflow.data_owner_approval import (
    DataOwnerApprovalError,
    approve_document_distribution,
    load_current_data_owner_approval,
)
from heva.workflow.people_registry import (
    PeopleRegistryError,
    PersonRecord,
    add_person,
    load_people_registry,
)
from heva.workflow.project_registry import (
    RegistryError,
    register_discovered_sources,
    scan_project_sources,
)
from heva.workflow.review_queue import (
    ReviewQueueError,
    list_review_queue,
    load_review_document,
    registered_source_path,
    submit_review_document,
)
from heva.workflow.review_state import (
    ReviewError,
    record_decisions,
    replace_sentence_record,
)


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
            annotator = load_annotator_registry(root).active()
            if annotator is None or not annotator.name:
                raise ValueError("Select an active project annotator before reviewing.")
            record_decisions(
                root,
                document_id,
                sentence_ids,
                status=status,
                reviewer=annotator.name,
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
            annotator = load_annotator_registry(root).active()
            if annotator is None or not annotator.name:
                raise ValueError("Select an active project annotator before editing.")
            replace_sentence_record(
                root,
                document_id,
                sentence_id,
                replacement,
                editor=annotator.name,
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

    @router.post("/api/review/{document_id}/submit")
    def submit_document_review(document_id: str):
        try:
            curator = load_people_registry(root).active_curator()
            annotator = load_annotator_registry(root).active() if curator is None else None
            actor = curator.name if curator is not None else (annotator.name if annotator else "")
            if not actor:
                raise ValueError("Select an active project curator before submitting.")
            return submit_review_document(
                root,
                document_id,
                submitted_by=actor,
            )
        except (
            OSError,
            ValueError,
            ValidationError,
            AnnotatorRegistryError,
            PeopleRegistryError,
            CurationError,
            ReviewError,
            ReviewQueueError,
        ) as error:
            return JSONResponse(
                {
                    "code": "document_review_not_submitted",
                    "message": "The document was not submitted for curator review.",
                    "action": str(error),
                },
                status_code=422,
            )

    @router.get("/api/curation/{document_id}")
    def curation_state(document_id: str):
        """Expose submitted snapshot evidence and decisions for one queue record."""

        try:
            state = load_curation_state(root, document_id)
            payload = state.model_dump(mode="json")
            payload["data_owners"] = [
                person.model_dump(mode="json")
                for person in load_people_registry(root).people
                if "data_owner" in person.roles
            ]
            try:
                approval, owner = load_current_data_owner_approval(root, document_id)
                payload["data_owner_approval"] = {
                    **approval.model_dump(mode="json"),
                    "owner_name": owner.name,
                }
            except DataOwnerApprovalError:
                payload["data_owner_approval"] = None
            return payload
        except CurationError as error:
            return JSONResponse(
                {
                    "code": "curation_state_unavailable",
                    "message": "The curator evidence cannot be loaded.",
                    "action": str(error),
                },
                status_code=422,
            )

    @router.post("/api/curation/{document_id}/data-owner-approval")
    def save_data_owner_approval(document_id: str, payload: dict):
        """Record accountable per-document distribution approval after acceptance."""

        try:
            result = approve_document_distribution(
                root,
                document_id,
                data_owner_id=str(payload.get("data_owner_id", "")),
                license_or_waiver=str(payload.get("license_or_waiver", "")),
                statement=str(payload.get("statement", "")),
            )
            return result
        except DataOwnerApprovalError as error:
            return JSONResponse(
                {
                    "code": "data_owner_approval_not_saved",
                    "message": "Distribution approval was not saved.",
                    "action": str(error),
                },
                status_code=422,
            )

    @router.post("/api/people/data-owners", status_code=201)
    def create_data_owner(payload: dict):
        """Add the person accountable for package distribution from the curation UI."""

        try:
            person = PersonRecord(
                name=str(payload.get("name", "")),
                affiliation=str(payload.get("affiliation", "")) or None,
                roles=["data_owner"],
            )
            return add_person(root, person)
        except (ValueError, ValidationError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.post("/api/curation/{document_id}/decisions")
    def save_curator_decision(document_id: str, payload: dict):
        """Validate and persist a curator decision against immutable evidence."""

        decision = payload.get("decision")
        actor = payload.get("actor")
        evidence = payload.get("evidence")
        requested_changes = payload.get("requested_changes", [])
        if (
            decision
            not in {"accepted", "changes_requested", "rejected", "quarantined"}
            or not isinstance(actor, str)
            or not isinstance(evidence, str)
            or not isinstance(requested_changes, list)
            or not all(isinstance(item, str) for item in requested_changes)
        ):
            raise HTTPException(
                status_code=422,
                detail="Provide a supported decision, curator, and evidence.",
            )
        try:
            result = record_curator_decision(
                root,
                document_id,
                decision=decision,
                actor=actor,
                evidence=evidence,
                requested_changes=requested_changes,
            )
            return result
        except CurationError as error:
            return JSONResponse(
                {
                    "code": "curator_decision_not_saved",
                    "message": "The curator decision was not saved.",
                    "action": str(error),
                },
                status_code=422,
            )

    return router
