# HEVA Quickstart

This guide installs HEVA, performs a basic installation check, starts the local web
application, and runs project validation.

## Requirements

- Python 3.12
- A terminal
- A local folder containing PDF or DOCX source documents
- Ollama only when automatic color-label suggestions are needed

HEVA runs locally. The web application does not upload source documents.

## 1. Download the repository

Open a terminal in the repository root—the folder containing `pyproject.toml`.

## 2. Create an isolated Python environment

macOS or Linux:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
```

## 3. Install HEVA

Install validation and the web application:

```bash
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[app]"
```

Install PDF/DOCX extraction support when annotations must be extracted:

```bash
python -m pip install -e ".[app,extraction]"
```

## 4. Check the installation

```bash
python -c "import heva; print('HEVA import: OK')"
python -m heva.workflow.package_validator --help
```

Both commands should finish without a traceback.

## 5. Start the application

```bash
python -m heva.app
```

Open <http://127.0.0.1:8000>. Keep the terminal running while using the app.

From the home page:

1. Choose **Create project** for a folder containing PDF/DOCX files, or **Open existing
   project** for a folder containing `data/project-registry.json`.
2. Configure the reusable annotator profile.
3. Open one document and confirm its citation and document-local color mapping.
4. Extract annotations.
5. Review every sentence.
6. Run **Validate this project** at any time.

## 6. Run validation from the terminal

Replace `/path/to/project` with the folder containing the HEVA `data/` directory:

```bash
python -m heva.workflow.package_validator /path/to/project validate
```

Exit codes:

- `0`: the check ran and all selected packages passed;
- `1`: the check ran and found specification failures;
- `2`: validation could not run.

Create a machine-readable report:

```bash
python -m heva.workflow.package_validator /path/to/project validate \
  --json \
  --report /path/to/project/data/validation-report.json
```

## What success means

- **Passed:** the package conforms to the current HEVA specification.
- **Completed:** a curator accepted the submitted candidate.
- **Release-ready:** the completed package also satisfies release validation.

A package can pass while still being incomplete. Validation does not prove scholarly
correctness or extraction recall against every mark in the source.

## Common installation problems

- `python3.12: command not found`: install Python 3.12 or use a Python 3.12 environment.
- `externally-managed-environment`: activate `.venv` before installing.
- Extraction import errors: install `".[app,extraction]"`, not only `".[app]"`.
- Ollama unavailable: manual color configuration remains available; Ollama is optional.
- Scanned/image-only PDF: OCR is currently unsupported.

Continue with the [guided review workflow](GUIDED_REVIEW_WORKFLOW.md) or return to the
[documentation home](index.md).
