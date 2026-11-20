# HEVA-ADR-003: Projects may define value sets for color annotations

- Status: accepted
- Date: 2026-11-20
- Decision owner: Product owner

## Context

HEVA maps the highlight colors of an annotated document to a controlled vocabulary. Until
now that vocabulary was fixed to the eight HEVA heritage values (`social`, `economic`,
`political`, `historic`, `aesthetical`, `scientific`, `age`, `ecological`). Researchers who
annotate other kinds of datasets, such as health documents, cannot name the values their
annotation protocol uses, even though the rest of the HEVA workflow — citation, extraction,
sentence review, validation, and Data Package export — applies to them unchanged.

The Alpha 2 EVA specification lists a change to the controlled label vocabulary as a stop
condition that needs human approval. This record describes the change and records that
approval, as HEVA-ADR-001 requires.

## Decision

1. The eight heritage values become the built-in value set `heva-heritage-values`, version 1.
   It is read-only, never stored in project files, and remains the default everywhere.
   `HEVA_LABELS` and the default record contract are unchanged.
2. A curator can create additional **value sets** for a project in `.heva/value-sets.json`.
   Like project palettes, value sets are immutable and versioned: a change appends a new
   version, and each version records who created it and when.
3. A **project palette version names the exact value set version** its colors map to.
   Sharing a confirmed mapping with other documents also shares its palette reference. A
   palette without a value-set reference keeps meaning the heritage values, so existing
   projects are unaffected. Documents and records already point to their palette version,
   which in turn identifies their vocabulary.
4. While project files are read, any label defined by the project's value sets is
   accepted. Validation then checks every document against the exact value set of its
   palette and reports `label_outside_value_set` when the two differ, so a Data Package
   cannot silently mix vocabularies.

## Consequences

- Heritage-only projects behave as before; the existing contract tests remain the gate.
- Labels in a Data Package are only meaningful together with the value set that defines
  them. Every release therefore lists the value sets it uses, with their values, in
  `datapackage.json` and `heva-annotations.json`, and each document names its value set.
  Heritage releases name the built-in heritage value set. Validation guarantees that a
  document's labels belong to the value set it is released with.
- Project tools accept the project's value sets, including the CSV compiler
  (`package_compiler`). Command-line tools that run without a project (`evaluation`,
  `validate_records`) still validate against the heritage values.
- The benchmark baselines (`src/heva/baselines`) are defined for the heritage values only and
  are not affected.
- The Alpha 2 EVA specification should be reassessed, as its `reassess_when` clause requires
  when the controlled vocabulary changes with human approval.
