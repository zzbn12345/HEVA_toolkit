# HEVA EVA specifications

This directory contains version-controlled Evaluation and Validation Agreements (EVA):
testable contracts connecting a product hypothesis to implementation evidence.

An EVA specification is drafted before implementation. Automated checks and alpha-test
evidence are recorded against it. In accordance with
[HEVA-ADR-001](../docs/adr/HEVA-ADR-001-versioned-eva-specifications.md), only a human may activate,
change, or supersede the contract.

Lifecycle:

1. `draft`: open for human review; does not authorize implementation.
2. `active`: approved criteria govern implementation and acceptance.
3. `superseded`: retained as historical evidence after a human approves a replacement.

The hidden local EDD remains the internal backlog. EVA specifications are committed so
researchers and developers can review why a change is considered complete.
