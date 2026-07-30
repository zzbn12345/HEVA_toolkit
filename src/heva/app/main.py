"""FastAPI composition root for the optional guided HEVA application."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from heva.app.project_context import ProjectContext
from heva.app.documentation import create_documentation_router
from heva.app.routes.project import create_project_router
from heva.app.routes.review import create_review_router


WEB_ROOT = Path(__file__).parent


def _template(name: str) -> str:
    return (WEB_ROOT / "templates" / name).read_text(encoding="utf-8")


def create_app(
    project_root: str | Path | None = None,
    session_path: str | Path | None = None,
) -> FastAPI:
    """Create an app that can open one persistent HEVA project at a time."""

    context = ProjectContext(project_root, session_path=session_path)
    app = FastAPI(title="HEVA Toolkit", version="0.1.0")
    app.state.project_context = context
    app.mount("/static", StaticFiles(directory=WEB_ROOT / "static"), name="static")
    app.include_router(create_documentation_router(_template))
    app.include_router(create_project_router(context, _template))
    app.include_router(create_review_router(context, _template))

    @app.middleware("http")
    async def require_active_project(request: Request, call_next):
        path = request.url.path
        unscoped = (
            path == "/"
            or path == "/health"
            or path == "/api/project"
            or path == "/guide"
            or path.startswith("/guide/")
            or path.startswith("/api/folders/")
            or path.startswith("/api/projects/")
            or path.startswith("/static/")
        )
        if not unscoped and not context.selected:
            if path.startswith("/api/"):
                return JSONResponse(
                    {
                        "code": "no_active_project",
                        "message": "No HEVA project is open.",
                        "action": "Open an existing project or create one from a source folder.",
                    },
                    status_code=409,
                )
            return RedirectResponse("/", status_code=303)
        return await call_next(request)

    return app


app = create_app()


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the local HEVA web interface.")
    parser.add_argument(
        "--project-root",
        default=None,
        help="Optionally open this HEVA project immediately.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(list(argv) if argv is not None else None)
    import uvicorn

    session_path = Path.cwd() / ".heva" / "active-project.json"
    uvicorn.run(
        create_app(args.project_root, session_path=session_path),
        host=args.host,
        port=args.port,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
