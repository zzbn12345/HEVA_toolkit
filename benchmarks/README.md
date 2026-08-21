# Extraction performance benchmarks

Run benchmarks from the repository root with the HEVA extraction environment active:

```bash
python benchmarks/benchmark_extraction.py \
  --source "tests/2011 EC Galle part 1(Appendix IV) - Copy.pdf"
```

The benchmark performs one warm-up followed by five measured extractions. It reports every
duration, the median, record count, and a deterministic output checksum. An optimization is
accepted only when the checksum and regression tests remain unchanged.

Benchmark one algorithmic change at a time on the same machine, environment, source, warm-up,
and repetition count. Compare medians rather than a single run. The bundled PDF is useful for
regression and smoke timing, but it is small; performance claims require the researcher-agreed
large and visually complex Alpha corpus.

## Initial baseline

Baseline commit: `511d830ba6658c18f676944056a8c5f892153a47`

Environment: macOS ARM64, Python 3.12.7, PyMuPDF 1.27.2.3, spaCy 3.7.4.

| Source | Size | Records | Runs (seconds) | Median | Output SHA-256 |
|---|---:|---:|---|---:|---|
| `tests/2011 EC Galle part 1(Appendix IV) - Copy.pdf` | 150 KB | 138 | 0.2356, 0.1391, 0.1511, 0.1366, 0.1361 | 0.1391 s | `85e841a0967b49fe65bcc343668910081a14a2f3d6d604848e79314621d6738c` |

The first run above included cold-start effects. The committed benchmark uses an explicit
warm-up so subsequent before/after comparisons are less sensitive to that effect.

## Sentence alignment microbenchmark

The PDF extractor formerly scanned every reconstructed word for every sentence.
The focused benchmark compares that implementation with the ordered moving
cursor used in production:

```bash
python benchmarks/benchmark_sentence_alignment.py
```

This isolates algorithmic scaling. It complements, but does not replace, the
end-to-end extraction benchmark above.

First optimization result on the same environment:

| Scope | Before | After | Result |
|---|---:|---:|---:|
| End-to-end sample PDF | 0.1371 s | 0.1343 s | 1.02x |
| 2,000-sentence alignment, 24,000 words | 1.2700 s | 0.0091 s | 139.46x |

The end-to-end result is the meaningful user-facing measure. The microbenchmark
shows that the targeted loop no longer becomes quadratic as documents grow.

## Page-block sorting microbenchmark

Dense multi-column pages exercise the layout sorter independently:

```bash
python benchmarks/benchmark_block_sort.py
```

The checksum covers both the ordered block IDs and their assigned band/column
metadata, preventing a faster implementation from silently changing layout.

Second optimization result on the same environment:

| Scope | Before | After | Result |
|---|---:|---:|---:|
| End-to-end sample PDF | 0.1343 s | 0.1269 s | 1.06x |
| Dense page layout, 600 blocks | 0.1429 s | 0.0019 s | 75.39x |

The optimized sorter calculates bands and columns once per page. The former
implementation rebuilt those same structures inside the key function for every
block being sorted.

## Highlight matching microbenchmark

The drawing matcher can be measured independently with:

```bash
python benchmarks/benchmark_highlight_matching.py
```

It models a long page containing 1,000 words and 100 colored drawing rectangles.
The checksum records the selected color for every word.

Third optimization result on the same environment:

| Scope | Before | After | Result |
|---|---:|---:|---:|
| End-to-end sample PDF | 0.1269 s | 0.1252 s | 1.01x |
| 1,000 words, 100 drawings | 0.5523 s | 0.0287 s | 19.25x |

The vertical rectangle index limits geometric intersection checks to drawings
near each word. Candidate drawings retain source order so equal-overlap behavior
does not change.

## Text-span matching microbenchmark

When drawing highlights are absent, colored text is located through PDF text
spans. Measure that fallback independently with:

```bash
python benchmarks/benchmark_span_matching.py
```

Fourth optimization result on the same environment:

| Scope | Before | After | Result |
|---|---:|---:|---:|
| End-to-end sample PDF | 0.1252 s | 0.1235 s | 1.01x |
| 1,000 words, 1,000 spans | 0.7317 s | 0.0398 s | 18.38x |

This reuses the same immutable spatial index while preserving the historical
rule that the first containing span is authoritative, even when it is neutral.

## Word grouping microbenchmark

PDF reconstruction associates words with their text blocks. Measure the former
repeated-filter approach with:

```bash
python benchmarks/benchmark_word_grouping.py
```

The checksum covers the order of every word within every block.

Fifth optimization result on the same environment:

| Scope | Before | After | Result |
|---|---:|---:|---:|
| End-to-end sample PDF | 0.1235 s | 0.1241 s | No measurable change |
| 500 blocks, 10,000 words | 0.0770 s | 0.00075 s | 102.54x |

The page now groups each word once and retrieves a block's list directly. The
small sample contains too few blocks for this operation to affect total runtime;
its slight median increase is benchmark noise, not evidence of a regression.

## PyMuPDF text-page microbenchmark

The extractor requests dictionary, word, and block views for every PDF page.
Measure independent text-page construction with:

```bash
python benchmarks/benchmark_textpage_reuse.py
```

The checksum covers the span text and the complete word/block view payloads.
