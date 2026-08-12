# Project color configurations

A project color configuration is an immutable, versioned interpretation of the colors
used by a research annotation protocol. It is selected once as the project default and
may then be applied to any document whose observed colors it fully defines.

This differs from automatic color proposals. Hex discovery records what is present in a
PDF; the project configuration records what those colors mean. Ollama is optional and is
not needed to create, select, or apply a configuration.

## Multiple colors for one category

Several shades may represent the same HEVA category:

```json
{
  "configuration_id": "student-palette",
  "version": 1,
  "name": "Student annotation palette",
  "mappings": [
    {
      "label": "historic",
      "hexes": ["#FFF200", "#FFFF00"]
    }
  ],
  "created_by": "PERSON-123ABC",
  "created_at": "2026-08-11T10:00:00Z"
}
```

One hex cannot represent two categories within the same version. All values are normalized
to uppercase `#RRGGBB` form before persistence.

## Immutability and provenance

Changing a mapping creates version 2; version 1 is never edited. The project selection
records the exact ID and version plus the curator and selection time. When applied to a
document, that same ID and version are copied into its metadata so previous extraction can
be reproduced.

Application fails rather than partially applying a configuration when an observed document
color is absent. The curator must create a new configuration version or choose another
existing version.

The registry is stored at `.heva/color-configurations.json` and validated by
`schemas/heva-color-configurations.schema.json`.

In the web application, confirming a document's color decisions creates the first
`project-palette` version, or selects an existing version with identical semantics. A new
immutable version is created only when the confirmed mapping is genuinely different. This
makes project semantics available to extraction without JSON or Python editing.

The **Project palettes** screen lists every version and identifies the exact selected one.
Curators can create a named configuration family, add controlled label rows with one or
several hex values, append later versions, filter the history, and deliberately select an
earlier version. Existing fields are read-only because corrections must create a new
version rather than rewrite the meaning used by earlier extraction.

## Python example

```python
from heva.workflow.color_configuration_registry import (
    create_color_configuration_version,
    select_color_configuration,
)

configuration = create_color_configuration_version(
    project_root,
    configuration_id="student-palette",
    name="Student palette",
    mappings=[{"label": "historic", "hexes": ["#FFF200", "#FFFF00"]}],
)
select_color_configuration(
    project_root,
    configuration.configuration_id,
    configuration.version,
)
```
