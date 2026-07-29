# Changelog

## Unreleased

### Added

- A neutral project chooser that opens an existing HEVA project, creates one around a
  folder of PDF/DOCX sources, and closes or switches the active project without exposing
  repository-level records by default.
- A schema-driven project annotator editor with filterable reusable profiles, validated
  form fields, read-only schema/generated-JSON views, stable identifiers, active-profile
  selection, and migration from the former single-profile JSON.
- Domain-safe removal of annotators from current project configuration without rewriting
  historical sentence-review evidence.
- A document dashboard that separates sentence-review percentage from overall annotation
  readiness and explains failed citation, color, extraction, and sentence gates.
- Deterministic citation proposals from PDF/DOCX properties or source filenames, with
  editable drafts and explicit annotator confirmation recorded in each document package.
- A document-local color review form that displays the colors actually stored in the
  package, distinguishes automatic suggestions from decisions, and requires an explicit
  controlled label or documented ignore reason for every color.
- A supervised **Request automatic proposals** action that extracts unresolved color
  evidence, asks local Ollama for controlled-label suggestions, persists them as pending
  evidence, and reports connection, timeout, or specification errors without changing
  confirmed decisions.
- Supervised batch mapping reuse that lists every other document with an explicit
  compatibility reason, enables only exact unconfirmed palette matches, and records the
  source document plus separate confirmation provenance in each selected package.
- Mapping-aware extraction checkpoints with visible current/stale/invalid state, persisted
  sentence counts and warnings, explicit rebuild controls, and corrective zero-record
  failures that preserve earlier extraction work.
- Explicit sentence selection and visible-batch review actions for 20/50-record views,
  with To be checked, Problematic, and Checked filters plus optional comments and one
  persisted audit decision per selected sentence.
- Safe migration of legacy extracted packages that have annotations but no review state:
  opening the queue creates pending sentence records without inventing decisions.
- A responsive extraction action with visible progress, a two-minute browser timeout,
  persisted-checkpoint feedback, and actionable extraction errors.
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
- A validated sentence-correction form for text, page, tokens, BIO tags, and controlled
  entities, with field-specific errors and before/after audit evidence.
- Inline sentence highlights that place every extracted annotation back into its textual
  context while retaining accessible label and hex-color details.
- Live document readiness gates and guarded curator submission that timestamps completed
  annotation review, moves the record to `in_review`, and locks submitted evidence.
- Direct Citation, Color configuration, and Annotator profile access from document review,
  plus a simplified repeatable extraction editor that derives hidden offsets and BIO tags.
- Restricted sentence correction to extracted text while retaining page, label, and color
  as visible read-only evidence from the document configuration.
- A read-only local curator queue combining registry workflow state with complete package
  validation findings and direct access to submitted annotation evidence.
- Immutable candidate snapshots with validator evidence and checksums, plus audited local
  accept, request-changes, reject, and quarantine decisions. Only acceptance marks a
  document done.

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
