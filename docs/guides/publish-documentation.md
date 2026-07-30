# Publish the documentation

HEVA uses the Markdown files in `docs/` for both the toolkit website and the
guidance shown inside the web application. A documentation correction therefore
has one source and appears in both places.

## Preview a change locally

Install the documentation dependencies:

```bash
python -m pip install -e ".[docs]"
```

Start the local documentation website:

```bash
mkdocs serve
```

Before committing, run the same strict build used by automation:

```bash
mkdocs build --strict
```

The generated `site/` directory is temporary and is not committed.

## Enable GitHub Pages once

A repository maintainer must open **Settings → Pages** and select
**GitHub Actions** as the publishing source. This setting is separate from the
workflow file and requires repository administration permission.

## What the workflow publishes

Pull requests build the documentation and catch broken navigation without
publishing. A documentation change merged into `main` builds and deploys the
site through GitHub Pages.

Only the generated documentation site is uploaded. Project data, PDFs,
annotations, and local registries are not included.
