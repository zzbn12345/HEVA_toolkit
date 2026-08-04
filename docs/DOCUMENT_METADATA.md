# Package metadata and review readiness

The package metadata module records who created a source, who annotated it, how the
annotations were produced, how document colors were interpreted, how the source can be
cited, and what may be distributed. One `metadata.json` describes each registered
document package.

The module does two different jobs:

1. Pydantic checks that the JSON has the expected fields and basic value types.
2. HEVA review-readiness validation checks whether the provenance and rights information
   is complete enough to send to a curator.

Saving metadata does not automatically declare it ready. Always inspect the readiness
report first.

## Prerequisite: register the source documents

The document must already exist in `.heva/project.json`. Initialize or synchronize
the registry from the project root:

```bash
./venv/bin/python -m heva.workflow.project_registry . --source-dir documents
```

Copy the relevant `document_id` from the registry. The ID connects the metadata to the
correct source and document package. Synchronization also creates an incomplete
`metadata.json` template for every registered document. It intentionally leaves
unknown authorship, rights, extraction, and color decisions empty rather than guessing.

## Create a reusable annotator profile

Annotator profiles use JSON:

```json
{
  "name": "Research Annotator",
  "orcid": "0000-0002-1825-0097"
}
```

For a standalone script, this may be saved as `data/annotator.json`. The web application
stores multiple reusable records and their active selection in `.heva/annotators.json`,
migrating the former single file when necessary. The source creator and annotator are
separate concepts: the source creator belongs under `source.creators`; the person doing
the HEVA annotation belongs under `annotator`.

Load the profile in Python:

```python
from heva.workflow.document_metadata import load_annotator

annotator = load_annotator("data/annotator.json")
```

## Build the package metadata

```python
from heva.workflow.document_metadata import (
    AnnotationProcessMetadata,
    ColorConfigurationMetadata,
    ColorMappingMetadata,
    PackageMetadata,
    ResourceMetadata,
    ReviewMetadata,
    RightsMetadata,
    SourceMetadata,
)

metadata = PackageMetadata(
    document_id="HEVA-EXAMPLE",
    source=SourceMetadata(
        title="Galle heritage report",
        creators=["Example Author"],
        citation="Example Author (2011), Galle heritage report.",
        reference="https://example.org/galle-report",
    ),
    annotator=annotator,
    rights=RightsMetadata(
        access_level="restricted",
        authorization_status="authorized",
        authorization_date="2026-07-23",
        authorized_by="Rights holder",
        evidence_reference="rights/galle-authorization",
        source_distribution_allowed=False,
        extracted_text_distribution_allowed=True,
        annotation_distribution_allowed=True,
        license="CC-BY-4.0",
    ),
    annotation_process=AnnotationProcessMetadata(
        method="automatic",
        extractor="HEVA PDF extractor",
        extractor_version="0.1.0",
        performed_at="2026-07-23T14:30:00Z",
        review=ReviewMetadata(
            all_sentences_require_approval=True,
            completed=True,
            reviewed_at="2026-07-23T15:30:00Z",
        ),
    ),
    color_configuration=ColorConfigurationMetadata(
        detection_method="automatic",
        document_consistency="consistent",
        human_confirmed=True,
        confirmed_by="Research Annotator",
        confirmed_at="2026-07-23T14:45:00Z",
        colors=[
            ColorMappingMetadata(
                hex="#FFFF00",
                color_name="Yellow",
                text_color="#000000",
                suggested_label="historic",
                label="historic",
                display_name="Historical value",
                method="document_legend",
                confidence=1.0,
                status="approved",
            )
        ],
    ),
    resources=[
        ResourceMetadata(
            name="annotations",
            path="annotations.json",
            format="json",
            record_count=128,
        )
    ],
)
```

`access_level` must be `public`, `restricted`, or `private`.
`authorization_status` must be `authorized`, `pending`, `unknown`, or `denied`.

Distribution permission is recorded separately for:

- the original source document;
- extracted text;
- HEVA annotations.

This separation matters because permission to publish annotations does not necessarily
include permission to redistribute the PDF or its extracted text.

`color_configuration` records the colors observed in this document and their controlled
HEVA labels. Automatic detection is only a proposal: `human_confirmed` must be true, and
the responsible person and confirmation time must be recorded before curator review.

`resources` describes the extracted data without embedding it in the metadata. The
annotation records remain in a separate `annotations.json` file in the same package.

If no DOI or URL exists, leave `reference` empty and give an explicit explanation:

```python
metadata.source.reference = None
metadata.source.not_findable_reason = (
    "Internal student work without a public DOI or URL."
)
```

An explained non-findable source produces a warning but does not block review.

## Check whether it is ready for review

```python
from heva.workflow.document_metadata import validate_review_readiness

report = validate_review_readiness(metadata)

if report.ready:
    print("Ready for curator review")
else:
    for issue in report.blocking_issues:
        print(f"{issue.path}: {issue.message}")

for issue in report.issues:
    if issue.severity == "warning":
        print(f"Warning: {issue.message}")
```

Review is blocked when required provenance, annotator identity, authorization, access,
distribution, process, color-confirmation, annotation-resource, or license information is
missing. Sentence review must also be complete.
Each issue provides a stable `code`, a JSON-style `path`, a severity, and a human-readable
message for use by scripts or a future web interface.

## Save it in the document package

```python
from heva.workflow.document_metadata import save_package_metadata

saved_path = save_package_metadata(".", metadata)
print(saved_path)
```

The module writes:

```text
data/documents/<document-id>/metadata.json
```

It also adds `metadata_path` to the matching document in
`.heva/project.json`. Metadata cannot be saved for an unregistered document.

The resulting package keeps description and data separate:

```text
data/documents/<document-id>/
├── metadata.json
└── annotations.json
```

At present this module is a Python interface, not a standalone command-line program.
