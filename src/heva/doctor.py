"""Installation and environment diagnostics for the HEVA Toolkit.

Run ``python -m heva.doctor`` after installation. Optional dependency groups can be
required explicitly without turning unavailable optional services into misleading core
installation failures.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys
from typing import Iterable, Literal
import urllib.error
import urllib.request

from pydantic import BaseModel, ConfigDict

from heva.workflow.project_registry import DEFAULT_REGISTRY_PATH, ProjectRegistry


class DiagnosticCheck(BaseModel):
    """One stable environment result with a corrective action."""

    model_config = ConfigDict(extra="forbid")

    code: str
    status: Literal["pass", "warning", "fail"]
    message: str
    action: str | None = None


class DiagnosticReport(BaseModel):
    """Machine-readable installation report shared by scripts and human output."""

    model_config = ConfigDict(extra="forbid")

    ready: bool
    required_capabilities: list[str]
    checks: list[DiagnosticCheck]


def _module_available(module: str) -> bool:
    """Return whether a Python module can be imported without importing it."""

    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def _dependency_check(
    module: str,
    *,
    code: str,
    capability: str,
    required: set[str],
    install_extra: str,
) -> DiagnosticCheck:
    available = _module_available(module)
    is_required = capability in required
    if available:
        return DiagnosticCheck(
            code=code,
            status="pass",
            message=f"{capability.capitalize()} dependency {module!r} is available.",
        )
    return DiagnosticCheck(
        code=code,
        status="fail" if is_required else "warning",
        message=f"{capability.capitalize()} dependency {module!r} is not installed.",
        action=(
            f'Install with: python -m pip install -e ".[{install_extra}]"'
            if install_extra
            else "Install with: python -m pip install -e ."
        ),
    )


def _project_check(project_root: str | Path) -> DiagnosticCheck:
    root = Path(project_root).expanduser().resolve()
    registry_path = root / DEFAULT_REGISTRY_PATH
    try:
        registry = ProjectRegistry.model_validate_json(
            registry_path.read_text(encoding="utf-8")
        )
    except FileNotFoundError:
        return DiagnosticCheck(
            code="project_registry",
            status="fail",
            message=f"{root} is not an initialized HEVA project.",
            action="Open it in the app and choose Create project, or select another folder.",
        )
    except (OSError, ValueError) as error:
        return DiagnosticCheck(
            code="project_registry",
            status="fail",
            message=f"The project registry cannot be read: {error}",
            action="Restore or correct data/project-registry.json.",
        )
    return DiagnosticCheck(
        code="project_registry",
        status="pass",
        message=(
            f"Project registry is valid and contains "
            f"{registry.summary.total} document(s)."
        ),
    )


def _ollama_check(host: str, *, required: bool) -> DiagnosticCheck:
    request = urllib.request.Request(f"{host.rstrip('/')}/api/tags")
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            if response.status != 200:
                raise urllib.error.URLError(f"HTTP {response.status}")
    except (OSError, urllib.error.URLError) as error:
        return DiagnosticCheck(
            code="ollama",
            status="fail" if required else "warning",
            message=f"Local Ollama is not reachable at {host}: {error}",
            action="Start Ollama only if automatic color suggestions are needed.",
        )
    return DiagnosticCheck(
        code="ollama",
        status="pass",
        message=f"Local Ollama is reachable at {host}.",
    )


def check_environment(
    *,
    require: Iterable[str] = (),
    project_root: str | Path | None = None,
    check_ollama: bool = False,
    ollama_host: str = "http://127.0.0.1:11434",
) -> DiagnosticReport:
    """Check requested HEVA capabilities without mutating the environment."""

    required = set(require)
    unknown = required - {"core", "app", "extraction", "ollama"}
    if unknown:
        raise ValueError(f"Unknown required capabilities: {', '.join(sorted(unknown))}.")
    required.add("core")
    checks = [
        DiagnosticCheck(
            code="python_version",
            status="pass" if sys.version_info >= (3, 12) else "fail",
            message=(
                f"Python {sys.version_info.major}.{sys.version_info.minor} is running; "
                "HEVA requires Python 3.12 or newer."
            ),
            action=(
                None
                if sys.version_info >= (3, 12)
                else "Create the environment with Python 3.12."
            ),
        ),
        _dependency_check(
            "pydantic",
            code="core_pydantic",
            capability="core",
            required=required,
            install_extra="",
        ),
    ]
    for module in ("fastapi", "uvicorn"):
        checks.append(
            _dependency_check(
                module,
                code=f"app_{module}",
                capability="app",
                required=required,
                install_extra="app",
            )
        )
    for module in ("fitz", "docx", "spacy"):
        checks.append(
            _dependency_check(
                module,
                code=f"extraction_{module}",
                capability="extraction",
                required=required,
                install_extra="extraction",
            )
        )
    if "extraction" in required and sys.version_info >= (3, 13):
        checks.append(
            DiagnosticCheck(
                code="extraction_python_version",
                status="fail",
                message="The pinned extraction stack is supported on Python 3.12.",
                action="Create a Python 3.12 environment for extraction.",
            )
        )
    if project_root is not None:
        checks.append(_project_check(project_root))
    if check_ollama or "ollama" in required:
        checks.append(_ollama_check(ollama_host, required="ollama" in required))
    return DiagnosticReport(
        ready=not any(check.status == "fail" for check in checks),
        required_capabilities=sorted(required),
        checks=checks,
    )


def format_report(report: DiagnosticReport) -> str:
    """Render a concise human diagnostic report with next actions."""

    lines = ["HEVA environment check"]
    for check in report.checks:
        lines.append(f"{check.status.upper():7} {check.code}: {check.message}")
        if check.action:
            lines.append(f"        Fix: {check.action}")
    lines.append("READY" if report.ready else "NOT READY")
    return "\n".join(lines)


def main(argv: Iterable[str] | None = None) -> int:
    """Run HEVA diagnostics through the command-line interoperability surface."""

    parser = argparse.ArgumentParser(
        description="Check whether requested HEVA capabilities are available."
    )
    parser.add_argument(
        "--require",
        action="append",
        choices=("core", "app", "extraction", "ollama"),
        default=[],
        help="Capability that must pass; may be repeated.",
    )
    parser.add_argument("--project", help="Optionally check an initialized HEVA project.")
    parser.add_argument(
        "--check-ollama",
        action="store_true",
        help="Report optional local Ollama availability without requiring it.",
    )
    parser.add_argument("--ollama-host", default="http://127.0.0.1:11434")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = check_environment(
        require=args.require,
        project_root=args.project,
        check_ollama=args.check_ollama,
        ollama_host=args.ollama_host,
    )
    print(
        json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True)
        if args.json
        else format_report(report)
    )
    return 0 if report.ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
