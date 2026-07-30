# HEVA — Heritage Value Extraction and Annotation Dataset

> Collaborative repository for heritage value extraction and data organization — developed at **TU Delft, Faculty of Architecture and the Built Environment** and with support from **TU Delft, Digital Competence Centre**.

---

## Start here

- [Install and run HEVA in the Quickstart](docs/quickstart.md)
- [Browse the complete toolkit documentation](docs/index.md)
- [Understand project validation](docs/VALIDATION.md)
- [Review current capabilities and limitations](docs/EVALUATION.md#current-product-boundary)

The Quickstart is the recommended entry point for annotators, curators, and technical
contributors. The remainder of this README describes the research dataset and its
annotation framework.

## Table of Contents

1. [Overview](#overview)
2. [Annotation Framework](#annotation-framework)
3. [Highlight Extractor Tool](#highlight-extractor-tool)
4. [Repository Structure](#repository-structure)
5. [Data Sources](#data-sources)
6. [Data Format](#data-format)
7. [How to Contribute](#how-to-contribute)
8. [License & Citation](#license--citation)
9. [Contact](#contact)

---

## Overview

**HEVA** (Heritage Value Extraction and Annotation) is a collaborative dataset developed at TU Delft, Faculty of Architecture and the Built Environment and with support from TU Delft, Digital Competence Centre. It compiles expert-annotated textual data from heritage-related research to support natural language processing (NLP) tasks, particularly **heritage value classification and extraction**.

The corpus brings together annotated texts from multiple heritage research projects conducted at TU Delft, spanning Mastermind course assignments and undergraduate, master's, and doctoral research. All annotations follow the **Heritage Values (HV) framework** proposed by Prof. Ana Pereira Roders.

This dataset is intended for NLP researchers, heritage studies scholars, and students working on value identification, multi-label text classification, or computational heritage analysis.

---

## Annotation Framework

All annotations in this dataset are based on the **Cultural Value Framework** proposed by **Prof. Ana Pereira Roders** (TU Delft, Faculty of Architecture and the Built Environment). This framework provides a structured, two-level taxonomy for identifying and classifying heritage values expressed in textual sources.

The taxonomy consists of **8 top-level value categories (L1)**, each subdivided into **sub-values (L2)**:

| L1 Code | L1 Value | L2 Code | L2 Sub-Value |
|---------|----------|---------|--------------|
| 1 | **social** | 1-1 | social-spiritual |
| | | 1-2 | social-emotional, individual |
| | | 1-3 | social-emotional, collective |
| | | 1-4 | social-allegorical |
| 2 | **economic** | 2-1 | economic-use |
| | | 2-2 | economic-non-use |
| | | 2-3 | economic-entertainment |
| | | 2-4 | economic-allegorical |
| 3 | **political** | 3-1 | political-educational |
| | | 3-2 | political-management |
| | | 3-3 | political-entertainment |
| | | 3-4 | political-symbolic |
| 4 | **historic** | 4-1 | historic-educational |
| | | 4-2 | historic-artistic |
| | | 4-3 | historic-conceptual |
| | | 4-4 | historic-symbolic |
| | | 4-5 | historic-archaeological |
| 5 | **aesthetical** | 5-1 | aesthetical-artistic |
| | | 5-2 | aesthetical-notable |
| | | 5-3 | aesthetical-conceptual |
| | | 5-4 | aesthetical-evidential |
| 6 | **scientific** | 6-1 | scientific-workmanship |
| | | 6-2 | scientific-technological |
| | | 6-3 | scientific-conceptual |
| 7 | **age** | 7-1 | age-workmanship |
| | | 7-2 | age-maturity |
| | | 7-3 | age-existential |
| 8 | **ecological** | 8-1 | ecological-spiritual |
| | | 8-2 | ecological-essential |
| | | 8-3 | ecological-existential |

> **Reference:** Pereira Roders, A. (2007). *Re-architecture: Lifespan rehabilitation of built heritage.* Eindhoven University of Technology.

---

## Highlight Extractor Tool

This repository includes a Python utility located in the [src/](src/) folder that processes PDF and Word (`.docx`) documents to extract colored text highlights. It aligns the highlighted phrases, normalizes punctuation and ligatures, segments sentences using NLP (`spaCy`), maps highlight colors to semantic labels (using manual configuration or zero-shot classification via a local LLM), and outputs training datasets in JSON format with token-level BIO tags.

For detailed architecture, configuration, and execution instructions, please refer to the documentation:
- **Guide**: [README_VE.md](docs/README_VE.md) (Highlight Extractor Guide)
- **Pipeline Architecture**: [ARCHITECTURE.md](docs/ARCHITECTURE.md) (Diagrams and execution details)
- **Automated LLM Classifier**: [AUTO_COLOR_MAPPER_ARCHITECTURE.md](docs/AUTO_COLOR_MAPPER_ARCHITECTURE.md) (Local LLM color classification)
- **Record Validation**: [VALIDATION.md](docs/VALIDATION.md) (Pydantic-backed structure,
  HEVA semantic checks, examples, and validation limits)
- **Project Registry**: [PROJECT_REGISTRY.md](docs/PROJECT_REGISTRY.md) (stable document
  IDs, source synchronization, and project summaries)
- **Document Metadata**: [DOCUMENT_METADATA.md](docs/DOCUMENT_METADATA.md) (citation,
  annotator identity, rights, and curator review readiness)
- **Supervised Color Mapping**: [COLOR_MAPPING.md](docs/COLOR_MAPPING.md) (document-local
  proposals, human confirmation, and batch palette safety)
- **Extraction Sessions**: [EXTRACTION_SESSIONS.md](docs/EXTRACTION_SESSIONS.md)
  (validated package persistence, batch execution, and reviewed collections)
- **Sentence Quality Flags**: [QUALITY_FLAGS.md](docs/QUALITY_FLAGS.md) (deterministic
  review warnings and configurable thresholds)
- **Sentence Review**: [SENTENCE_REVIEW.md](docs/SENTENCE_REVIEW.md) (explicit decisions,
  edit history, and submission readiness)
- **Approved Export**: [APPROVED_EXPORT.md](docs/APPROVED_EXPORT.md) (layered package
  validation, curator approval, and deterministic JSON/CSV release files)
- **Project Boundaries**: [PROJECT_BOUNDARIES.md](docs/PROJECT_BOUNDARIES.md) (separate
  management, extraction/NLP, and optional application dependencies)
- **Guided Review Workflow**: [GUIDED_REVIEW_WORKFLOW.md](docs/GUIDED_REVIEW_WORKFLOW.md)
  (document states, completion, settings, sentence decisions, batching, and PDF review)

Quick CLI example:

```bash
./venv/bin/python -m heva.workflow.validate_records --all
```

The optional web dependencies are installed only when the interface is needed:

```bash
./venv/bin/python -m pip install -e ".[app]"
./venv/bin/python -m heva.app
```

Then open `http://127.0.0.1:8000` and open an existing HEVA project or create one from a
folder containing PDF/DOCX sources. To bypass the chooser for scripting or development,
pass `--project-root /path/to/project`.

## Setup

Use a local virtual environment. For HEVA data management and validation only:

```bash
python3.12 -m venv venv
./venv/bin/python -m pip install --upgrade pip setuptools wheel
./venv/bin/python -m pip install -e .
```

Install the original document extraction and NLP adapters only when needed:

```bash
./venv/bin/python -m pip install -e ".[extraction]"
```

Contributors running the complete root test suite can use:

```bash
./venv/bin/python -m pip install -e ".[dev]"
```

### Troubleshooting dependency installation

- If installation fails with `externally-managed-environment`, you are using system Python. Use `./venv/bin/python -m pip ...`.
- If `pip` command is not found under `pyenv`, use `python -m pip` instead of `pip`.
- Python 3.13 is currently not supported by this dependency set (`spacy==3.7.4` build issues). Use Python 3.12.

---

## Repository Structure

```
HEVA_DCC_collab/
├── src/
│   └── heva/
│       ├── app/                     # Optional FastAPI interface
│       ├── extraction/              # PDF, Word, tokenization, and color evidence
│       └── workflow/                # Registry, review, validation, and release
├── tests/
│   ├── app/
│   ├── extraction/
│   └── workflow/
├── docs/
└── pyproject.toml                  # Base and optional dependency groups
```

### Folder Naming Convention

- **Root-level folders** are numbered sequentially and named as `X_[ProjectName or AuthorName]`
- **`X-1_raw/`** — Contains original annotation files in their native format (Atlas.ti exports, Word documents, PDFs, Excel files, etc.)
- **`X-2_processed/`** — Contains standardised files (`.xlsx` or `.csv`) with at minimum two columns: `sentence` and `label`

---

## Data Sources

This repository contains data from multiple heritage research projects conducted at TU Delft. Each project occupies a numbered folder at the root level. The table below will be updated as new datasets are added.

| # | Project / Author | Source Type | Year | Heritage Type | # Sentences |
|---|-----------------|-------------|------|---------------|-------------|
| — | *(to be populated)* | — | — | — | — |

**Source types include:**
- Mastermind course assignments
- Undergraduate (BSc) research projects
- Master's (MSc) theses
- Doctoral (PhD) dissertations

---

## Data Format

### Target Format (`Example.xlsx`)

The `Example.xlsx` file in the root directory defines the **target annotation format** for all processed data in this repository. All files in `X-2_processed/` folders should conform to this format. The file contains three sheets:

- **Sheet 1** — The dataset table itself (one row per annotated phrase)
- **Sheet 2** — Column definitions and data types
- **Sheet 3** — Full list of value and sub-value labels with descriptions

#### Column Definitions (Sheet 1)

| Column | Required | Data Type | Description |
|--------|----------|-----------|-------------|
| `Source` | Optional | string | The original source (e.g., URL, database, publication) |
| `Case Study` | **Required** | string | The heritage case study the sentence refers to |
| `Title` | Optional | string | Title of the source document (literature, policy, thesis, etc.) |
| `Source_type` | **Required** | string | Type of source: `social media` / `literature` / `policy` / `newspaper` / `stakeholders` / `graduation research` |
| `ID_phrase` | **Required** | float | Serial number uniquely identifying each annotated phrase |
| `Phrase` | **Required** | string | The annotated sentence or text span |
| `Date` | **Required** | float | Date the data was collected |
| `Author` | **Required** | string | Person who collected or annotated the data |
| `Number of labels` | **Required** | float | Count of value labels assigned to this phrase |
| `Classification hierarchy` | **Required** | float | `1` = L1-only classification; `2` = two-level (L1 + L2) classification |
| `1` – `8` | **Required** | binary (0/1) | L1 value labels: social, economic, political, historic, aesthetical, scientific, age, ecological |
| `1-1` – `8-3` | **Required** | binary (0/1) | L2 sub-value labels (see full list in Sheet 3 and the [Annotation Framework](#annotation-framework) section) |

#### Label Encoding

Each phrase may carry **multiple labels** (multi-label classification). Labels are encoded as **binary columns**: `1` = label applies, `0` = label does not apply.

- **L1 columns** (`1` through `8`): one column per top-level value category
- **L2 columns** (`1-1` through `8-3`): one column per sub-value (35 sub-values in total)

When `Classification hierarchy = 1`, only L1 columns are filled. When `Classification hierarchy = 2`, both L1 and L2 columns are filled.

### Raw Data Formats

Files in `X-1_raw/` may include:

| Format | Description |
|--------|-------------|
| `.atp` / Atlas.ti | Qualitative coding projects |
| `.docx` / Word | Annotated text documents |
| `.pdf` | Original source documents |
| `.xlsx` / `.csv` | Tabular annotation data |

---

## How to Contribute

This repository is maintained by the HEVA project team at TU Delft. Contributions are primarily made by project members, student assistants, and affiliated researchers. To add a new dataset:

1. **Create a new folder** following the naming convention: `X_[ProjectName or AuthorName]`, where `X` is the next available number.
2. **Add raw files** to `X-1_raw/` in their original format (Atlas.ti, Word, PDF, Excel, etc.).
3. **Add processed files** to `X-2_processed/` in `.xlsx` or `.csv` format, conforming to the structure defined in `Example.xlsx` (at minimum: `sentence` and `label` columns).
4. **Update the [Data Sources](#data-sources) table** in this README with your project's metadata.
5. Notify the data coordinator (Yan Zhou) or open a pull request for review.

> ⚠️ All processed files must include at minimum a `sentence` column and a `label` column before submission. Please refer to `Example.xlsx` in the root directory for the required format.

---

## License & Citation
**License:** This dataset is currently **not publicly released**. Access is restricted to members of the HEVA project team and affiliated researchers at TU Delft. Redistribution, publication, or use outside the project is not permitted without explicit written consent from the principal investigators.

A formal license and citation format will be added upon public release. If you are interested in accessing this dataset for research purposes, please contact the project team directly (see [Contact](#contact)).

---

## Contact

| Role | Name | Affiliation | Contact |
|------|------|-------------|---------|
| Principal Investigator | Dr. Nan Bai | TU Delft, Faculty of Architecture and the Built Environment | N.Bai@tudelft.nl |
| Principal Investigator | Yan Zhou | TU Delft, Faculty of Architecture and the Built Environment | Yan.Zhou@tudelft.nl |
| HV Framework Consultant | Prof. Ana Pereira Roders | TU Delft, Faculty of Architecture and the Built Environment | A.R.Pereira-Roders@tudelft.nl |
| Student Assistant | Jingze Yin | TU Delft, Faculty of Architecture and the Built Environment | J.Yin-9@student.tudelft.nl |
| DCC support staff| Jose Carlos Urra Llanusa| TU Delft, Digital Competence Centre | J.C.UrraLlanusa@tudelft.nl |

For questions about the dataset, please open an issue on this repository or contact the **Principal Investigators** directly.

---

*Last updated: March 2026*
