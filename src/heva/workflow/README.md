# HEVA project workflow

This package is the durable data-management and validation core of HEVA. It can be used
from Python and command-line module entry points without installing the web application or
document extractors.

Its JSON files are the backend of an annotation project. The GUI and scripts are clients
of this layer rather than alternative sources of truth.

## Install

```bash
python -m pip install -e .
```

## Project lifecycle

1. `project_registry.py` scans sources without mutation, then assigns stable document IDs
   and package paths only to explicitly registered files.
2. `people_registry.py` distinguishes original annotators, active curators, and accountable
   data owners; `annotator_registry.py` remains a compatibility interface during migration.
3. `document_citation.py`, `document_rights.py`, and `document_metadata.py` record citation,
   explicit distribution boundaries, and process provenance; `citation_import.py`
   validates structured or CSV citation entry.
4. `color_configuration_registry.py` stores immutable project conventions, while
   `color_mapping.py` preserves supervised document evidence and the applied version.
5. `extraction_draft.py` preserves unresolved raw color evidence for collaboration;
   `extraction_session.py` persists canonical extraction checkpoints and provenance.
6. `quality_flags.py` identifies sentences needing closer attention.
7. `review_state.py` records explicit sentence decisions and corrections.
8. `dataset_metadata.py` safely persists the citable identity, rights, and limitations of
   the project-level release.
9. `package_validator.py` reports structural, semantic, rights, review, and release issues.
10. `curation_state.py` records curator decisions against immutable candidate evidence.
11. `data_owner_approval.py` records per-document distribution accountability.
12. `release_builder.py` creates deterministic approved annotation releases.

## Important interfaces

Validate a project without changing it:

```bash
python -m heva.workflow.package_validator /path/to/project validate
```

Compile carefully edited CSV records back into a package:

```bash
python -m heva.workflow.package_compiler /path/to/project DOCUMENT_ID annotations.csv
```

Command-line execution is an interoperability layer rather than a separate CLI product.

## Package ownership

The project registry owns membership and stable paths. Each document package owns its
metadata, color configuration, extraction evidence, annotations, quality report, and
review state. Dataset-level releases reference accepted packages; they do not replace
document-local evidence.

Pydantic validates required fields and primitive types. HEVA semantic validation checks
relationships such as entity offsets, controlled labels, mapping provenance, BIO
transitions, review completeness, and distribution rights.

## Tests

```bash
python -m pytest tests/workflow
```

See [package validation](../../../docs/VALIDATION.md),
[package layout](../../../docs/reference/package-layout.md), and
[approved export](../../../docs/APPROVED_EXPORT.md).
