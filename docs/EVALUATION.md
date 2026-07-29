# Accuracy and performance evidence

HEVA does not currently have enough approved evidence for a client-facing accuracy,
throughput, or time-saving claim. Prototype success on a few documents is useful for
development, but it is not a representative evaluation.

The scorer in `heva.workflow.evaluation` keeps unlike questions separate:

- exact-record precision and recall;
- annotation-span precision and recall;
- controlled-label accuracy for matched spans;
- failures grouped by expected label;
- Ollama curator-correction and abstention rates;
- estimated human time saved;
- elapsed extraction time; and
- peak memory.

An overall pass requires a curator-approved manifest covering structured annotations,
flattened highlights, colored fonts, mixed conventions, decorations, malformed PDFs, and
explicitly unsupported scans. A scan should pass only when HEVA returns the approved
unsupported-input error; it must not be counted as a successful extraction.

## Corpus layout

Keep the evaluation corpus outside Git when source rights do not permit redistribution.
Paths in the manifest are relative and cannot leave the corpus folder.

```json
{
  "evaluation_version": "1.0",
  "approved_by": "Curator name",
  "approved_at": "2026-07-29",
  "cases": [
    {
      "case_id": "structured-001",
      "category": "structured_annotations",
      "source_reference": "internal-corpus/structured-001",
      "expected_path": "expected/structured-001.json",
      "observed_path": "observed/structured-001.json",
      "expected_support": true
    },
    {
      "case_id": "scan-001",
      "category": "unsupported_scan",
      "source_reference": "internal-corpus/scan-001",
      "observed_path": "observed/scan-001.json",
      "expected_support": false,
      "expected_error_code": "unsupported_scan"
    }
  ]
}
```

A supported observed result wraps canonical records and optional measurements:

```json
{
  "records": [],
  "duration_seconds": 1.25,
  "peak_memory_mb": 84.2,
  "ollama_proposals": 10,
  "curator_corrections": 2,
  "ollama_abstentions": 3,
  "time_saved_seconds": 45
}
```

An unsupported result records the stable error:

```json
{"error_code": "unsupported_scan", "duration_seconds": 0.2}
```

Run the scorer:

```bash
PYTHONPATH=src .venv/bin/python -m heva.workflow.evaluation \
  /path/to/corpus/manifest.json \
  --report /path/to/corpus/evaluation-report.json
```

The command exits non-zero when required categories are missing or any case fails.

## Current product boundary

- Completed extraction checkpoints are reused by source and color-mapping checksums.
- The browser shows extraction progress and stops waiting after two minutes.
- The server does not yet provide cancellable background jobs, bounded workers, streaming
  progress, or per-user resource limits.
- There is no representative concurrent load report with latency percentiles and peak
  memory.
- OCR and image-only scans are unsupported.

Therefore HEVA should currently be described as a supervised research prototype, not a
production extraction service. No percentage accuracy, throughput, concurrency, or time
saving should be quoted until a real approved corpus produces the corresponding report.
