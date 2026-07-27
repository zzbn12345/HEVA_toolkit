# HEVA extraction and NLP adapters

`heva_extraction` contains PDF, DOCX, tokenization, stable Word-color normalization, and
automatic color-proposal adapters. Its responsibility ends when candidate annotation
records and raw color evidence have been produced.

It must not approve semantic color mappings, make sentence-review decisions, decide
rights, or build a release.

Install this optional capability with:

```bash
./venv/bin/python -m pip install -r extraction/requirements.txt
```

New code should import, for example:

```python
from extraction.heva_extraction.pdf_extractor import extract_colored_highlights
```

The modules under `src/` are temporary compatibility imports for older scripts.
