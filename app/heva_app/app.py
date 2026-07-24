"""FastAPI foundation for the guided HEVA workflow."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from src.document_metadata import AnnotatorMetadata
from src.package_validator import PackageValidationError, validate_project
from src.project_registry import DEFAULT_REGISTRY_PATH, ProjectRegistry


WEB_ROOT = Path(__file__).parent


def _template(name: str) -> str:
    return (WEB_ROOT / "templates" / name).read_text(encoding="utf-8")


def create_app(project_root: str | Path = ".") -> FastAPI:
    """Create an app bound to one persistent HEVA project directory."""

    root = Path(project_root).resolve()
    app = FastAPI(title="HEVA Toolkit", version="0.1.0")
    app.state.project_root = root
    app.mount("/static", StaticFiles(directory=WEB_ROOT / "static"), name="static")

    @app.get("/", response_class=HTMLResponse)
    def home() -> str:
        return _template("home.html")

    @app.get("/validate", response_class=HTMLResponse)
    def validation_page() -> str:
        return _template("validate.html")

    @app.get("/create", response_class=HTMLResponse)
    def creation_page() -> str:
        return _template("create.html")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/project")
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

    @app.get("/api/annotator")
    def annotator_status():
        path = root / "data" / "annotator.json"
        if not path.exists():
            return {"configured": False, "annotator": {"name": None, "orcid": None}}
        try:
            annotator = AnnotatorMetadata.model_validate_json(path.read_text(encoding="utf-8"))
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
        return {"configured": bool(annotator.name), "annotator": annotator.model_dump(mode="json")}

    @app.put("/api/annotator")
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
            json.dumps(normalized.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
        return {"configured": True, "annotator": normalized.model_dump(mode="json")}

    @app.post("/api/validate")
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

    return app


app = create_app()


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the local HEVA web interface.")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(list(argv) if argv is not None else None)
    import uvicorn

    uvicorn.run(
        create_app(args.project_root),
        host=args.host,
        port=args.port,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
