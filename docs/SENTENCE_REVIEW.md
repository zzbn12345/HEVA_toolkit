# Auditable sentence review

Every extracted sentence begins with review state `pending`, whether or not it has quality
flags. Flags guide attention; they do not count as human decisions.

Initialize or refresh package review state:

```bash
./venv/bin/python -m management.heva_management.review_state . initialize \
  --document-id HEVA-ABC123
```

Record decisions for an explicitly selected batch:

```bash
./venv/bin/python -m management.heva_management.review_state . decide \
  --document-id HEVA-ABC123 \
  --sentence-id 1 \
  --sentence-id 2 \
  --status approved \
  --reviewer "Research Annotator"
```

Other decision states are `needs_correction` and `excluded`. Each selected sentence gets
its own audit event with actor, timestamp, previous state, new state, and optional comment.
There is no invisible document-level approve-all shortcut.

Submit a completely decided document:

```bash
./venv/bin/python -m management.heva_management.review_state . submit \
  --document-id HEVA-ABC123
```

Submission fails while any sentence is `pending` or `needs_correction`. Once all sentences
are `approved` or `excluded`, the registry document moves to `in_review`.

## Editing annotations

`replace_sentence_record` accepts a complete replacement HEVA record and editor identity.
The replacement must pass the HEVA contract. The system writes it atomically, reads it
back unchanged, resets the sentence to `needs_correction`, and records the before and
after values in an audit event.

Review state is stored in `review-state.json` beside `annotations.json`. If re-extraction
changes a record, its prior decision is not silently reused: the sentence returns to
`pending` with a `source_record_changed` audit event.
