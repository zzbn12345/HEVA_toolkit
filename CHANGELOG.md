# Changelog

## Unreleased

### Added

- A schema-driven project annotator editor with filterable reusable profiles, validated
  form fields, read-only schema/generated-JSON views, stable identifiers, active-profile
  selection, and migration from the former single-profile JSON.
- Domain-safe removal of annotators from current project configuration without rewriting
  historical sentence-review evidence.
- A document dashboard that separates sentence-review percentage from overall annotation
  readiness and explains failed citation, color, extraction, and sentence gates.
- Deterministic citation proposals from PDF/DOCX properties or source filenames, with
  editable drafts and explicit annotator confirmation recorded in each document package.
- A document review queue that summarizes batch-prepared documents while opening only one
  document, PDF, color evidence, sentence set, and audit state at a time.
- A row-based annotation project list with explicit completion bars and an
  **Edit this annotation** action for every reviewable document.
- Immediate inline PDF display when an annotator opens a registered document from the
  project list, without selecting the same source file again.
- Separate Add document and Edit annotation paths: adding requests a PDF or DOCX file,
  while editing retains the registered source.
- Researcher-facing sentence cards with pending/problematic filters, 20/50 record views,
  readable color hex codes, quality flags, and explicit review decisions.

### Changed

- Consolidated the toolkit under one `heva` namespace, with `app`, `extraction`, and
  `workflow` subpackages in a standard `src` layout.
- Replaced separate requirements files with base, app, extraction, and development
  dependency groups in `pyproject.toml`.
- Documented the agreed document-state, completion, settings, sentence-review, batch
  decision, quality-flag, and side-by-side PDF workflow.
- Organized the application around a small `main.py` composition root and separate project
  and review route modules.
- Moved tests into matching app, extraction, and workflow groups and removed the temporary
  compatibility modules.
