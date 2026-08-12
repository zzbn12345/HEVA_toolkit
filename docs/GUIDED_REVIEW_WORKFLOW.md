# Guided document and sentence review workflow

This document defines the researcher-facing workflow for preparing and reviewing HEVA
annotation projects. Automatic operations may prepare several documents, but human review
always takes place within one clearly identified document.

## 0. Open or create a project

The application starts without assuming that its installation folder is an annotation
project. Like opening a working file in a desktop application, the user first selects one
HEVA project:

- **Open existing project** accepts a folder containing
  `.heva/project.json` and restores only that registry's records.
- **Create from source folder** accepts a folder containing PDF or DOCX source files,
  initializes `.heva/project.json`, and creates one document-package workspace per
  discovered source.

The selected source folder becomes the project root. HEVA scans its source documents but
does not rename, move, or upload them. The dashboard, annotator profiles, validation,
document preparation, and review routes remain scoped to the active project. Closing the
project returns to the neutral chooser; invalid or empty folders display a corrective
error and do not become active.

## 1. Global annotator profile

The annotator profile belongs to the project, not to an individual document or submission.
The annotator enters their name and available affiliation, contact, or identifier details
once. The application persists and reuses this profile when multiple document packages are
created or reviewed.

The annotator is not necessarily the author of a source document. Source authorship is
stored and reviewed separately within each document record.

Use **Annotator profile** from the home page to load, filter, add, or edit project
annotators. Each record has a stable ID plus a name and optional affiliation, email, and
ORCID. The collection and active selection are stored in `.heva/annotators.json`. A former
`data/annotator.json` profile is migrated automatically when first loaded.

The editor offers Form, Schema, and Generated JSON views. Users edit only safe form fields;
the application generates the JSON and displays it read-only for transparency. Field
constraints come from the JSON Schema and the backend validates the same schema again
before saving. Preparing a document displays the selected active annotator and links back
to this editor; it does not duplicate identity fields inside document metadata.

### Shared safe record editor

The same interaction pattern applies to annotators, documents, and sentences: a filterable
record list opens a schema-generated form. Users create and update records through fields,
while JSON Schema defines constraints and the backend validates them again. Schema and
generated JSON may be inspected read-only; raw JSON editing is not required or supported.

Deletion follows the meaning of each record. An annotator may be removed from current
project configuration without altering decisions already attributed to that person.
Documents with processing history are archived. Reviewed sentences are excluded or
superseded rather than erased, preserving FAIR provenance and the review audit trail.

## 2. Document list, completion, and workflow state

The project opens as a row-based list of registered documents. Each document has one
workflow state:

| Interface label | Registry value | Meaning |
|---|---|---|
| To do | `backlog` | The document is registered but preparation has not started. |
| In progress | `in_progress` | Extraction, mapping, metadata, or sentence review is underway. |
| In review | `in_review` | Annotator work is complete and the document awaits curator review. |
| Finished | `done` | The curator has accepted the document for approved output. |

The interface uses the friendly labels. The registry values remain stable machine-readable
terms.

Every row also shows an annotation-readiness result:

- **Incomplete** means at least one annotation-curation requirement—color configuration,
  extraction, or sentence review—still needs attention.
- **Complete** means the color configuration is confirmed, a persisted sentence inventory
  exists, and every sentence has an approved or excluded human decision.

This completion result describes annotator preparation. It does not mean that a curator
has accepted the document; curator acceptance is a later workflow decision.

The dashboard displays Citation, Colors, Extraction, and Sentences separately. Citation is
a release requirement and may remain open during annotation curation; the other three
determine whether annotations can be submitted. Users may filter the list to all,
incomplete, or complete documents. A 100% sentence-review bar does not make a document
complete when another annotation-curation gate still requires attention.

Every row provides an **Edit this annotation** action. If the document is already
registered, editing reuses its source and persisted package state. **Add document** is a
separate action that asks the user to choose a new PDF or DOCX.

The document review toolbar links directly to **Citation**, **Color configuration**, and
**Rights and access**. Rights are recorded per document because permission to inspect a
source is not the same as permission to distribute its extracted text or annotations.

## 3. Sentence-review progress

Workflow state and completion are related but different:

- workflow state says where the document is in the overall process;
- completion says how much sentence-level annotator review has been finalized.

The completion percentage is:

```text
(approved sentences + excluded sentences) / all extracted sentences × 100
```

`pending` and `needs_correction` sentences remain incomplete. A document with no extracted
sentences displays 0% and explains that extraction is still required.

## 4. Document settings

Settings are persisted with the project or the document package, not only in the browser.
They include:

- reusable annotator identity for the active project session;
- source creator or author, which is separate from the annotator;
- source citation and reference;
- per-document rights and authorization information;
- the document-local color map and its human approval evidence;
- extraction method and provenance.

The source author and annotator must never be treated as the same field implicitly. One
person may have written the source while another person performs and reviews its
annotations.

When usable source metadata is available, the application may propose authorship and
citation values automatically. Proposed values remain unconfirmed until the annotator
reviews them. Missing or unconfirmed required citation details keep the document
**Incomplete**.

The citation step loads existing package values and proposes only blank title, author, or
citation fields from embedded PDF/DOCX properties when available, falling back to a
readable filename title. **Save citation draft** persists work without passing the gate.
**Confirm citation details** requires title, at least one source creator, a human-readable
citation, and either a DOI/public URL or an explanation of why the source is not findable.
Confirmation records the active annotator and time. Any later draft edit resets the
confirmation so it must be reviewed again.

Color meaning is local to a document or an explicitly validated group of documents. A
historical or automatic convention may propose a label, but it cannot approve the mapping.
The color-review step therefore loads the observed palette from that document's package;
it does not display a generic placeholder color. Each swatch shows its hex value and an
automatic suggestion, when one exists, as evidence. The annotator must select a controlled
HEVA label or explicitly ignore the color with a reason. Only a confirmed configuration
enables extraction.

When an observed color has no suggestion, **Request automatic proposals** extracts raw
highlight evidence and sends only those unresolved color groups to the configured local
Ollama model. The action shows progress and provides corrective errors when extraction,
Ollama, or its response fails. Returned labels must belong to the controlled HEVA
specification and remain `pending_review`; the operation cannot replace a confirmed
configuration or count as human approval.

After confirming one document, the annotator may inspect registered batch candidates.
Every candidate remains visible with its compatibility reason. Only an unconfirmed
document with the exact same observed hex palette can be selected. Reuse requires a
separate acknowledgement and writes confirmation evidence plus the source document ID
into every selected package. A mismatch never receives a partial or approximate mapping.

While extraction runs, the workspace displays progress and prevents a second request.
Completion reports the number of persisted sentence records and whether an existing
checkpoint was reused. Failures and a two-minute browser timeout produce a visible
corrective message instead of leaving the action apparently unfinished.

Reopening a document restores its persisted extraction count and warnings. A checkpoint
is current only when its source checksum, selected mapping checksum, and positive record
count still match. Legacy provenance, changed sources, changed mappings, unreadable files,
and count mismatches are shown as stale or invalid while preserving the old files for
inspection. The annotator must choose **Rebuild extraction** deliberately. Extracting zero
records is an error with corrective guidance, never a successful empty package.

## 5. Opening a document

Selecting **Edit this annotation** opens a document workspace. It may be a full page or a
focused window, provided it preserves the same domain behavior.

The workspace displays:

1. persisted annotator and source-author fields;
2. document metadata and rights settings;
3. the detected color palette and proposed mappings;
4. explicit mapping confirmation;
5. sentence review after extraction.

For a registered PDF, the source opens immediately in the right-hand viewer. The user is
not asked to choose the file again. The PDF pane and annotation pane scroll independently,
and the PDF can be hidden or shown.

The review toolbar provides direct access to the selected document's **Citation** and
**Color configuration**, plus the reusable project **Annotator profile**. These controls
open the existing persisted forms for that exact document rather than creating duplicate
configuration state.

## 6. Sentence states

Every extracted sentence begins requiring a check. The interface may summarize this as
**To be checked** or **Checked**, while retaining the more precise persisted states:

| Interface grouping | Persisted state | Meaning |
|---|---|---|
| To be checked | `pending` | No explicit human decision has been made. |
| To be checked | `needs_correction` | A person identified a problem or an edit still requires confirmation. |
| Checked | `approved` | A person explicitly accepted the sentence. |
| Checked | `excluded` | A person explicitly decided the sentence must not enter approved output. |

Each sentence card shows sentence text, page, controlled labels, raw colors and hex codes,
quality flags, decision state, and available actions. Decisions and edits record the actor,
time, and change history.

The correction form displays page and one row per extraction. Extracted text is the only
editable field; page, controlled label, and color remain visible as read-only evidence.
It displays every row when a sentence contains several annotations. Technical offsets and
BIO tags remain hidden and are derived and validated before persistence.

## 7. Batch checking and quality flags

Users may check sentences in batches, but only sentences that are currently visible and
explicitly selected may be changed. A batch action produces one persisted decision and
audit event per sentence.

The workspace provides **Select this visible batch** for the current 20/50-record view,
shows the exact selected count, and disables batch decisions when nothing is selected.
Changing filters or page size prunes hidden sentences from the selection. An optional
comment is copied into each selected sentence's individual audit event.

The interface supports batches of 20 or 50 and filters for:

- sentences still requiring a decision;
- sentences with quality flags;
- sentences marked as needing correction;
- all sentences in the current document.

Quality flags draw attention to likely extraction or annotation problems. They never
change a label, exclude a sentence, or make a human decision automatically.

The PDF remains visible on the right while reviewing sentences so the annotator can compare
the extracted sentence, color evidence, and page context and can spot omissions or
incorrect boundaries.

## 8. Finishing annotator review

The document workspace shows the same Citation, Colors, Extraction, and Sentences gates as
the project dashboard. The readiness display refreshes after every sentence decision or
correction. **Submit for curator review** requires Colors, Extraction, and Sentences;
Citation may be completed before or after curator acceptance but must pass before release.

Submitting timestamps completion in the package's annotation-process metadata and changes
the registry state to `in_review`. The sentence workspace then becomes read-only and
clearly displays **Submitted for curator review**. This protects the exact evidence sent
to the curator; a later correction workflow must explicitly return the document to
`in_progress` before changing records or decisions.

## Acceptance criteria

- The project list shows friendly state, sentence-review completion, and Edit action for
  every document.
- Editing a registered PDF displays it immediately without another file selection.
- Document settings persist and keep source authors separate from annotators.
- The global annotator profile is entered once and reused across document records.
- Each record shows Complete or Incomplete based on confirmed color configuration,
  persisted extraction, and finalized sentence decisions; citation readiness remains a
  separate visible release gate.
- Automatically proposed citation details require explicit human review.
- Color mappings remain document-local and require an explicit human decision.
- Every extracted sentence has a precise persisted review state.
- Batch review affects only visible, selected sentences and creates individual audit events.
- Flagged sentences remain visible and require human resolution.
- A document cannot enter In review with pending or needs-correction sentences.
- A document cannot be submitted until colors, extraction, and sentence review are
  complete; submitted annotation evidence becomes read-only while citation may still be
  completed for release.
- The PDF and review list remain independently scrollable.
