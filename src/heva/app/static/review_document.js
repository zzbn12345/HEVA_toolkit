const documentId = document.body.dataset.documentId;
const app = document.getElementById("review-app");
const list = document.getElementById("sentence-list");
const statusBox = document.getElementById("review-status");
const editor = document.getElementById("sentence-editor");
const editorForm = document.getElementById("sentence-editor-form");
const editorError = document.getElementById("sentence-editor-error");
const entityRows = document.getElementById("edit-entities");
const gateLabels = {
  citation: "Citation",
  color_configuration: "Colors",
  extraction: "Extraction",
  sentence_review: "Sentences",
};
let reviewDocument = null;
let visibleSentences = [];
let editingRecord = null;
const selectedSentenceIds = new Set();

if (new URLSearchParams(window.location.search).get("embedded") === "1") {
  document.body.classList.add("embedded-review");
}

function textElement(tag, className, text) {
  const element = document.createElement(tag);
  element.className = className;
  element.textContent = text;
  return element;
}

function contrastColor(hex) {
  if (!/^#[0-9A-Fa-f]{6}$/.test(hex || "")) return "#FFFFFF";
  const rgb = hex.slice(1).match(/../g).map((value) => parseInt(value, 16));
  const luminance = 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2];
  return luminance > 145 ? "#000000" : "#FFFFFF";
}

function highlightedSentence(record) {
  const paragraph = document.createElement("p");
  paragraph.className = "sentence-text annotated-sentence";
  const boundaries = new Set([0, record.sentence.length]);
  record.entities.forEach((entity) => {
    boundaries.add(entity.start);
    boundaries.add(entity.end);
  });
  const positions = [...boundaries].sort((left, right) => left - right);
  for (let index = 0; index < positions.length - 1; index += 1) {
    const start = positions[index];
    const end = positions[index + 1];
    const text = record.sentence.slice(start, end);
    const active = record.entities.filter(
      (entity) => entity.start <= start && entity.end >= end,
    );
    if (!active.length) {
      paragraph.appendChild(document.createTextNode(text));
      continue;
    }
    const primary = active[0];
    const highlight = textElement("mark", "annotation-highlight", text);
    const descriptions = active.map((entity) =>
      `${entity.label}${entity.color ? ` ${entity.color}` : ""}`
    );
    highlight.title = descriptions.join("; ");
    highlight.setAttribute(
      "aria-label",
      `${text}, annotated as ${descriptions.join(" and ")}`,
    );
    highlight.tabIndex = 0;
    if (primary.color) {
      highlight.style.backgroundColor = primary.color;
      highlight.style.color = contrastColor(primary.color);
    }
    paragraph.appendChild(highlight);
  }
  return paragraph;
}

async function decide(sentenceIds, status, comment = null) {
  const response = await fetch(`/api/review/${encodeURIComponent(documentId)}/decisions`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sentence_ids: sentenceIds, status, comment }),
  });
  const result = await response.json();
  if (!response.ok) {
    statusBox.className = "notice error";
    statusBox.textContent = `${result.message} ${result.action}`;
    return;
  }
  reviewDocument = result;
  selectedSentenceIds.clear();
  render();
}

function renderReadiness() {
  const panel = document.getElementById("review-readiness");
  const gates = document.getElementById("review-gates");
  const blockers = document.getElementById("review-blockers");
  const submit = document.getElementById("submit-document-review");
  gates.replaceChildren(...Object.entries(reviewDocument.readiness_gates).map(
    ([key, passed]) => textElement(
      "span",
      `workspace-gate ${passed ? "passed" : "blocked"}`,
      `${passed ? "✓" : "○"} ${gateLabels[key]}`,
    ),
  ));
  blockers.replaceChildren(...reviewDocument.blocking_reasons.map(
    (reason) => textElement("li", "", reason),
  ));
  const submitted = ["in_review", "done"].includes(reviewDocument.status);
  panel.classList.toggle("submitted", submitted);
  submit.disabled = !reviewDocument.annotation_complete || submitted;
  submit.textContent = submitted
    ? "Submitted for curator review"
    : "Submit for curator review";
  document.getElementById("review-readiness-title").textContent = submitted
    ? "Annotation submitted"
    : reviewDocument.annotation_complete
      ? "Ready for curator review"
      : "Complete the annotation gates";
}

async function submitDocumentReview() {
  const submit = document.getElementById("submit-document-review");
  submit.disabled = true;
  submit.textContent = "Submitting…";
  try {
    const response = await fetch(
      `/api/review/${encodeURIComponent(documentId)}/submit`,
      {method: "POST"},
    );
    const result = await response.json();
    if (!response.ok) {
      statusBox.className = "notice error";
      statusBox.textContent = `${result.message} ${result.action}`;
      renderReadiness();
      return;
    }
    reviewDocument = result;
    render();
    statusBox.className = "notice success";
    statusBox.textContent = "This document is now read-only and awaiting curator review.";
  } catch (error) {
    statusBox.className = "notice error";
    statusBox.textContent = `The document could not be submitted: ${error.message}`;
    renderReadiness();
  }
}

function entityRow(entity = {}) {
  const row = document.createElement("div");
  row.className = "entity-row";
  row.dataset.originalStart = entity.start ?? "-1";
  row.dataset.label = entity.label ?? "";
  row.dataset.color = entity.color ?? "";
  const textWrapper = textElement("label", "", "Extracted text");
  const extractedText = document.createElement("textarea");
  extractedText.rows = 2;
  extractedText.dataset.entityField = "text";
  extractedText.required = true;
  extractedText.value = entity.text ?? "";
  textWrapper.appendChild(extractedText);
  row.appendChild(textWrapper);
  const labelWrapper = textElement("label", "", "HEVA label");
  const labelValue = textElement(
    "span",
    "extraction-evidence",
    entity.label || "No label",
  );
  labelWrapper.appendChild(labelValue);
  row.appendChild(labelWrapper);
  const colorWrapper = textElement("label", "", "Color");
  const colorValue = textElement(
    "span",
    "extraction-evidence extraction-color",
    entity.color || "No color",
  );
  if (entity.color) {
    colorValue.style.setProperty("--evidence-color", entity.color);
  }
  colorWrapper.appendChild(colorValue);
  row.appendChild(colorWrapper);
  return row;
}

function closeEditor() {
  editor.close();
  editingRecord = null;
}

function openEditor(record) {
  editingRecord = structuredClone(record);
  editorError.hidden = true;
  document.getElementById("edit-sentence-id").value = record.sentence_id;
  document.getElementById("edit-page").value = record.page;
  entityRows.replaceChildren(...record.entities.map(entityRow));
  editor.showModal();
}

function locateExtraction(sentence, text, preferredStart) {
  const matches = [];
  let position = sentence.indexOf(text);
  while (position !== -1) {
    matches.push(position);
    position = sentence.indexOf(text, position + 1);
  }
  if (!matches.length) {
    throw new Error(`“${text}” does not occur exactly in the sentence.`);
  }
  return matches.reduce((best, candidate) =>
    Math.abs(candidate - preferredStart) < Math.abs(best - preferredStart)
      ? candidate
      : best
  );
}

function tokenSpans(sentence, tokens) {
  let cursor = 0;
  return tokens.map((token) => {
    const start = sentence.indexOf(token, cursor);
    if (start === -1) {
      throw new Error(
        `The stored token “${token}” cannot be aligned with this sentence.`,
      );
    }
    cursor = start + token.length;
    return {start, end: cursor};
  });
}

function deriveBioTags(sentence, tokens, entities) {
  let previousEntity = null;
  return tokenSpans(sentence, tokens).map((token) => {
    const entityIndex = entities.findIndex(
      (entity) => entity.start < token.end && entity.end > token.start,
    );
    if (entityIndex === -1) {
      previousEntity = null;
      return "O";
    }
    const prefix = previousEntity === entityIndex ? "I" : "B";
    previousEntity = entityIndex;
    return `${prefix}-${entities[entityIndex].label}`;
  });
}

function correctedRecord() {
  const entities = [...entityRows.querySelectorAll(".entity-row")].map((row) => {
    const value = (name) => row.querySelector(`[data-entity-field="${name}"]`).value;
    const text = value("text").trim();
    const start = locateExtraction(
      editingRecord.sentence,
      text,
      Number(row.dataset.originalStart),
    );
    const entity = {
      text,
      start,
      end: start + text.length,
      label: row.dataset.label,
    };
    const color = row.dataset.color.trim();
    if (color) entity.color = color.toUpperCase();
    return entity;
  });
  return {
    ...editingRecord,
    sentence_id: Number(document.getElementById("edit-sentence-id").value),
    page: Number(document.getElementById("edit-page").value),
    values: [...new Set(entities.map((entity) => entity.label))],
    entities,
    ner_tags: deriveBioTags(editingRecord.sentence, editingRecord.tokens, entities),
  };
}

async function saveCorrection() {
  const saveButton = document.getElementById("save-sentence-editor");
  saveButton.disabled = true;
  saveButton.textContent = "Validating…";
  editorError.hidden = true;
  try {
    const record = correctedRecord();
    const response = await fetch(
      `/api/review/${encodeURIComponent(documentId)}/sentences/${record.sentence_id}`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ record }),
      },
    );
    const result = await response.json();
    if (!response.ok) {
      editorError.hidden = false;
      editorError.textContent = result.detail || `${result.message} ${result.action}`;
      return;
    }
    reviewDocument = result;
    closeEditor();
    render();
    statusBox.className = "notice success";
    statusBox.textContent = `Sentence ${record.sentence_id} was validated and saved. Review it again before approval.`;
  } catch (error) {
    editorError.hidden = false;
    editorError.textContent = `The correction could not be saved: ${error.message}`;
  } finally {
    saveButton.disabled = false;
    saveButton.textContent = "Validate and save correction";
  }
}

function updateSelectionControls() {
  const editable = !reviewDocument.draft_only && !["in_review", "done"].includes(reviewDocument.status);
  const selectedCount = visibleSentences.filter((item) =>
    selectedSentenceIds.has(item.record.sentence_id)
  ).length;
  document.getElementById("selected-count").textContent =
    `${selectedCount} selected`;
  document.querySelectorAll("[data-batch-status]").forEach((button) => {
    button.disabled = selectedCount === 0 || !editable;
  });
  const selectVisible = document.getElementById("select-visible");
  selectVisible.disabled = !editable;
  selectVisible.checked =
    visibleSentences.length > 0 && selectedCount === visibleSentences.length;
  selectVisible.indeterminate =
    selectedCount > 0 && selectedCount < visibleSentences.length;
}

function sentenceCard(item) {
  const record = item.record;
  const card = document.createElement("article");
  card.className = `sentence-card${item.flags.length ? " problematic" : ""}`;
  card.dataset.status = item.review.status;
  card.dataset.problematic = String(Boolean(item.flags.length));
  if (selectedSentenceIds.has(record.sentence_id)) card.classList.add("selected");
  const selection = document.createElement("label");
  selection.className = "sentence-selection";
  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.disabled = reviewDocument.draft_only || ["in_review", "done"].includes(reviewDocument.status);
  checkbox.checked = selectedSentenceIds.has(record.sentence_id);
  checkbox.setAttribute("aria-label", `Select sentence ${record.sentence_id}`);
  checkbox.addEventListener("change", () => {
    if (checkbox.checked) selectedSentenceIds.add(record.sentence_id);
    else selectedSentenceIds.delete(record.sentence_id);
    card.classList.toggle("selected", checkbox.checked);
    updateSelectionControls();
  });
  selection.append(checkbox, `Select sentence ${record.sentence_id}`);
  card.appendChild(selection);
  card.appendChild(textElement("div", "sentence-meta", `Sentence ${record.sentence_id} · Page ${record.page} · ${item.review.status}`));
  card.appendChild(highlightedSentence(record));
  if (item.flags.length) {
    const flags = document.createElement("div");
    flags.className = "flag-list";
    item.flags.forEach((flag) => flags.appendChild(textElement("span", "flag", `${flag.code}: ${flag.message}`)));
    card.appendChild(flags);
  }
  const actions = document.createElement("div");
  actions.className = "decision-actions";
  const editable = !reviewDocument.draft_only && !["in_review", "done"].includes(reviewDocument.status);
  const editButton = textElement("button", "button secondary", "Edit sentence");
  editButton.type = "button";
  editButton.disabled = !editable;
  editButton.addEventListener("click", () => openEditor(record));
  actions.appendChild(editButton);
  [["Approve", "approved"], ["Needs correction", "needs_correction"], ["Exclude", "excluded"]].forEach(([label, status]) => {
    const button = textElement("button", `button${status === "approved" ? "" : " secondary"}`, label);
    button.type = "button";
    button.disabled = !editable;
    button.addEventListener("click", () => decide([record.sentence_id], status));
    actions.appendChild(button);
  });
  card.appendChild(actions);
  return card;
}

function render() {
  const filter = document.getElementById("review-filter").value;
  const limit = Number(document.getElementById("page-size").value);
  visibleSentences = reviewDocument.sentences.filter((item) => {
    if (filter === "to_check") {
      return ["pending", "needs_correction"].includes(item.review.status);
    }
    if (filter === "problematic") return item.flags.length > 0 || item.review.status === "needs_correction";
    if (filter === "checked") {
      return ["approved", "excluded"].includes(item.review.status);
    }
    return true;
  }).slice(0, limit);
  const visibleIds = new Set(
    visibleSentences.map((item) => item.record.sentence_id),
  );
  [...selectedSentenceIds].forEach((sentenceId) => {
    if (!visibleIds.has(sentenceId)) selectedSentenceIds.delete(sentenceId);
  });
  list.replaceChildren(...visibleSentences.map(sentenceCard));
  updateSelectionControls();
  renderReadiness();
  const completed = reviewDocument.sentences.filter((item) =>
    ["approved", "excluded"].includes(item.review.status)
  ).length;
  statusBox.className = `notice ${reviewDocument.draft_only ? "warning" : "success"}`;
  statusBox.textContent = reviewDocument.draft_only
    ? `Showing ${visibleSentences.length} of ${reviewDocument.sentences.length} raw extracted sentences. Colors are visible, but review decisions remain locked until Color config resolves their HEVA labels.`
    : `Showing ${visibleSentences.length} of ${reviewDocument.sentences.length} sentences from this document only. ${completed} have final decisions.`;
}

function navigationLink(documentIdValue, label) {
  const link = textElement("a", "button secondary", label);
  link.href = document.body.classList.contains("embedded-review")
    ? `/create?document_id=${encodeURIComponent(documentIdValue)}&section=annotations`
    : `/review/${encodeURIComponent(documentIdValue)}`;
  return link;
}

async function loadDocument() {
  const response = await fetch(`/api/review/${encodeURIComponent(documentId)}`);
  const result = await response.json();
  if (!response.ok) {
    statusBox.className = "notice error";
    statusBox.textContent = `${result.message} ${result.action}`;
    return;
  }
  reviewDocument = result;
  document.getElementById("document-name").textContent = result.source_path;
  document.getElementById("review-citation-link").href =
    `/create?document_id=${encodeURIComponent(documentId)}&section=citation`;
  document.getElementById("review-colors-link").href =
    `/create?document_id=${encodeURIComponent(documentId)}&section=colors`;
  document.getElementById("review-rights-link").href =
    `/documents/${encodeURIComponent(documentId)}/rights`;
  document.getElementById("review-pdf-frame").src = `/api/review/${encodeURIComponent(documentId)}/source`;
  const navigation = document.getElementById("document-navigation");
  if (result.previous_document_id) navigation.appendChild(navigationLink(result.previous_document_id, "← Previous document"));
  else navigation.appendChild(document.createElement("span"));
  if (result.next_document_id) navigation.appendChild(navigationLink(result.next_document_id, "Next document →"));
  render();
}

document.getElementById("toggle-review-pdf").addEventListener("click", (event) => {
  const hidden = app.classList.toggle("pdf-hidden");
  event.currentTarget.textContent = hidden ? "Show PDF" : "Hide PDF";
  event.currentTarget.setAttribute("aria-expanded", String(!hidden));
});
document.getElementById("review-filter").addEventListener("change", render);
document.getElementById("page-size").addEventListener("change", render);
document.getElementById("select-visible").addEventListener("change", (event) => {
  visibleSentences.forEach((item) => {
    const sentenceId = item.record.sentence_id;
    if (event.currentTarget.checked) selectedSentenceIds.add(sentenceId);
    else selectedSentenceIds.delete(sentenceId);
  });
  render();
});
document.querySelectorAll("[data-batch-status]").forEach((button) => {
  button.addEventListener("click", () => {
    const visibleIds = visibleSentences
      .map((item) => item.record.sentence_id)
      .filter((sentenceId) => selectedSentenceIds.has(sentenceId));
    const comment = document.getElementById("batch-comment").value.trim() || null;
    decide(visibleIds, button.dataset.batchStatus, comment);
  });
});
document.getElementById("submit-document-review").addEventListener(
  "click",
  submitDocumentReview,
);
document.getElementById("close-sentence-editor").addEventListener("click", closeEditor);
document.getElementById("cancel-sentence-editor").addEventListener("click", closeEditor);
editorForm.addEventListener("submit", (event) => {
  event.preventDefault();
  saveCorrection();
});
loadDocument();
