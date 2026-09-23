# HEVA extraction adapters

This package reads colored evidence from PDF and DOCX source documents and converts it
into sentence-level HEVA records. Extraction preserves the observed hexadecimal color;
semantic meaning is supplied by a supervised document color mapping.

Extraction is optional. Validation, review, and release management can be installed and
used without the PDF, Word, spaCy, or Ollama dependencies.

## Install

```bash
python -m pip install -e ".[extraction]"
```

## Python usage

```python
from heva.extraction.pdf_extractor import extract_colored_highlights

records = extract_colored_highlights(
    "/path/to/annotated.pdf",
    color_label_map={"#FFFF00": "architectural"},
)
```

For Word documents, use `extract_docx_highlights` from `docx_extractor` with the same
mapping shape.

## Command-line usage

Raw interoperability writes extracted records without creating or changing a
HEVA project:

```bash
python -m heva.extraction.extract_highlights annotated.pdf \
  --color-map color-map.json \
  --output annotations.json
```

A folder can be processed as a batch:

```bash
python -m heva.extraction.extract_highlights source-folder --output-dir extracted
```

To extract registered documents and persist their package metadata, checkpoints,
and canonical annotations, use the project workflow instead:

```bash
python -m heva.curation.extraction_session /path/to/project \
  --document-id HEVA-EXAMPLE \
  --force
```

Use `--all` instead of `--document-id` to process every registered document. Both
commands call the same optimized PDF and DOCX extraction adapters used by the web
application.

For PDFs, progress callbacks and the module command report completed source pages against
the actual page total. This covers the PDF-reading stage only; it does not imply that NLP or
persistence has completed, and extraction is not yet resumable by page.

## Responsibilities

- `pdf_extractor.py` aligns PDF text with colored drawings and font evidence.
- `docx_extractor.py` aligns Word runs and colors with sentences.
- `tokenization.py` provides language detection and sentence/token segmentation.
- `word_colors.py` translates stable Word highlight names into hexadecimal colors.
- `auto_color_mapper.py` optionally asks local Ollama for controlled-label proposals.
- `extract_highlights.py` preserves the original script interoperability layer.

Automatic mappings are proposals, not scholarly decisions. The curation package records
their provenance and requires human confirmation.

## Known boundaries

- Flattened visual colors may not be represented as structured annotation evidence.
- Image-only documents require OCR outside the current extractor.
- Layout reconstruction and sentence segmentation can fail on unusual page structures.
- PDFs with broken embedded font mappings may look correct but expose punctuation-like
  cipher text to software. HEVA rejects long unreadable text layers before creating
  annotations; re-export with searchable Unicode text or apply OCR and retry.
- Successful extraction does not prove complete recall or correct semantic labels.

## Tests

Binary fixtures are generated at runtime so source documents are never committed:

```bash
python -m pytest tests/extraction
```

See the concise [software design](../../../docs/SOFTWARE_DESIGN.md) and
[HEVA validation overview](../../../docs/HEVA_AND_VALIDATION.md).
