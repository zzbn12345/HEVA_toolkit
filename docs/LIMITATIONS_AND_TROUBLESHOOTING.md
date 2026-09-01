# Limitations and extraction troubleshooting

HEVA extracts highlighted natural-language sentences from PDF and DOCX files. It is not a
general-purpose OCR or table-extraction system. Always compare extracted sentences with the
source document before approving them.

## PDF and table limitations

HEVA can process a tabular PDF when the file contains searchable Unicode text and its words,
colors, and reading order can be recovered reliably. A table is therefore not rejected merely
because it is a table.

Results may be incomplete or appear in an unnatural order when a PDF contains complex tables,
merged cells, isolated labels, fragmented phrases, overlapping columns, or little sentence-like
text. Scanned or image-only pages require OCR before HEVA can extract their text and colors.

Some PDFs look correct in a viewer but contain broken embedded font mappings. Copying text from
these files may produce symbols or gibberish. HEVA rejects a sufficiently long page whose text
layer is dominated by such encoding artifacts. If one selected page is unreadable, the selected
extraction fails as a whole and HEVA does not save a partial, corrupted extraction.

## Troubleshoot PDF extraction

### The PDF is reported as unreadable

1. Open the PDF in a viewer and try to select and copy a complete sentence.
2. Paste it into a plain-text editor.
3. If the pasted text is missing or unreadable, apply OCR or re-export the original document
   with searchable Unicode text and embedded fonts.
4. Open or import the repaired PDF in HEVA and run color discovery and extraction again.

Do not continue by assigning HEVA labels to gibberish or corrupted raw colors. The repaired PDF
must preserve the intended colored annotations for HEVA to recover them.

### No colored annotations are found

- Confirm that the selected page range contains the annotations.
- Confirm that the annotations are represented as PDF highlights, colored backgrounds, or
  colored text rather than only as pixels in a scanned image.
- Try selecting and copying an annotated sentence to verify that the page has a text layer.
- Apply OCR or re-export the source when the page is image-only.

HEVA preserves the previous extraction draft when a new run finds no colored annotations.

### A table extracts in the wrong order

Compare every extracted sentence with the source. Correct or exclude unreliable sentences in
the review interface. If the table cannot be reviewed as coherent natural-language sentences,
convert it to a more accessible source representation or record it outside the automatic HEVA
extraction workflow.

### A repaired PDF still fails

Record the source application, export or OCR method, affected page numbers, and the exact HEVA
error message. Keep the original and repaired files so the failure can be reproduced without
using synthetic test data alone.
