# Alpha test protocol

The alpha test asks researchers to reproduce the demonstrated package structure with one
authorized real dataset. It evaluates usability and specification fitness; it is not an
extraction-accuracy benchmark.

## Setup

1. Create a dedicated dataset repository or folder, separate from the toolkit code.
2. Keep source PDFs outside it unless their rights explicitly permit versioning.
3. Install HEVA with app and extraction support and run the environment doctor.
4. Identify at least one original annotator, curator, and responsible data owner.

## Research task

Using the Quickstart, complete at least two real documents:

1. Bind or discover each source.
2. Add citation and per-document rights evidence.
3. Confirm and reuse a project color configuration.
4. Extract and inspect raw/canonical evidence.
5. Review every sentence, including at least one correction or exclusion when applicable.
6. Submit and record a curator decision.
7. Record data-owner approval for each accepted document.
8. Run validation in the GUI and terminal.
9. Generate the JSON and CSV Data Package derivatives.
10. Commit the dataset workspace and confirm another authorized collaborator can clone it,
    bind their local sources, and continue without committed absolute paths.

## Evidence to collect

- Dataset and document count, annotation count, and validation report.
- Any confusing label, action, role, or status wording.
- Every manual workaround or direct JSON edit.
- Extraction failures and unsupported document characteristics.
- Sentences requiring correction and why.
- Time per major step, reported as observation rather than a product claim.
- Whether the resulting JSON/CSV supports the researchers' intended analysis or training.

## Product-owner acceptance questions

- Does the minimum citation profile fit the actual sources?
- Is the controlled HEVA label vocabulary correct and sufficiently documented?
- Does project-level palette versioning reflect real annotation protocols?
- Are annotator, curator, data owner, and reviewer responsibilities understandable?
- Which findings must block curation, owner approval, and release respectively?
- Is the flat CSV appropriate for the intended machine-learning task, or is another
  task-specific adapter required?
- Which real corpus may become the approved evaluation set, and who may approve it?
- Which alpha problems block adoption and which can enter a post-alpha backlog?

The alpha is complete when researchers can create and validate a real candidate package,
explain every unresolved finding, and decide whether the HEVA specification represents
their research data faithfully.
