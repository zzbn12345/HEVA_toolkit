# The HEVA dataset

6,324 text units from 8 collections and 197 sources in English, Dutch and Chinese, annotated with
the eight values of the Cultural Value Framework. 1,017 sentences from the highlighted collections
also carry token-level value spans. Licence: [CC BY 4.0](LICENSE). Source documents are not
redistributed.

## 1. Collections and naming

Each collection has one identifier, `<index>_<format>_<year>_<annotators>`, used in every file here
as `collection` or `Folder_ID`. [`collections.csv`](collections.csv) is the reference table that
maps it to the other names in use.

| Index | Identifier | Name in the paper | Format | Sources | Units |
|---|---|---|---|---:|---:|
| 1 | `1_E_2024_MF` | Yazd | E | 64 | 3,760 |
| 2 | `2_A_2025_Mastermind` | V&D Amsterdam | A | 44 | 301 |
| 3 | `3_P_2011_AS` | Willemstad | P | 8 | 724 |
| 4 | `4_P_2011_RB_RF` | Galle | P | 1 | 28 |
| 5 | `5_P_2011_BM_YV` | Stone Town | P | 1 | 265 |
| 6 | `6_E_2026_QL` | Shanghai | E | 1 | 380 |
| 7 | `7_E_2023_EL` | Official Charters | E | 65 | 378 |
| 8 | `8_E_2014_CL` | Singapore | E | 13 | 488 |

Formats: `E` spreadsheet, `A` Atlas.ti project, `P` colour-highlighted PDF or Word document.

`collections.csv` also gives the language, case study, annotators and citation. `year` is the year of
annotation, as reported in the paper. The year in a collection's identifier is part of its name and can
differ.

[`documents.csv`](documents.csv) lists all 197 sources with their collection and number of units.
Documents processed with the HEVA app also have a `document_id` such as `HEVA-2A49E7E20ED2`.
`document_id` is empty for sources that didn't go through the HEVA app; these are identified by their
`source` name. Each collection's social media posts count as one source.

## 2. Files

| File | Content | Units |
|---|---|---:|
| `structured/2_A_2025_Mastermind.xlsx` | V&D Amsterdam (Atlas.ti quotations in table form) | 301 |
| `structured/excels combined dataset.xlsx` | Yazd, Shanghai, Official Charters and Singapore | 5,006 |
| `heva/<collection>/` | HEVA Data Packages of Willemstad, Galle and Stone Town | 1,017 |
| `collections.csv`, `documents.csv` | The reference tables above | |

**Spreadsheets: 52 columns, one text unit per row.**

- *Provenance:* `Folder_ID` (collection), `Sub_Folder_ID`, `Datasource`, `Source_type`, `Format`,
  `Date`, `Data_collector`.
- *Content:* `Case_study`, `Language`, `Sentence` (the text), `Page_number`.
- *Label counts:* `Number_of_L1_labels`, `Number_of _L2_labels`, `Classification_hierarchy`.
- *Values:* `1` to `8` are 1 when the unit expresses the value: 1 social, 2 economic, 3 political,
  4 historic, 5 aesthetical, 6 scientific, 7 age, 8 ecological.
- *Sub-values:* `1-1` to `8-3`. No unit has sub-value labels in this release.

A unit whose eight value columns are all 0 was read by the annotators and judged to express no value.

**Data Packages:** see [What is a HEVA Data Package?](../docs/DATA_PACKAGE.md).

## 3. Loading

```python
import pandas as pd

units = pd.read_excel("data/structured/excels combined dataset.xlsx", dtype=str)
yazd = units[units["Folder_ID"] == "1_E_2024_MF"]
```

For training and evaluation, use the fixed splits in [`benchmark/`](../benchmark/README.md). There,
identical texts are merged, so their counts are lower than the totals here.
