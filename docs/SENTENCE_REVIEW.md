# Auditable sentence review

Every extracted sentence begins with review state `pending`, whether or not it has quality
flags. Flags guide attention; they do not count as human decisions.

Initialize or refresh package review state:

```bash
./venv/bin/python -m heva.workflow.review_state . initialize \
  --document-id HEVA-ABC123
```

Record decisions for an explicitly selected batch:

```bash
./venv/bin/python -m heva.workflow.review_state . decide \
  --document-id HEVA-ABC123 \
  --sentence-id 1 \
  --sentence-id 2 \
  --status approved \
  --reviewer "Research Annotator"
```

Other decision states are `needs_correction` and `excluded`. Each selected sentence gets
its own audit event with actor, timestamp, previous state, new state, and optional comment.
There is no invisible document-level approve-all shortcut.

In the document workspace, users choose a 20- or 50-sentence visible view and may select
individual cards or **Select this visible batch**. Batch actions operate only on IDs that
are both visible and explicitly selected; changing the filter or view removes hidden IDs
from the selection. **To be checked** contains `pending` and `needs_correction`,
**Problematic** contains quality-flagged or correction-needed records, and **Checked**
contains `approved` and `excluded`. Quality flags never select a sentence or create a
decision automatically.

Annotations appear directly in sentence context as colored highlights derived from their
stored character offsets. Hover over a highlight—or focus it with the keyboard—to inspect
its controlled HEVA label and hex color. This avoids separating the extracted phrase from
the sentence an annotator must compare with the source PDF. Overlapping spans preserve all
sentence text and expose every applicable label in the accessible description.

Submit a completely decided document:

```bash
./venv/bin/python -m heva.workflow.review_state . submit \
  --document-id HEVA-ABC123
```

Submission fails while any sentence is `pending` or `needs_correction`. Once all sentences
are `approved` or `excluded` and the citation, color configuration, and extraction gates
also pass, the workspace enables **Submit for curator review**. Submission timestamps the
annotation-process review, moves the registry document to `in_review`, and makes its
sentence evidence read-only.

## Editing annotations

Choose **Edit sentence** on a sentence card to correct the page and every extracted
annotation through structured fields. Each extraction appears as its own editable text
box with its read-only controlled HEVA label and color, including sentences with more than
two extractions. Extracted text is the only editable value: page, label, color, offsets,
tokens, BIO tags, and other implementation details cannot be changed in this dialog.

The edited extraction text must occur exactly in the displayed sentence. HEVA derives
character offsets, categorical `values`, and BIO tags from the visible fields before
validation, so those related representations cannot silently disagree.

Choose **Validate and save correction** to run the complete HEVA contract. If a correction
is invalid, the form stays open and identifies the field and reason—for example, a token
and BIO-tag count mismatch or entity offsets that do not match the entity text. Invalid
changes do not overwrite `annotations.json`.

Use **Citation**, **Color configuration**, or **Annotator profile** at the top of the
document workspace to correct a blocking gate without returning to the project dashboard.
Citation and colors open the selected document directly in its persisted setup workflow.

After a valid correction, the system writes it atomically, reads it back unchanged,
resets the sentence to `needs_correction`, and records the editor plus complete before and
after values in an audit event. The annotator must then inspect and explicitly approve,
exclude, or correct the sentence again.

Review state is stored in `review-state.json` beside `annotations.json`. If re-extraction
changes a record, its prior decision is not silently reused: the sentence returns to
`pending` with a `source_record_changed` audit event.

When a legacy package contains `annotations.json` but no `review-state.json`, opening the
review queue initializes one pending state per extracted sentence. This migration does not
approve, exclude, flag, or otherwise invent any human decision.
