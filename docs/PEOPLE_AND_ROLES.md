# People and workflow roles

HEVA records people independently from the roles they exercise. One person may have more
than one role:

- **annotator** — originally applied annotations to a source PDF;
- **curator** — extracts, maps, verifies, and corrects annotations using HEVA; and
- **data owner** — is accountable for a document's inclusion in a Data Package.

Review is an action performed by an authorized person, usually the data owner. It is not a
fourth permanent identity type.

## Registry

Project people are stored in `.heva/people.json` and validated by
`schemas/heva-people.schema.json`:

```json
{
  "schema_version": "1.0",
  "active_curator_id": "PERSON-123ABC",
  "people": [
    {
      "person_id": "PERSON-123ABC",
      "name": "Alex Researcher",
      "roles": ["curator", "data_owner"],
      "affiliation": "Example Heritage Institute",
      "email": null,
      "orcid": null
    }
  ]
}
```

The active curator must reference a person who has the `curator` role. Original PDF
annotators and data owners are never implicitly authorized to operate the curation session.
Removing a person from current configuration does not rewrite names or identifiers already
recorded in historical audit evidence.

## Compatibility migration

Earlier HEVA versions called the person operating the review workflow an "annotator" and
stored profiles in `.heva/annotators.json`. The first people-registry load imports those
operators as curators into `.heva/people.json`. The old file is retained as migration
evidence until the application interface has completed its transition.

The migration does not infer who originally annotated a PDF. Those identities must be
imported or entered explicitly with the `annotator` role.

## Web application

Open **People and roles** from the project home page. The validated form supports creating,
editing, filtering, and removing people; assigning one or several controlled roles; and
selecting a person with the curator role as the active curator. Original annotators and
data owners cannot be activated implicitly as curators.

Citation confirmation, color decisions, raw extraction, and review submission prefer the
active curator from `.heva/people.json`. Former projects may continue using their legacy
active operator during migration, but new project configuration should use this explicit
people interface.

## Python use

```python
from heva.workflow.people_registry import PersonRecord, activate_curator, add_person

person = add_person(
    project_root,
    PersonRecord(name="Alex Researcher", roles=["curator", "data_owner"]),
)
activate_curator(project_root, person.person_id)
```

## Authoritative CSV import

Projects that already maintain people in a spreadsheet can use the strict CSV adapter.
Copy `tests/fixtures/people.csv` as a starting point. Columns must be exactly:

```text
person_id,name,roles,affiliation,email,orcid,active_curator
```

Separate several controlled roles with semicolons. `person_id` remains the stable identity;
`active_curator` accepts true/false, yes/no, or 1/0 and may be true for at most one person,
who must have the curator role. Email and ORCID use the same validation as the app.

```bash
python -m heva.workflow.people_import /path/to/project people.csv
```

The CSV is treated as the authoritative current configuration and atomically replaces
`.heva/people.json` only after every row passes. Any invalid row leaves the former registry
unchanged. Replacement does not rewrite person names or IDs already embedded in historical
review, curation, or approval evidence.
