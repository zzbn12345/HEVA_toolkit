"""Tests for cooperative extraction-job lifecycle state."""

from heva.app.extraction_jobs import ExtractionJobRegistry


def test_running_job_can_request_cancellation() -> None:
    registry = ExtractionJobRegistry()
    registry.start("HEVA-TEST")
    registry.update("HEVA-TEST", state="running", stage="extracting")

    job = registry.request_cancellation("HEVA-TEST")

    assert job is not None
    assert job["cancel_requested"] is True
    assert registry.cancellation_requested("HEVA-TEST") is True


def test_finished_or_missing_job_cannot_be_cancelled() -> None:
    registry = ExtractionJobRegistry()
    registry.start("HEVA-DONE")
    registry.update("HEVA-DONE", state="completed", stage="completed")

    assert registry.request_cancellation("HEVA-DONE") is None
    assert registry.request_cancellation("HEVA-MISSING") is None


def test_compilation_is_not_reported_as_cancellable() -> None:
    registry = ExtractionJobRegistry()
    registry.start("HEVA-COMPILING")
    registry.update("HEVA-COMPILING", state="running", stage="compiling")

    assert registry.request_cancellation("HEVA-COMPILING") is None
