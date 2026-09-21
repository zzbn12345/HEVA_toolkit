# Source-diagnostics dummy HEVA project

This example contains one authorized four-page PDF whose tables are visually legible but whose
custom Type3 font has no usable Unicode character map. Copying text from the PDF or using its
ordinary text layer produces cipher-like content.

The workspace is deliberately prepared up to the extraction step. It includes dummy dataset
metadata, a confirmed citation, an assigned original annotator, an active curator, rights
context, and the six approved document color mappings. Extraction and sentence review are the
only incomplete workflow gates.

Use this workspace only to test rejected-source diagnostics and assisted-extraction safeguards.
It is intentionally not export-ready. The source PDF is regression evidence and must not be
included in generated HEVA Data Packages.

See [MANUAL_TEST.md](MANUAL_TEST.md) for the acceptance walkthrough.
