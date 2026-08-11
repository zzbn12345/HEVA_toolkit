# HEVA Quickstart

This guide installs HEVA, performs a basic installation check, starts the local web
application, and runs project validation.

## Requirements

- Python 3.12
- A terminal
- A folder for the curated dataset; source PDF/DOCX files may be elsewhere
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
python -m heva.doctor --require app
```

For extraction support:

```bash
python -m heva.doctor --require app --require extraction
```

Every required check should report `PASS`, followed by `READY`. Ollama is optional:

```bash
python -m heva.doctor --check-ollama
```

Check an existing project folder:

```bash
python -m heva.doctor --project /path/to/project
```

## 5. Start the application

```bash
python -m heva.app
```

Open <http://127.0.0.1:8000>. Keep the terminal running while using the app.

From the home page:

1. Create or open the dedicated curated-dataset project.
2. Configure the active curator and record the original annotator separately.
3. Add a PDF/DOCX from the project folder or bind an authorized source elsewhere. External
   paths remain local and the source is not copied into the dataset repository.
4. Add or import a valid citation. Citation is required for release, not sentence curation.
5. Confirm the document colors. HEVA creates or reuses the immutable project palette.
6. Extract annotations. Raw hex evidence is saved first; canonical annotations appear only
   after the selected palette resolves every observed color.
7. Review every sentence and submit the document for curator review.
8. Accept the candidate in the curator queue, add the responsible data owner, and record
   that document's license or waiver approval.
9. Run **Validate this project** throughout the process.

## 6. Run validation from the terminal

Replace `/path/to/project` with the folder containing `.heva/project.json`:

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
  --report /path/to/project/validation-report.json
```

## What success means

- **Passed:** the package conforms to the current HEVA specification.
- **Completed:** a curator accepted the submitted candidate.
- **Release-ready:** the completed package satisfies release validation. Data Package
  generation additionally verifies intact curator evidence and per-document data-owner
  approval.

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
