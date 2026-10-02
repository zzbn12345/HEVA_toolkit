"""Compare naive and moving-cursor sentence-to-word alignment."""

from __future__ import annotations

import argparse
import statistics
import time
from dataclasses import dataclass

from heva.extraction.pdf_extractor import iter_sentence_word_spans


@dataclass
class Sentence:
    """Minimal spaCy-compatible sentence used by this microbenchmark."""

    text: str
    start_char: int
    end_char: int


def build_fixture(sentence_count: int, words_per_sentence: int):
    """Build ordered sentences and word spans with deterministic offsets."""
    sentences = []
    spans = []
    cursor = 0
    for sentence_index in range(sentence_count):
        sentence_start = cursor
        words = []
        for word_index in range(words_per_sentence):
            text = f"w{sentence_index}_{word_index}"
            start = cursor
            end = start + len(text)
            spans.append({
                "word": {"text": text, "color": None},
                "start": start,
                "end": end,
                "page": 1,
            })
            words.append(text)
            cursor = end + 1
        sentences.append(Sentence(" ".join(words), sentence_start, cursor - 1))
    return sentences, spans


def align_naively(sentences, spans):
    """Reproduce the former full word-list scan for every sentence."""
    return [
        [
            span["word"]["text"]
            for span in spans
            if span["start"] >= sentence.start_char
            and span["end"] <= sentence.end_char
        ]
        for sentence in sentences
    ]


def align_with_cursor(sentences, spans):
    """Run the optimized production alignment and retain comparable output."""
    return [
        [span["word"]["text"] for span in sent_words]
        for _, _, _, sent_words, _ in iter_sentence_word_spans(sentences, spans)
    ]


def median_runtime(function, sentences, spans, repeats: int):
    """Return median runtime after checking deterministic output."""
    durations = []
    expected = None
    for _ in range(repeats):
        started = time.perf_counter()
        result = function(sentences, spans)
        durations.append(time.perf_counter() - started)
        if expected is None:
            expected = result
        elif result != expected:
            raise RuntimeError("Alignment output changed between repetitions")
    return statistics.median(durations), expected


def main() -> None:
    """Run both algorithms on the same synthetic ordered document."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--sentences", type=int, default=2_000)
    parser.add_argument("--words-per-sentence", type=int, default=12)
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()

    sentences, spans = build_fixture(args.sentences, args.words_per_sentence)
    naive_seconds, naive_output = median_runtime(
        align_naively, sentences, spans, args.repeats
    )
    cursor_seconds, cursor_output = median_runtime(
        align_with_cursor, sentences, spans, args.repeats
    )
    if naive_output != cursor_output:
        raise RuntimeError("Optimized alignment does not match the former algorithm")

    print(f"sentences={len(sentences)} words={len(spans)} repeats={args.repeats}")
    print(f"naive_median_seconds={naive_seconds:.6f}")
    print(f"cursor_median_seconds={cursor_seconds:.6f}")
    print(f"speedup={naive_seconds / cursor_seconds:.2f}x")


if __name__ == "__main__":
    main()
