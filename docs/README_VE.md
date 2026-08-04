# Hybrid_VE: Highlight Extractor

A Python utility that processes PDF/DOCX documents in a directory, extracts colored highlights (capturing their coordinates, text, and hex color codes), maps the colors to semantic labels, splits the text into sentences, and formats the output into a dynamic dataset with token-level BIO tags.

## Environment Details

- **Recommended Python Version**: `3.12.x` (Note: Python `3.13` is currently unsupported due to compilation dependencies in `spaCy`'s internal dependency libraries).
- **Core Dependencies**:
  - `pymupdf` (Version `1.27.2.3`)
  - `spacy` (Version `3.7.4`)

---

## Installation Instructions

1. **Verify or Switch to Python 3.12**
   Ensure you are using a Python 3.12 environment. If you use Conda or `virtualenv`, you can create a clean Python 3.12 environment:
   ```bash
   # Using conda:
   conda create -n hybrid_ve python=3.12
   conda activate hybrid_ve
   
   # Or using venv:
   python3.12 -m venv venv
   source venv/bin/activate
   ```

2. **Install Python Packages**
   Install PyMuPDF, spaCy, and python-docx with the extraction dependency group:
   ```bash
   pip install -e ".[extraction]"
   ```

---

## Project Structure

Below is an overview of the modular codebase architecture:

```
├── data/                             # Folder containing source files and generated outputs
├── docs/                             # Documentation folder
│   ├── ARCHITECTURE.md               # Main system architecture of the extraction pipeline (Mermaid diagrams)
│   ├── AUTO_COLOR_MAPPER_ARCHITECTURE.md # Architecture of the LLM color mapper pipeline
│   └── README_VE.md                  # This highlight extractor guide
├── src/                              # Source code folder
│   ├── auto_color_mapper.py          # Automated color mapping classification script using local Ollama
│   ├── color_mapping.py              # Supervised document-local mapping gate
│   ├── docx_extractor.py             # Word document inline runs and font color highlight extraction
│   ├── extract_highlights.py         # Main CLI entry point script for orchestrating batch file processing
│   ├── pdf_extractor.py              # PDF-specific layout sorting and drawing overlap highlight extraction
│   ├── word_colors.py                # Stable Word highlight-name to hex conversion
│   └── utils.py                      # NLP pipelines, language detection, ligature normalization helpers
├── pyproject.toml                    # Base and optional dependencies
└── README.md                         # Main HEVA repository README
```

---

## Configuring document colors

Semantic color mappings are not configured in Python. Every registered document stores
its own proposals and confirmed decisions in:

```text
data/documents/<document-id>/metadata.json
```

Run an extractor without a mapping to inspect raw normalized hex colors. An Ollama or
generic suggestion remains pending until an annotator approves or explicitly ignores
every color. A confirmed mapping can then be loaded from the document package and passed
to the extractor.

Word's preset names such as `YELLOW`, `PINK`, and `TURQUOISE` are normalized to hex using
`WORD_HIGHLIGHT_TO_HEX` in `src/heva/extraction/word_colors.py`. This is stable DOCX format conversion,
not a HEVA semantic mapping. Custom Word font colors are already read as their RGB hex.

See [COLOR_MAPPING.md](COLOR_MAPPING.md) for the complete supervised workflow.

---

## Automated Color Mapping (Zero-Shot Classification)

The automated color mapping prototype (`src/heva/extraction/auto_color_mapper.py`) uses a local Ollama
model to suggest categories for highlighted text groups. Its suggestions require human
review through the document-local mapping gate before they can be considered HEVA data.

### 1. Requirements

- **Ollama**: Install [Ollama](https://ollama.com) and ensure the application is open and running.
- **Model**: Pull the default `llama3.1:8b` model (or another compatible model like `qwen3.5:9b` or `llama3:8b`):
  ```bash
  ollama pull llama3.1:8b
  ```

### 2. How to Run

Run the automated color mapping script on a PDF or DOCX file (executing from the repository root):
```bash
python3.12 src/auto_color_mapper.py -f data/Galle_P127.pdf
```

### 3. Command Line Arguments

- `-f`, `--file` (Required): Path to the target PDF or DOCX file.
- `-m`, `--model` (Optional): The Ollama model to use. Defaults to `llama3.1:8b`.
- `-H`, `--host` (Optional): The local Ollama server address. Defaults to `http://localhost:11434`.
- `-c`, `--categories` (Optional): Comma-separated list of target categories (e.g., `social,economic,political,historic,aesthetical,ecological`) to restrict the classification. Defaults to all 8 standard categories.
- `-o`, `--output` (Optional): Custom path for the final extracted JSON.

### 4. Generated Artifacts

Upon completion, the script generates two outputs:
1. **Sidecar Color Map** (`<filename>_color_map.json`): A JSON mapping configuration containing the inferred category and a sample sentence for each highlight color.
   ```json
   {
       "#8E67AC": {
           "category": "economic",
           "reasoning": "The highlights relate to economic activities, such as shopping streets...",
           "sentence": "“Behind them towards the former creek snake out shopping streets belonging to the Indians...”"
       }
   }
   ```
2. **Final Parsed Highlights** (`<filename>_extracted.json`): The finalized dataset where highlights are annotated using the dynamically inferred categories.

---

## Usage Instructions (Manual Config)

1. **Place PDFs in the Data Folder**
   Put the PDF/DOCX files you wish to process inside the `data/` directory.

2. **Execute the Script**
   Run the extractor with the Python 3.12 interpreter (from the repository root):
   ```bash
   python3.12 src/extract_highlights.py
   ```

3. **Check the Output**
   The script will generate structured JSON files in the same `data/` directory containing sentence-level highlights, coordinates, page numbers, mapped colors, tokens, and BIO tags.
   - Example: `data/Galle_P127.pdf` -> `data/Galle_P127_extracted.json`
