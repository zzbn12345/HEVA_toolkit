# PDF extraction fixtures

`broken-type3-font.pdf` is an authorized four-page excerpt retained for regression testing.
Its table text uses a custom Type3 font without a usable Unicode character map, so ordinary
PDF text extraction produces cipher-like text even though the page remains visually legible.

The fixture establishes two boundaries:

- normal extraction must reject the unreadable text layer instead of persisting gibberish;
- source diagnostics may inspect and recommend assisted extraction, but must not alter the
  source or start OCR without an explicit user action.

The fixture is test evidence only and is not included in generated HEVA Data Packages.
