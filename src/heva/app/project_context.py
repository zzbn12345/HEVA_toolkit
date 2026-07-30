"""Active local project selection for the single-user desktop-style web app."""

from __future__ import annotations

import os
import json
from pathlib import Path


class NoActiveProjectError(RuntimeError):
    """Raised when a project-scoped operation is attempted before selection."""


class ProjectContext(os.PathLike[str]):
    """Mutable path-like reference to the project currently open in the app."""

    def __init__(
        self,
        project_root: str | Path | None = None,
        session_path: str | Path | None = None,
    ) -> None:
        self._session_path = Path(session_path).resolve() if session_path else None
        self._root = Path(project_root).expanduser().resolve() if project_root else None
        if self._root is None:
            self._root = self._restore()
        elif self._session_path is not None:
            self._persist()

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
        self._persist()
        return self._root

    def close(self) -> None:
        self._root = None
        if self._session_path is not None:
            self._session_path.unlink(missing_ok=True)

    def _restore(self) -> Path | None:
        """Restore the most recently selected folder when it still exists."""

        if self._session_path is None:
            return None
        try:
            value = json.loads(self._session_path.read_text(encoding="utf-8"))
            candidate = Path(value["project_root"]).expanduser().resolve()
        except (OSError, KeyError, TypeError, json.JSONDecodeError):
            return None
        return candidate if candidate.is_dir() else None

    def _persist(self) -> None:
        """Atomically persist the active project pointer as local app state."""

        if self._session_path is None or self._root is None:
            return
        self._session_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._session_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps({"project_root": str(self._root)}, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self._session_path)

    def __fspath__(self) -> str:
        return os.fspath(self.require())

    def __truediv__(self, other: str | Path) -> Path:
        return self.require() / other

    def __str__(self) -> str:
        return str(self._root) if self._root else ""
