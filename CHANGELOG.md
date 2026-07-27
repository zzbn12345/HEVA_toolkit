# Changelog

## Unreleased

### Added

- A document review queue that summarizes batch-prepared documents while opening only one
  document, PDF, color evidence, sentence set, and audit state at a time.
- Researcher-facing sentence cards with pending/problematic filters, 20/50 record views,
  readable color hex codes, quality flags, and explicit review decisions.

### Changed

- Separated the extraction/NLP, data-management, and optional FastAPI application into
  independent package directories and dependency profiles.
- Organized the application around a small `main.py` composition root and separate project
  and review route modules.
- Moved tests into extraction and management groups while retaining temporary `src/`
  compatibility imports for existing scripts.
