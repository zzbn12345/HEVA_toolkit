# Software design

HEVA is separated into layers so researchers can use validation and extraction without
installing or running the web interface.

```text
src/heva/
├── extraction/   PDF/DOCX reading, colors, text, and NLP adapters
├── workflow/     project records, validation, and Data Package generation
├── doctor.py     installation and environment check
└── app/           optional FastAPI web interface
```

## Extraction

The extraction layer reads source documents and returns observations: text, locations, and
colors. It does not decide that a color has a universal HEVA meaning. A person reviews the
mapping used by the project.

## Workflow and validation

The workflow layer owns durable project records and the rules used to validate them. It also
builds the distributable Data Package. This is the core of the toolkit.

## Command-line access

Scripts and automated workflows call the workflow modules directly without the browser. The
validation module's command-line entry point is the main supported example.

## App

The FastAPI app guides a user through the workflow and shows source documents beside the
records being reviewed. It is an interface over the extraction and workflow layers, not a
separate data implementation.

This separation keeps the Data Package specification and validation reusable if the user
interface changes.
