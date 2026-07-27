# Project boundaries and optional dependencies

HEVA contains three related capabilities with different responsibilities and dependency
costs. They must remain independently usable.

## Workflow

The implementation lives in `src/heva/workflow`. The base installation includes only
Pydantic. It covers the canonical record contract,
project registry, document metadata, document-local color decisions, quality flags,
sentence review, validation, and approved release construction.

```bash
./venv/bin/python -m pip install -e .
```

Workflow modules consume canonical JSON records. They do not need to know how PDF or
Word evidence was extracted.

## Document extraction and NLP

The implementation lives in `src/heva/extraction`. Its optional group adds PyMuPDF, spaCy,
and python-docx. These modules turn PDF or Word evidence into candidate records. They must
not decide rights, approve mappings,
complete reviews, or release data.

```bash
./venv/bin/python -m pip install -e ".[extraction]"
```

Batch extraction is permitted because each result is persisted independently. Color
proposals and review decisions remain document-local.

## Researcher-facing application

The optional application lives under `src/heva/app`, with `main.py`, thin route modules,
templates, and static assets. FastAPI, Uvicorn, and multipart upload support are not
installed for workflow-only users.

```bash
./venv/bin/python -m pip install -e ".[app]"
```

The application is an interface over the management services. It must not contain a second
implementation of the HEVA contract or review rules. Automatic extraction can later be
enabled by adding the extraction profile to the app environment.

All public imports share one namespace: `heva.app`, `heva.extraction`, and
`heva.workflow`. The subpackages describe responsibility without repeating the project
name.

## Batch preparation, individual review

A batch operation may discover sources, extract candidate records, and generate separate
color proposals. It creates one persistent package per registered document. The review
queue then opens one document at a time with its own PDF, mapping, annotations, flags, and
audit history. No batch action may silently approve mappings or sentence decisions across
documents.
