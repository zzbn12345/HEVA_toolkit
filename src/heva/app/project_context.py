"""Active local project selection for the single-user desktop-style web app."""

from __future__ import annotations

import os
from pathlib import Path


class NoActiveProjectError(RuntimeError):
    """Raised when a project-scoped operation is attempted before selection."""


class ProjectContext(os.PathLike[str]):
    """Mutable path-like reference to the project currently open in the app."""

    def __init__(self, project_root: str | Path | None = None) -> None:
        self._root = Path(project_root).expanduser().resolve() if project_root else None

    @property
    def selected(self) -> bool:
        return self._root is not None

    @property
    def root(self) -> Path | None:
        return self._root

    def require(self) -> Path:
        if self._root is None:
            raise NoActiveProjectError("Open or create a HEVA project first.")
        return self._root

    def select(self, project_root: str | Path) -> Path:
        self._root = Path(project_root).expanduser().resolve()
        return self._root

    def close(self) -> None:
        self._root = None

    def __fspath__(self) -> str:
        return os.fspath(self.require())

    def __truediv__(self, other: str | Path) -> Path:
        return self.require() / other

    def __str__(self) -> str:
        return str(self._root) if self._root else ""
