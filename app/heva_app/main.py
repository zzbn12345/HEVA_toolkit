"""FastAPI composition root for the optional guided HEVA application."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.heva_app.routes.project import create_project_router
from app.heva_app.routes.review import create_review_router


WEB_ROOT = Path(__file__).parent


def _template(name: str) -> str:
    return (WEB_ROOT / "templates" / name).read_text(encoding="utf-8")


def create_app(project_root: str | Path = ".") -> FastAPI:
    """Create an app bound to one persistent HEVA project directory."""

    root = Path(project_root).resolve()
    app = FastAPI(title="HEVA Toolkit", version="0.1.0")
    app.state.project_root = root
    app.mount("/static", StaticFiles(directory=WEB_ROOT / "static"), name="static")
    app.include_router(create_project_router(root, _template))
    app.include_router(create_review_router(root, _template))
    return app


app = create_app()


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the local HEVA web interface.")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(list(argv) if argv is not None else None)
    import uvicorn

    uvicorn.run(create_app(args.project_root), host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
