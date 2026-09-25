# Manual acceptance test: rejected-source diagnostics

This walkthrough verifies F14.25 using the included `broken-type3-font.pdf`. Perform it after
the source-diagnostics interface has been implemented.

## Preparation

1. Start HEVA using the normal local application instructions.
2. Choose **Open existing project** and select this `source-diagnostics-dummy-project` folder.
3. Confirm that the project contains one document named `broken-type3-font.pdf`.
4. Confirm that Curator, Original annotator, Citation, and Color configuration are complete,
   while Extraction and Sentence review remain incomplete.
5. Open the PDF outside HEVA, inspect a table, and copy a sentence from it into a plain-text
   editor. Confirm that the pasted result is cipher-like even though the page is readable.

This visual/copy comparison establishes that the problem is the PDF text encoding, not that
the table itself is unreadable.

## Normal extraction remains the default

1. Start normal extraction for the registered document.
2. Confirm that HEVA rejects the extraction instead of saving the garbled text.
3. Confirm that the message explains that the PDF has no reliably readable Unicode text layer.
4. Confirm that the failed attempt offers **Run source diagnostics** as the next action.
5. Confirm that OCR has not started and no extracted annotation records were created.

## Inspect the diagnostic result

1. Select **Run source diagnostics**.
2. Confirm that HEVA identifies pages 1–4 as affected.
3. Confirm that the explanation identifies a broken Unicode/font mapping. Technical evidence
   may mention a Type3 font and a missing `ToUnicode` map, but the main message must remain
   understandable without PDF expertise.
4. Confirm that HEVA recommends OCR-assisted span alignment as an available next step.
5. Confirm that the result describes OCR as optional and does not claim that OCR has run.

## Create an OCR candidate explicitly

1. Select **Start OCR-assisted extraction** and confirm the action.
2. Confirm that HEVA reports candidate records for pages 1–4 and a mean OCR confidence.
3. Confirm that the result says the records remain separate and require researcher review.
4. Inspect the candidate list, comparing representative colored spans with the source PDF.
   On table pages, confirm each candidate contains only the relevant source cell (for example,
   the first candidate is the Franciscan chapel quotation) rather than headers and neighboring
   Argumentation or Attributes cells. Text outside detected tables must retain normal paragraph
   grouping.
5. Confirm that Extraction and Sentence review remain incomplete; creating a candidate must
   not make the document valid or export-ready.
6. Inspect `.heva/documents/HEVA-DEMO-BROKEN-FONT/ocr-candidate.json` and confirm its status is
   `pending_review`, `requires_review` is true, and it records Tesseract provenance.
7. Select **Use candidate and create annotations** and confirm the decision.
8. Confirm that the ordinary annotation review opens with every OCR-derived sentence pending.
   Correct OCR mistakes and approve or exclude each sentence through the normal review flow.
9. Confirm that the candidate status is now `promoted`, Extraction is complete, and Sentence
   review remains incomplete until every generated record receives a decision.
10. Return to the annotation section and confirm that **Extract annotations** is no longer
    offered. Continue in the annotation review; only the explicit **Rebuild extraction** action
    may replace the current evidence.

OCR execution is synchronous in this first four-page evaluation slice; background progress and
cancellation remain required before using it on large PDFs.

## Safety inspection

1. Close and reopen the project. Confirm that the diagnostic result remains associated with
   the same document, if diagnostic persistence is part of the implemented slice.
2. Confirm that an ordinary extraction request is rejected because current annotations already
   exist. If you deliberately choose **Rebuild extraction**, confirm that the broken source is
   rejected rather than being silently routed through OCR.
3. Verify the source checksum:

   ```text
   2ef43c75037ea820d46f1f4f43262b6b29d9151fe966ce3433d6dbd9b3d2de5c
   ```

4. Confirm that no source file was replaced, renamed, or rewritten.

## Pass criteria

The walkthrough passes when normal extraction rejects the corrupt text layer, diagnostics give
an actionable cause and identify pages 1–4, OCR starts only after explicit confirmation, its
output requires sentence review after promotion, the interface does not loop back to ordinary
extraction, and the source checksum remains unchanged.

Record the HEVA version or commit, operating system, result, and any screenshots with the Alpha
evaluation evidence. A changed checksum, automatic OCR, persisted gibberish, or a successful
extraction claim is a failure.
