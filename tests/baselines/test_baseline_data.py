"""Data loading, splitting and metrics for the T1/T2 baselines (no torch needed)."""

from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

import pytest

from heva.baselines.corpus import (
    LoadReport,
    load_t1_dataset,
    load_t2_dataset,
    read_atlasti_csv,
    read_structured_file,
)
from heva.baselines.labels import BIO_TAGS, VALUES, encode_values, normalize_value
from heva.baselines.metrics import bio_spans, span_scores, tune_thresholds
from heva.baselines.splits import iterative_stratification, split_examples

DUMMY_PACKAGE = Path(__file__).parents[2] / "examples/dummy-data-package"

ATLASTI_HEADER = "ID;Quotation Name;Document;Document Groups;Quotation Content;Comment;Codes;Reference"


def write_atlasti(path: Path, header: str, rows: list[list[str]], encoding="cp1252") -> None:
    lines = [header] + [";".join(f'"{cell}"' for cell in row) for row in rows]
    path.write_bytes("\r\n".join(lines).encode(encoding))


def test_labels_cover_eight_values_and_seventeen_bio_tags() -> None:
    assert len(VALUES) == 8
    assert len(BIO_TAGS) == 17
    assert normalize_value("Aesthetic") == "aesthetical"
    assert normalize_value("Tangible Attribute") is None
    assert encode_values(["age", "social"]) == [1, 0, 0, 0, 0, 0, 1, 0]


def test_heva_package_feeds_both_tasks(tmp_path: Path) -> None:
    shutil.copytree(DUMMY_PACKAGE, tmp_path / "heva" / "release-1")

    t1, _ = load_t1_dataset(tmp_path)
    t2, report = load_t2_dataset(tmp_path)

    assert len(t1) == len(t2) == 92
    assert report.files[0].endswith("heva-annotations.json")
    assert t1[0].values == ("historic", "political")
    assert t2[0].tags[13:17] == ("B-political", "I-political", "I-political", "I-political")


def test_heva_csv_is_used_only_without_json(tmp_path: Path) -> None:
    package = tmp_path / "heva" / "csv-only"
    package.mkdir(parents=True)
    shutil.copy(DUMMY_PACKAGE / "heva-annotations.csv", package)

    t2, report = load_t2_dataset(tmp_path)

    assert report.files == [str(package / "heva-annotations.csv")]
    assert len(t2) == 92


def test_heva_records_with_misaligned_tags_are_skipped(tmp_path: Path) -> None:
    package = json.loads((DUMMY_PACKAGE / "heva-annotations.json").read_text(encoding="utf-8"))
    package["documents"][0]["records"][0]["ner_tags"].pop()
    target = tmp_path / "heva" / "broken"
    target.mkdir(parents=True)
    (target / "heva-annotations.json").write_text(json.dumps(package), encoding="utf-8")

    t2, report = load_t2_dataset(tmp_path)

    assert len(t2) == 91
    assert report.skipped == {"tokens_tags_length_mismatch": 1}


def test_atlasti_labels_come_from_value_codes_not_value_columns(tmp_path: Path) -> None:
    """A quotation coded Before and After must keep its value even if a 0/1 column says 0."""
    source = tmp_path / "export.csv"
    write_atlasti(source, ATLASTI_HEADER + ";Historic", [
        ["1:1", "Oud pand", "Doc A", "Lit", "Een oud pand.", "", "Value: Historic - After\nValue: Historic - Before", "1", "0"],
        ["1:2", "Winkel", "Doc A", "Lit", "Een winkel met café.", "", "Positive (+)\nValue: Aesthetic - Before\nValue: Economic - After", "2", "0"],
        ["1:3", "Plek", "Doc B", "Lit", "Alleen een plek.", "", "Tangible Attribute: Area Before", "3", "0"],
    ])

    examples = read_atlasti_csv(source, LoadReport())

    assert [example.values for example in examples] == [
        ("historic",),
        ("aesthetical", "economic"),
        (),
    ]
    assert examples[1].text == "Een winkel met café."


def test_atlasti_quotation_manager_with_unreadable_header(tmp_path: Path) -> None:
    source = tmp_path / "quotation-manager.csv"
    write_atlasti(source, "ID;????;??;????;????;??;??;??", [
        ["1:1", "Gebouw", "Doc A", "Lit", "Een mooi gebouw.", "", "Value: Aesthetic - Before", "1"],
    ])

    examples = read_atlasti_csv(source, LoadReport())

    assert examples[0].values == ("aesthetical",)
    assert examples[0].document == "Doc A"


def test_atlasti_file_without_value_codes_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "not-atlasti.csv"
    write_atlasti(source, ATLASTI_HEADER, [["1", "x", "Doc", "", "Tekst.", "", "Other code", "1"]])

    with pytest.raises(ValueError, match="no 'Value: <name>' codes"):
        read_atlasti_csv(source, LoadReport())


def test_duplicate_quotations_across_exports_are_merged(tmp_path: Path) -> None:
    atlasti = tmp_path / "atlasti"
    atlasti.mkdir()
    row = ["1:1", "Plek", "Doc A", "Lit", "Het is een mooi punt.", "", "Value: Social - After", "1"]
    write_atlasti(atlasti / "a.csv", ATLASTI_HEADER, [row])
    write_atlasti(atlasti / "b.csv", ATLASTI_HEADER, [row[:6] + ["Value: Aesthetic - Before", "1"]])

    t1, report = load_t1_dataset(tmp_path)

    assert [example.values for example in t1] == [("aesthetical", "social")]
    assert report.merged_duplicates == 1
    assert report.conflicting_duplicates == 1


def test_iterative_stratification_is_seeded_and_keeps_rare_labels_in_each_split() -> None:
    items = [(f"id{i}", ["common"] + (["rare"] if i % 10 == 0 else [])) for i in range(100)]

    first = iterative_stratification(items, seed=1)
    again = iterative_stratification(items, seed=1)

    assert first == again
    sizes = {name: sum(1 for part in first.values() if part == name) for name in ("train", "validation", "test")}
    assert sizes == {"train": 70, "validation": 10, "test": 20}
    rare = {name: sum(1 for item_id, labels in items if "rare" in labels and first[item_id] == name)
            for name in sizes}
    assert rare == {"train": 7, "validation": 1, "test": 2}


def test_split_refuses_too_few_examples(tmp_path: Path) -> None:
    shutil.copytree(DUMMY_PACKAGE, tmp_path / "heva" / "p")
    t2, _ = load_t2_dataset(tmp_path)

    with pytest.raises(ValueError, match="too few"):
        split_examples(t2[:3], seed=13)


def test_bio_spans_follow_conlleval_chunking() -> None:
    tags = ["B-social", "I-social", "O", "I-age", "I-age", "B-age", "I-social"]

    assert bio_spans(tags) == {(0, 2, "social"), (3, 5, "age"), (5, 6, "age"), (6, 7, "social")}


def test_span_f1_requires_exact_boundaries_and_value() -> None:
    gold = [["B-social", "I-social", "O", "B-age"]]
    predicted = [["B-social", "O", "O", "B-age"]]

    scores = span_scores(gold, predicted)

    assert scores["per_class"]["age"]["f1"] == 1.0
    assert scores["per_class"]["social"]["f1"] == 0.0
    assert scores["micro"]["f1"] == 0.5
    assert "historic" in scores["classes_without_support"]


def test_thresholds_are_tuned_per_class() -> None:
    gold = [encode_values(["social"]), encode_values(["age"]), encode_values([])]
    probabilities = [
        [0.3, 0, 0, 0, 0, 0, 0.1, 0],
        [0.1, 0, 0, 0, 0, 0, 0.8, 0],
        [0.2, 0, 0, 0, 0, 0, 0.7, 0],
    ]

    thresholds = tune_thresholds(gold, probabilities)

    assert 0.2 < thresholds[0] <= 0.3
    assert 0.7 < thresholds[6] <= 0.8
    assert thresholds[1] == 0.5


def test_hamming_loss_and_jaccard_similarity() -> None:
    from heva.baselines.metrics import multilabel_scores

    gold = [encode_values(["social", "age"]), encode_values([]), encode_values(["historic"])]
    predicted = [encode_values(["social"]), encode_values([]), encode_values(["economic"])]

    scores = multilabel_scores(gold, predicted)

    # Wrong decisions: age missed, historic missed, economic added = 3 of 3 x 8.
    assert scores["hamming_loss"] == 3 / 24
    # Per text: 1/2, 1.0 (both empty), 0/2.
    assert scores["jaccard_samples"] == (0.5 + 1.0 + 0.0) / 3


STRUCTURED_HEADER = (
    ["Folder_ID", "Sub_Folder_ID", "Datasource", "Source_type", "Format", "Case_study", "Language",
     "Sentence", "Page_number", "Date", "Data_collector", "Number_of_L1_labels",
     "Number_of _L2_labels", "Classification_hierarchy"]
    + [str(code) for code in range(1, 9)]
    + [f"{value}-{sub}" for value in range(1, 9) for sub in (1, 2, 3)]
)


def structured_row(folder: str, source: str, sentence: str, values: dict[int, int]) -> list[str]:
    row = [folder, folder[0] + "_2", source, "Policy", "Excel", "Case", "English", sentence,
           "1", "2024", "Annotator", str(sum(values.values())), "0", "1"]
    row += [str(values.get(code, 0)) for code in range(1, 9)]
    return row + ["0"] * 24


def write_structured_csv(path: Path, rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        csv.writer(handle).writerows([STRUCTURED_HEADER] + rows)


def test_structured_values_count_any_positive_cell(tmp_path: Path) -> None:
    """A value coded twice is stored as 2 in some files and must still count once."""
    source = tmp_path / "final.csv"
    write_structured_csv(source, [
        structured_row("2_A_2025_X", "Doc A", "Een oud pand.", {4: 2, 5: 1}),
        structured_row("2_A_2025_X", "Doc A", "Alleen tekst.", {}),
        structured_row("2_A_2025_X", "Doc B", "  ", {1: 1}),
    ])
    report = LoadReport()

    examples = read_structured_file(source, report)

    assert [example.values for example in examples] == [("historic", "aesthetical"), ()]
    assert examples[0].collection == "2_A_2025_X"
    assert examples[0].document == "Doc A"
    assert examples[0].source == "structured"
    assert report.skipped == {"structured_empty_sentence": 1}


def test_structured_file_without_value_columns_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "other.csv"
    source.write_text("Sentence,Label\nTekst.,social\n", encoding="utf-8")

    with pytest.raises(ValueError, match="value columns 1-8"):
        read_structured_file(source, LoadReport())


def test_structured_xlsx_is_read_from_the_matching_sheet(tmp_path: Path) -> None:
    openpyxl = pytest.importorskip("openpyxl")
    workbook = openpyxl.Workbook()
    workbook.active.append(["Column_name", "Definition"])
    data = workbook.create_sheet("Data")
    header = [int(name) if name.isdigit() and name != "1" else name for name in STRUCTURED_HEADER]
    data.append(header)
    row = structured_row("8_E_2014_CL", "Doc", "Founded in 1859.", {1: 1, 8: 1})
    data.append([int(cell) if cell.isdigit() else cell for cell in row])
    workbook.save(tmp_path / "combined.xlsx")

    examples = read_structured_file(tmp_path / "combined.xlsx", LoadReport())

    assert examples[0].values == ("social", "ecological")
    assert examples[0].collection == "8_E_2014_CL"


def test_t1_combines_structured_spreadsheets_with_packages(tmp_path: Path) -> None:
    shutil.copytree(DUMMY_PACKAGE, tmp_path / "heva" / "release-1")
    shutil.copytree(DUMMY_PACKAGE, tmp_path / "heva-only" / "heva" / "release-1")
    (tmp_path / "structured").mkdir()
    write_structured_csv(tmp_path / "structured" / "combined.csv", [
        structured_row("1_E_2024_Y", "Posts", "the city of windcatchers", {8: 1}),
        structured_row("1_E_2024_Y", "Posts", "the city of windcatchers", {8: 1}),
    ])

    packages_only, _ = load_t1_dataset(tmp_path / "heva-only")
    t1, report = load_t1_dataset(tmp_path)

    assert len(t1) == len(packages_only) + 1
    assert report.merged_duplicates == 1
    assert {example.collection for example in t1} == {"release-1", "1_E_2024_Y"}
