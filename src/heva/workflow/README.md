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

1. `project_registry.py` assigns stable document IDs and package paths.
2. `annotator_registry.py` stores reusable project annotator profiles.
3. `document_citation.py` and `document_metadata.py` record citation, rights, and process
   provenance.
4. `color_mapping.py` stores supervised document-local color decisions.
5. `extraction_session.py` persists extraction checkpoints and mapping provenance.
6. `quality_flags.py` identifies sentences needing closer attention.
7. `review_state.py` records explicit sentence decisions and corrections.
8. `package_validator.py` reports structural, semantic, rights, review, and release issues.
9. `curation_state.py` records curator decisions against immutable candidate evidence.
10. `release_builder.py` creates deterministic approved annotation releases.

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
