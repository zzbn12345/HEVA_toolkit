# Changelog

## Unreleased

### Removed

- Removed the internal **Submit for curator review** workflow, curator decision page,
  approval APIs, edit locks, and approval-only export gate. HEVA now ends at validated
  Data Package export; repository platforms own review, acceptance, and publication.

### Changed

- Reduced Alpha validation to annotation Data Package requirements. Detailed per-document
  source authorization/access fields and color-detection method remain optional workspace
  provenance; dataset-level license and rights remain mandatory for export.
- Replaced numbered document steps with live green-check/missing-cross indicators for
  curator identity, citation, color configuration, extracted annotations, curated
  sentences, and document validation. The three annotation checks open the same sentence
  queue but remain independent so extracted work is never presented as curated or valid.
- Simplified the alpha workflow so opening a project leads directly to its document review
  queue, while document preparation now follows curator, citation, color configuration,
  and annotation steps.
- Embedded unresolved and canonical sentence evidence in the document annotation step so
  researchers can continue from color discovery into review without switching workflows.

### Fixed

- Localized annotation and sentence-review validation findings with document ID, canonical
  JSON path, record index, and sentence ID where available. Sentence findings now link to
  and reveal the exact sentence across paginated review results.
- Persist annotation-text corrections while keeping source sentences, tokens, pages,
  labels, and colors immutable. The editor now shows the full read-only sentence, attributes
  changes to the active curator, and explains whether color configuration or curator identity
  must be completed before editing is available.
- Added independent previous/next sentence pagination with a visible page indicator, so
  researchers can inspect later batches without approving the current batch first.
- Connected raw PDF/DOCX color discovery to the document Color config: observed hex values
  are persisted, displayed as readable swatches, and made available for supervised HEVA
  label decisions before canonical annotations are created.
- Added visible color-discovery progress, retry controls, timeouts, and actionable errors
  for missing extraction dependencies or unreadable/empty source evidence.
- Restored automatic extraction in the unified Python environment with spaCy available.
  Extraction performance remains unmeasured and is not yet an alpha performance claim.

### Still under alpha review

- Restore direct access to project validation beside **Add document** in the review queue.
- Measure PDF and DOCX extraction duration and memory use on the agreed alpha corpus.
- Explain in the Color config interface that hex codes are observed document colors and
  HEVA labels are supervised semantic decisions rather than universal color meanings.

### Added

- Added deterministic document selection to Data Package generation. Python callers and the
  module command can export one or several valid registered documents while invalid
  unselected project documents remain explicitly recorded as excluded membership. The
  validation screen offers the same per-document selection and preserves it in ZIP download.
- Added explicit **Accept warning** decisions for non-blocking automated sentence findings.
  Accepted warnings leave the active-problem list but retain their code, evidence, curator,
  timestamp, and optional explanation in review audit history; validation errors cannot be
  waived this way.
- Explicit original-annotator assignment per document, backed by stable project-person
  references and distributable identity snapshots that omit private email. The checklist,
  validation, and export now distinguish source authors, original annotators, and curators.
- Added read-only **Validate document** checks directly in sentence review, with timestamped
  valid/invalid outcomes, grouped actionable findings, corrective links, and immediate
  synchronization with document readiness.
- A Conda/Miniforge environment definition that installs the app, spaCy, and PDF/DOCX
  extraction consistently on Windows, macOS, and Linux.
- A fictional two-document Data Package plus a concise concept guide and tutorial for
  reproducing the same validated result with new documents.
- Direct **Validate project** and **Export Data Package** actions in the project review
  queue.
- A localhost-only **Stop HEVA** action that gracefully shuts down the Uvicorn process,
  with Ctrl+C retained as the documented fallback.
- Data Package generation from the validation view, with exact release-gate feedback and
  a deterministic annotation-only ZIP that excludes source documents and workspace state.
- A schema-validated dataset-details form for citable identity, creators, license, rights,
  and limitations, persisted as project-level metadata without requiring raw JSON editing.
- Separate curation and release readiness: citation may be completed after annotation
  acceptance, but validated citation remains mandatory before Data Package generation.
- A per-document rights and access form that records source authorization and independent
  PDF, extracted-text, and annotation distribution decisions without raw JSON editing.
- An all-or-nothing people CSV adapter with stable IDs, controlled multi-role values,
  contact validation, explicit active-curator selection, and command-line interoperability.
- A native people-CSV import action in the role-management view, reusing the strict adapter
  and warning before authoritative current configuration is replaced.

- A project people registry with explicit annotator, curator, and data-owner roles,
  active-curator integrity rules, and compatibility migration for former app operators.
- Immutable, curator-attributed project color-configuration versions that allow several
  hex values per HEVA category and record the selected version in document metadata.
- Collaborative unresolved extraction drafts that preserve raw text, offsets, pages, and
  hex colors, then compile only through a complete selected color-configuration version.
- A strict programmatic citation adapter with a small CSL-compatible profile, exact
  filename matching, CSV support, and machine-validation provenance.
- A non-mutating source scan whenever a project opens, with explicit per-file registration
  and session-only dismissal of newly discovered PDF/DOCX sources.
- Per-document data-owner approval bound to exact curator-accepted evidence, with required
  license/waiver provenance and a hard gate before Data Package generation.
- External PDF/DOCX bindings that keep protected source paths local and ignored while the
  separate dataset repository versions stable IDs, checksums, annotations, and evidence.
- A guarded raw-to-canonical extraction transition: the app saves raw evidence first and
  promotes it only through the selected complete project color-configuration version.
- Automatic creation or reuse of the immutable project palette when a curator confirms a
  document's color decisions in the web interface.
- A curator-queue data-owner form that creates the responsible project person and records
  per-document license/waiver approval after curator acceptance.
- An executable end-to-end alpha journey plus a researcher test protocol covering external
  sources, roles, citation, versioned colors, review, curation, ownership, and release.
- A role-aware project-people interface for original annotators, curators, and data owners,
  including safe CRUD and explicit active-curator selection for workflow attribution.
- A project-palette interface that exposes immutable history, validates controlled
  label/hex rows, appends revisions, and selects exact reusable versions.
- Source-folder project roots and collaborative workspace tracking, allowing another
  researcher to clone canonical annotations plus durable extraction, review, and curation
  state while keeping caches, locks, local sessions, binaries, and exports out of Git.
- A clean project layout where canonical analytical records live in `documents/`,
  application state lives in hidden `.heva/` workspace directories, and validated HEVA
  Data Packages are generated under `exports/`; legacy projects migrate automatically.
- A native folder chooser for opening or creating local projects, replacing inconvenient
  manually typed paths without uploading or copying source files.
- Session-only active-project selection and data-folder recognition, avoiding persisted or
  displayed user-directory paths while preventing accidental nested projects.
- Runtime-generated PDF and DOCX extraction fixtures, preserving regression coverage
  without distributing binary research documents in the toolkit repository.

### Removed

- Research PDFs, Word documents, spreadsheets, and other binary source material from the
  toolkit repository; HEVA projects now remain external and are selected through the app.
- A documentation home, newcomer Quickstart, task guides, and command/package references
  that provide one navigable entrance while preserving the existing authoritative docs.
- A read-only environment doctor with human and JSON reports for core, app, extraction,
  project-registry, and optional local Ollama readiness.
- A sanitized in-app guide that renders the same packaged Markdown used by the repository,
  remains available before opening a project, and provides contextual navigation from the
  main workflow screens.
- A deterministic private Wiki builder and synchronization workflow that validates pull
  requests and publishes the same documentation source after changes reach `main`.
- An independent strict HTML documentation workflow that packages an offline MkDocs site
  with a SHA-256 checksum as a 30-day workflow artifact.
- Developer READMEs for the web application, extraction adapters, and durable project
  workflow, documenting their dependencies, ownership boundaries, usage, and tests.

### Fixed

- Project people and palette forms now use the shared dark-theme field layout, keep labels
  and controls in readable rows, and reliably remove hidden actions from the page layout.
- Batch color compatibility now returns confirmation guidance for pending source palettes
  instead of invoking unrelated citation validation and failing unexpectedly.
- Registered external PDFs can now be previewed and inspected through their exact
  machine-local binding without exposing the protected absolute path in project records.

- The document review queue now responds to the width of the list itself and moves its
  action onto a second row before the table becomes too narrow, keeping **Edit this
  annotation** fully visible even inside a constrained page layout.
- Contextual guide references on validation findings in both the web report and
  human-readable command-line output.
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
- Deterministic FAIR candidate releases restricted to intact curator-accepted packages,
  with citable dataset/document metadata, rights, membership, checksums, build evidence,
  and explicit known limitations.
- A curator-approved evaluation manifest and reproducible scorer that separates
  record/span precision and recall, label accuracy, human correction/abstention measures,
  elapsed time, and peak memory while failing incomplete corpus coverage.
- A test-runner-style project validation report in both the app and command line, showing
  per-document pass/fail, independent completion state, issue locations, corrective
  actions, filters, summaries, stable JSON, and meaningful exit codes.
- A safe CSV-to-package compiler for non-GUI editing workflows that validates all rows,
  groups by stable document ID, refuses locked packages, refreshes changed sentence review,
  and preserves existing annotations when compilation fails.

### Changed

- Reduced the alpha documentation navigation to installation/running, validation, the Data
  Package concept, one practical tutorial, and current limitations. Advanced governance
  documentation remains available to developers but is no longer presented as required
  alpha reading.
- Automatic color suggestions now preselect their controlled-label fields while
  model-generated reasoning remains package provenance instead of appearing as a fixed
  color specification; only explicit document-legend mappings show source text.
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
