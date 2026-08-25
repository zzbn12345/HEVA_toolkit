"""Small in-process job registry for observable local extraction work."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from threading import Lock
from typing import Any


class ExtractionJobRegistry:
    """Track one active extraction per document for the local alpha application."""

    def __init__(self) -> None:
        self._jobs: dict[str, dict[str, Any]] = {}
        self._lock = Lock()

    def start(self, document_id: str) -> dict[str, Any] | None:
        """Create a queued job, or return ``None`` when that document is busy."""

        with self._lock:
            current = self._jobs.get(document_id)
            if current and current["state"] in {"queued", "running"}:
                return None
            now = datetime.now(UTC).isoformat()
            self._jobs[document_id] = {
                "document_id": document_id,
                "state": "queued",
                "stage": "queued",
                "message": "Extraction is queued.",
                "completed_steps": 0,
                "total_steps": 3,
                "completed_pages": 0,
                "total_pages": None,
                "started_at": now,
                "updated_at": now,
                "result": None,
                "error": None,
                "cancel_requested": False,
            }
            return deepcopy(self._jobs[document_id])

    def update(self, document_id: str, **changes: Any) -> dict[str, Any]:
        """Atomically update a job and return a safe response copy."""

        with self._lock:
            job = self._jobs[document_id]
            job.update(changes)
            job["updated_at"] = datetime.now(UTC).isoformat()
            return deepcopy(job)

    def get(self, document_id: str) -> dict[str, Any] | None:
        """Return a safe copy of the latest job state."""

        with self._lock:
            job = self._jobs.get(document_id)
            return deepcopy(job) if job else None

    def request_cancellation(self, document_id: str) -> dict[str, Any] | None:
        """Request cooperative cancellation for a queued or running job."""

        with self._lock:
            job = self._jobs.get(document_id)
            if (
                job is None
                or job["state"] not in {"queued", "running"}
                or job["stage"] not in {"queued", "extracting"}
            ):
                return None
            job["cancel_requested"] = True
            job["message"] = "Cancellation requested; finishing the current safe unit."
            job["updated_at"] = datetime.now(UTC).isoformat()
            return deepcopy(job)

    def cancellation_requested(self, document_id: str) -> bool:
        """Return whether an active job should stop at its next safe boundary."""

        with self._lock:
            job = self._jobs.get(document_id)
            return bool(job and job.get("cancel_requested"))
