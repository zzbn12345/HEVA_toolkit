# HEVA Toolkit documentation

HEVA helps researchers extract colored PDF/DOCX annotations, review them with human
supervision, validate document packages, and build curator-approved annotation releases.
Source documents remain local unless their rights explicitly permit distribution.

## Start

- [Quickstart](quickstart.md) — install HEVA, check the installation, and open the app.
- [Alpha test protocol](ALPHA_TEST.md) — reproduce the workflow with an authorized dataset.
- [Guided workflow](GUIDED_REVIEW_WORKFLOW.md) — understand the complete annotation cycle.
- [Validation](VALIDATION.md) — run the minimum product from the app or command line.
- [Current evidence and limitations](EVALUATION.md) — understand what HEVA can and cannot
  currently claim.

## Core concepts

- [Project boundaries](PROJECT_BOUNDARIES.md)
- [Project registry and stable document IDs](PROJECT_REGISTRY.md)
- [Canonical annotation record](HEVA_RECORD_CONTRACT.md)
- [Document metadata, citation, and rights](DOCUMENT_METADATA.md)
- [Document-local color mapping](COLOR_MAPPING.md)
- [Extraction sessions and checkpoints](EXTRACTION_SESSIONS.md)
- [Sentence quality flags](QUALITY_FLAGS.md)
- [Human sentence review](SENTENCE_REVIEW.md)
- [Local curator decisions](CURATION.md)
- [FAIR candidate releases](APPROVED_EXPORT.md)

## Task guides

- [Create and open a project](guides/create-project.md)
- [Review document colors](guides/review-colors.md)
- [Validate a project](guides/validate-project.md)
- [Edit annotations through CSV](guides/edit-with-csv.md)
- [Prepare an annotation-only distribution](guides/distribute-without-sources.md)
- [Publish the private documentation Wiki](guides/publish-documentation.md)

## Technical reference

- [Architecture](ARCHITECTURE.md)
- [Extraction guide](README_VE.md)
- [Automatic color mapper architecture](AUTO_COLOR_MAPPER_ARCHITECTURE.md)
- [Command-line reference](reference/command-line.md)
- [Package layout reference](reference/package-layout.md)

## Roles

- **Annotator:** the person who originally annotated the source PDF or DOCX.
- **Curator:** processes and reviews annotations in HEVA, then accepts, requests changes,
  rejects, or quarantines an exact submitted candidate.
- **Data owner:** the person responsible for the Data Package and its per-document
  distribution approval; an institution may be recorded as their affiliation.
- **Reviewer:** an action role, typically exercised by the data owner.

HEVA separates specification conformance from scholarly correctness. A passing validation
report means the package follows the current contract; it does not prove that every source
annotation was extracted or that every scholarly interpretation is correct.
