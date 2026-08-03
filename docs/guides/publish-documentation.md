# Publish the private documentation Wiki

HEVA uses the Markdown files in `docs/` for the private repository Wiki and the
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

Before committing, run the same strict documentation and Wiki builds used by automation:

```bash
mkdocs build --strict
python -m heva.wiki docs wiki-build
```

The generated `site/` and `wiki-build/` directories are temporary and are not committed.

## Download standalone HTML

The **Build standalone HEVA documentation** workflow is independent from both the Wiki
and the FastAPI application. Every documentation pull request and change to `main` creates
a strict MkDocs build, packages the complete HTML site as
`heva-documentation-html.tar.gz`, and records its SHA-256 checksum.

Download the `heva-documentation-html-<commit>` artifact from the workflow run. Extract
the archive and open `index.html`, or serve the extracted directory with any static web
server. Artifacts are retained for 30 days and contain documentation assets only.

## Initialize the private Wiki once

A repository maintainer must:

1. Enable **Wikis** under the repository's **Settings → General → Features**.
2. Open the **Wiki** tab and create its first page. GitHub creates the separate
   `.wiki.git` repository only after this initial page exists.
3. Create a token that can clone and push the private Wiki repository.
4. Save it as the Actions repository secret `WIKI_TOKEN` under
   **Settings → Secrets and variables → Actions**.

The token belongs only in GitHub's encrypted secret store. Do not put it in a local
environment file, workflow source, command example, or project package.

## What the workflow publishes

Pull requests generate the complete Wiki and attach a preview artifact without
publishing. A documentation change merged into `main`
synchronizes the generated pages to the private Wiki. The workflow replaces generated
Wiki Markdown so `docs/` remains the authoritative source.

Only generated Markdown is pushed. Project data, PDFs, annotations, local registries,
and secrets are not included. Access to a private repository Wiki follows access to its
repository.
