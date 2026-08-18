# What is a HEVA Data Package?

A HEVA Data Package is a small, self-describing dataset produced from one or more annotated
documents. It lets another researcher understand the dataset, inspect its annotations, and
reuse it without knowing how the application stores temporary working state.

The package contains:

```text
heva-data-package/
├── datapackage.json          # dataset identity and list of resources
├── heva-annotations.json     # metadata plus annotations grouped by document
├── heva-annotations.csv      # flat derivative for analysis
└── build-log.json            # reproducibility information
```

The source PDFs/DOCXs and the hidden `.heva/` application workspace are not part of the
Data Package.

## Why both JSON and CSV?

- **JSON is canonical.** It preserves document identity, citations, annotator information,
  sentence text, extracted spans, colors, HEVA labels, and BIO tags without flattening
  relationships.
- **CSV is a derivative.** It is convenient for inspection, statistics, spreadsheets, and
  machine-learning adapters. It can always be regenerated from validated JSON.
- **`datapackage.json` is the manifest.** It describes the dataset and points to the files a
  program or researcher can reuse.

## Document and sentence evidence

Each document has a stable `document_id`, citation metadata, and its own annotations. Each
sentence record identifies its page and contains:

- the complete sentence;
- the highlighted phrase and character offsets;
- the original hex color;
- the supervised HEVA label;
- tokens and BIO tags for NLP use.

Hex colors are evidence from the source document. They do not have universal semantic
meaning. The Data Package records the human-reviewed mapping from each observed color to a
HEVA label. Several hex colors may map to the same label—for example, two yellow shades may
both represent `social` in one annotation protocol.

The controlled label vocabulary is stored in `schemas/heritage-values.csv`. The current alpha
interface uses its eight top-level labels. Color-to-label decisions are stored with the project
and exported as document evidence; they are not defined by the vocabulary file.

The visual guide used by the app is stored in
`src/heva/app/static/heva-reference-palette.json`. It records the reference color, subcategories,
and historical source shown in the HEVA reference chart. It is guidance rather than a rule that
rejects nearby shades.

## Validation

Validation checks that required files and fields are present and that relationships are
coherent—for example, entity offsets point to the recorded text, labels belong to the HEVA
vocabulary, and BIO tags align with tokens. A passing report means the package follows the
current HEVA specification. It does not establish scholarly correctness or extractor recall.

## Explore the dummy package

Open `examples/dummy-data-package/` in the repository. It contains two fictional documents
and a few records so researchers can see the intended result before processing real data.

Next: [replicate the example with new documents](TUTORIAL.md).
