# Guided document and sentence review workflow

This document defines the researcher-facing workflow for preparing and reviewing HEVA
annotation projects. Automatic operations may prepare several documents, but human review
always takes place within one clearly identified document.

## 1. Global annotator profile

The annotator profile belongs to the project, not to an individual document or submission.
The annotator enters their name and available affiliation, contact, or identifier details
once. The application persists and reuses this profile when multiple document packages are
created or reviewed.

The annotator is not necessarily the author of a source document. Source authorship is
stored and reviewed separately within each document record.

Use **Annotator profile** from the home page to save the annotator's name and optional
affiliation, email, and ORCID. The profile is stored in `data/annotator.json`. Preparing a
document displays the active profile and links back to this editor; it does not duplicate
the identity fields inside document metadata.

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

- **Incomplete** means at least one citation, color configuration, extraction, or sentence
  review requirement still needs attention.
- **Complete** means citation details and the color configuration are confirmed, a
  persisted sentence inventory exists, and every sentence has an approved or excluded
  human decision.

This completion result describes annotator preparation. It does not mean that a curator
has accepted the document; curator acceptance is a later workflow decision.

Every row provides an **Edit this annotation** action. If the document is already
registered, editing reuses its source and persisted package state. **Add document** is a
separate action that asks the user to choose a new PDF or DOCX.

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

Color meaning is local to a document or an explicitly validated group of documents. A
historical or automatic convention may propose a label, but it cannot approve the mapping.

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

## 7. Batch checking and quality flags

Users may check sentences in batches, but only sentences that are currently visible and
explicitly selected may be changed. A batch action produces one persisted decision and
audit event per sentence.

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

## Acceptance criteria

- The project list shows friendly state, sentence-review completion, and Edit action for
  every document.
- Editing a registered PDF displays it immediately without another file selection.
- Document settings persist and keep source authors separate from annotators.
- The global annotator profile is entered once and reused across document records.
- Each record shows Complete or Incomplete based on confirmed citation, confirmed color
  configuration, persisted extraction, and finalized sentence decisions.
- Automatically proposed citation details require explicit human review.
- Color mappings remain document-local and require an explicit human decision.
- Every extracted sentence has a precise persisted review state.
- Batch review affects only visible, selected sentences and creates individual audit events.
- Flagged sentences remain visible and require human resolution.
- A document cannot enter In review with pending or needs-correction sentences.
- The PDF and review list remain independently scrollable.
