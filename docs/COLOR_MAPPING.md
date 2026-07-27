# Supervised document color mapping

HEVA treats a color-to-label mapping as a document-local research decision. A color does
not have a universal HEVA meaning, and an Ollama or generic-color suggestion is never
approved automatically.

The safe sequence is:

1. Run the PDF or DOCX extractor with an empty color map.
2. Collect the observed hex colors.
3. Create pending proposals from a document legend, Ollama, or a generic convention.
4. Let an annotator approve or explicitly ignore every color.
5. Confirm the complete mapping.
6. Save it into the document's `package-metadata.json`.
7. Only then use approved mappings for candidate HEVA extraction.

There is no global semantic `COLOR_MAP`. Calling either extractor without
`color_label_map` preserves raw hex colors.

## Create proposals from raw extraction

```python
from heva.workflow.color_mapping import (
    observed_colors_from_records,
    propose_color_configuration,
)
from heva.extraction.pdf_extractor import extract_colored_highlights

records = extract_colored_highlights("documents/source.pdf", color_label_map={})
observed = observed_colors_from_records(records)

configuration = propose_color_configuration(
    observed,
    ollama_suggestions={
        "#FFFF00": "historic",
        "#FF00FF": "economic",
    },
    ollama_confidence={
        "#FFFF00": 0.72,
        "#FF00FF": 0.64,
    },
)
```

When calling the legacy extractor directly from the project root, start Python with
`PYTHONPATH=src ./venv/bin/python` so its existing absolute imports can be resolved.

Each proposal contains:

- normalized `#RRGGBB` hex;
- a readable color name;
- black or white contrasting text color for a future interface;
- suggested and approved HEVA labels;
- proposal method and optional confidence;
- `pending_review`, `approved`, or `ignored` status;
- reasoning or an ignore explanation.

When a document legend is supplied, it takes precedence over Ollama and generic
conventions:

```python
configuration = propose_color_configuration(
    observed,
    legend_mapping={"#FFFF00": "historic"},
    ollama_suggestions={"#FFFF00": "economic"},
)
```

The yellow proposal uses `historic` with method `document_legend`, but it remains pending
until a person reviews it.

## Resolve and confirm colors

```python
from heva.workflow.color_mapping import confirm_color_configuration, resolve_color

configuration = resolve_color(configuration, "#FFFF00", label="historic")
configuration = resolve_color(
    configuration,
    "#000080",
    ignore_reason="Decorative page header, not a heritage annotation.",
)
configuration = confirm_color_configuration(
    configuration,
    confirmed_by="Research Annotator",
)
```

Confirmation fails if a color is pending, an approved color lacks a controlled HEVA
label, or an ignored color lacks an explanation.

## Save the document-local decision

```python
from heva.workflow.color_mapping import save_color_configuration

save_color_configuration(
    ".",
    "HEVA-ABC123",
    configuration,
)
```

This updates only the `color_configuration` section of:

```text
data/packages/HEVA-ABC123/package-metadata.json
```

It does not create extracted annotations or change the source document.

Load the confirmed map before semantic extraction:

```python
from heva.workflow.color_mapping import load_confirmed_color_mapping

mapping = load_confirmed_color_mapping(".", "HEVA-ABC123")
records = extract_colored_highlights(
    "documents/source.pdf",
    color_label_map=mapping,
)
```

Loading fails if a person has not confirmed the document-local configuration.

Alternatively, a pending automatic proposal can be deliberately authorized for extraction
without claiming that it is scientifically approved:

```python
from heva.workflow.color_mapping import authorize_pending_mapping_for_extraction

configuration = authorize_pending_mapping_for_extraction(
    configuration,
    authorized_by="Research Annotator",
)
save_color_configuration(".", "HEVA-ABC123", configuration)
```

This records who made the decision and when. The resulting extraction is persisted with
`mapping_status: pending_review` and remains unsuitable for curator review until the map
is confirmed.

## Write automatic proposals from another workflow

Automatic classification and package persistence are separate operations. After an
Ollama-facing function has produced suggestions, an initializer, web route, or other
orchestrator can store them with:

```python
from heva.workflow.color_mapping import write_automatic_color_proposals

write_automatic_color_proposals(
    ".",
    "HEVA-ABC123",
    observed_colors=["#FFFF00", "#FF00FF"],
    suggestions={
        "#FFFF00": "historic",
        "#FF00FF": "economic",
    },
    reasoning={
        "#FFFF00": "Suggested from highlighted sentence context.",
        "#FF00FF": "Suggested from highlighted sentence context.",
    },
    confidence={
        "#FFFF00": 0.72,
        "#FF00FF": 0.64,
    },
    source_mechanisms={
        "#FFFF00": "word_font_color",
        "#FF00FF": "word_font_color",
    },
)
```

This function does not call Ollama and does not extract annotations. It only adapts a
classifier result into the package contract. Every suggestion is written as
`pending_review`, with no approved `label`.

The function refuses to replace any existing color configuration, including an earlier
pending proposal. Replacement must be an explicit future workflow rather than an
initializer side effect.

## Batch safety

```python
from heva.workflow.color_mapping import validate_shared_batch_mapping

report = validate_shared_batch_mapping(
    {
        "HEVA-ONE": first_configuration,
        "HEVA-TWO": second_configuration,
    }
)
```

A shared mapping is allowed only when the palettes match and every document has its own
human confirmation. A palette mismatch means the documents must use independent mappings.

## Current limit

The older `src/heva/extraction/auto_color_mapper.py` prototype still writes a sidecar map and immediately
extracts using its Ollama result. It does not call the package writer yet and should not
be treated as a curator-ready HEVA workflow. A later initializer or web workflow can
compose automatic classification with `write_automatic_color_proposals` without changing
the classifier itself.
