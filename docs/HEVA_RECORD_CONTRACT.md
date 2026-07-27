# HEVA extracted-record contract

Version 1.0 formalizes the sentence records already produced by the HEVA extractors. It is
backward compatible with the four `data/*_extracted.json` examples: a missing
`schema_version` is interpreted as legacy version 0.1 and does not rewrite the source.

## Canonical fields

Each record contains a positive `sentence_id` and `page`, the source `sentence`, parallel
`tokens` and `ner_tags`, the distinct HEVA `values`, and labeled character-span `entities`.
The entity offsets must select exactly the entity text from the sentence. Labels and BIO
tags use the controlled eight-value HEVA vocabulary. The labels represented by BIO tags,
categorical `values`, and entities must agree; disagreement is reported as
`bio_value_mismatch`.

The structural descriptor is `schemas/heva-extracted-record.json`. Nested entity, offset,
vocabulary, and BIO semantics are checked by `heva.workflow.contract`, which uses strict
Pydantic input parsing plus semantic contract checks.

## Versioned evidence extension

New records may add:

- `schema_version: "1.0"`;
- an entity-level `color` in normalized `#RRGGBB` form;
- top-level `mapping_provenance` with `method`, `status`, and optional `config_id`.

Mapping status is either `pending_review` or `approved`. The contract records provenance;
it does not approve an automatic mapping or infer that a color has a global HEVA meaning.

## Error classes

JSON parsing failures raise `ContractParseError` with line and column. Decoded records
return all detected `ContractIssue` values with a stable code and JSON-style path, allowing
later CLI and GUI layers to present the same evidence without parsing exception text.

For executable validation examples, expected output, and the limits of what a successful
result proves, see [Validating HEVA extracted records](VALIDATION.md).
