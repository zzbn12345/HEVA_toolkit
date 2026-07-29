# Local curator review

HEVA keeps curator review usable without GitHub. The queue at `/curation` combines the
project registry, complete package validation, and package-local curation evidence.

When an annotator selects **Submit for curator review**, the toolkit first runs the
complete package validator and records:

- a SHA-256 identifier for the candidate;
- checksums for annotations, package metadata, and sentence-review evidence;
- the source checksum;
- the complete validator report; and
- the submitting annotator and submission time.

The source PDF is not copied into this snapshot. Before saving a decision, HEVA
recalculates the evidence checksums. A changed package must be reopened and submitted
again, preventing a curator from accepting content different from what they inspected.

## Decisions

Every decision requires the curator name and written evidence:

- **Accept** marks the registry record `done`. This is the only route to `done`.
- **Request changes** requires one or more requested changes and returns the record to
  `in_progress`, where the annotator can correct and resubmit it as a new candidate.
- **Reject** records the reason but does not describe the package as approved.
- **Quarantine** records that the candidate should be isolated for investigation.

The package-local `curation-state.json` retains candidate and decision history. GitHub
credentials are never stored in project JSON.
