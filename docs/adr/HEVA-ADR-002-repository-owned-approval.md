# HEVA-ADR-002: Repositories own approval and publication workflow

- Status: accepted for Alpha 2
- Date: 2026-08-21
- Decision owner: Product owner

## Context

HEVA currently mixes annotation preparation and validation with submission, curator
acceptance, data-owner approval, and publication-like release states. These layers use
different gates, allowing the interface to say that work is ready while the next action
fails on governance metadata that is outside the Alpha 2 value proposition.

Research data repositories already provide collaboration, review, access control,
versioning, acceptance, and publication workflows.

## Decision

For Alpha 2, HEVA owns the workflow from source registration through validated Data Package
export. A repository or other external process owns submission, approval, and publication.

HEVA exposes three primary states:

1. `working`: one or more required preparation or validation gates remain unresolved;
2. `valid`: canonical data and distribution metadata pass the HEVA specification;
3. `exported`: an exact package was generated from the valid state.

HEVA does not require internal curator acceptance, data-owner approval records, candidate
submission snapshots, or a `done` registry state to export an Alpha 2 Data Package.
Citation, license, explicit distribution permissions, annotation provenance, canonical
annotations, completed sentence review, and successful validation remain export gates.

## Consequences

- “Valid” means fit for HEVA export, not approved or published by a repository.
- Existing curation and approval modules become deferred/experimental and are not part of
  the primary Alpha 2 journey.
- Repository adapters may later transfer packages and approval evidence without changing
  the canonical HEVA validation contract.
- The application must not claim that an exported package has been approved or published.
