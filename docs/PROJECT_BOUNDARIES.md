# Project boundaries and optional dependencies

HEVA contains three related capabilities with different responsibilities and dependency
costs. They must remain independently usable.

## Data management

The implementation lives in `management/heva_management`. The default environment installs
only Pydantic. It covers the canonical record contract,
project registry, document metadata, document-local color decisions, quality flags,
sentence review, validation, and approved release construction.

```bash
./venv/bin/python -m pip install -r requirements.txt
```

Management modules consume canonical JSON records. They do not need to know how PDF or
Word evidence was extracted.

## Document extraction and NLP

The implementation lives in `extraction/heva_extraction`. Its profile adds PyMuPDF, spaCy,
and python-docx. These modules turn PDF or Word evidence into candidate records. They must
not decide rights, approve mappings,
complete reviews, or release data.

```bash
./venv/bin/python -m pip install -r requirements-extraction.txt
```

Batch extraction is permitted because each result is persisted independently. Color
proposals and review decisions remain document-local.

## Researcher-facing application

The optional application lives under `app/heva_app`, with `main.py`, thin route modules,
templates, and static assets. It has its own environment. FastAPI, Uvicorn,
multipart upload support, and browser-test dependencies are therefore not imposed on
management scripts or the original NLP tools.

```bash
python3.12 -m venv app/venv
./app/venv/bin/python -m pip install -r app/requirements.txt
```

The application is an interface over the management services. It must not contain a second
implementation of the HEVA contract or review rules. Automatic extraction can later be
enabled by adding the extraction profile to the app environment.

The modules remaining under `src/` are temporary forwarding imports and command entry
points. They preserve existing integrations while callers migrate to the new package
names; they contain no canonical implementation.

## Batch preparation, individual review

A batch operation may discover sources, extract candidate records, and generate separate
color proposals. It creates one persistent package per registered document. The review
queue then opens one document at a time with its own PDF, mapping, annotations, flags, and
audit history. No batch action may silently approve mappings or sentence decisions across
documents.
