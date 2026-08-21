# HEVA-ADR-001: Versioned EVA specifications require human approval

- Status: accepted
- Date: 2026-08-21
- Decision owner: Product owner

## Context

HEVA evolves through hypotheses about researcher needs and the software changes intended
to satisfy them. If an implementation agent or script can silently weaken its own
acceptance criteria, passing evaluation no longer demonstrates that the product outcome
was achieved. Manual or scripted changes can also corrupt canonical project JSON.

## Decision

EVA specifications are version-controlled research and engineering contracts.

1. Every EVA specification has an explicit schema version, lifecycle status, hypothesis,
   acceptance thresholds, protected behaviour, and human owner.
2. Agents and scripts may draft changes and collect evidence, but only a human may activate
   or supersede a specification.
3. A material change to a hypothesis, business criterion, threshold, protected behaviour,
   or HEVA data contract creates a new specification version. The previous version remains
   in Git history and must not be rewritten to fit an implementation.
4. Implementation stops when satisfying the work would require weakening an active EVA
   specification.
5. HEVA may diagnose corruption and prepare a repaired copy. Replacing or deleting
   canonical project data requires explicit human approval, with the original retained
   until approval.

## Consequences

- Evaluation intent and changes are reviewable in Git.
- Test evidence cannot redefine success automatically.
- Some changes require an additional human gate, even when technically straightforward.
- Superseded specifications accumulate, but provide a traceable history of changing
  hypotheses and product decisions.
