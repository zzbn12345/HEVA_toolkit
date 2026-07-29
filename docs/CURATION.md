# Local curator review

The first F10 slice provides a read-only curator queue at `/curation`. It works entirely
from the local HEVA project and does not require GitHub or Git knowledge.

The queue combines two existing sources of truth:

- `data/project-registry.json` supplies source names and workflow states;
- `heva.workflow.package_validator` supplies complete structural, semantic, provenance,
  rights, mapping, extraction, and review findings.

The default **Awaiting review** filter shows documents whose registry state is
`in_review`. Curators may also inspect documents that need validation attention, all
validator-passing documents, or every registered document. Each row links to the
document's read-only annotation and PDF evidence.

This slice intentionally does not expose Accept, Reject, Quarantine, or Request changes.
Those actions will be added only after local curator identity, immutable candidate
checksums, validator snapshots, decision evidence, timestamps, and requested-change
records are persisted. Until then, command-line approval remains development
infrastructure rather than the intended researcher-facing workflow.
