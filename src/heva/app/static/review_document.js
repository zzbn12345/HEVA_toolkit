const documentId = document.body.dataset.documentId;
const app = document.getElementById("review-app");
const list = document.getElementById("sentence-list");
const statusBox = document.getElementById("review-status");
const editor = document.getElementById("sentence-editor");
const editorForm = document.getElementById("sentence-editor-form");
const editorError = document.getElementById("sentence-editor-error");
const entityRows = document.getElementById("edit-entities");
const gateLabels = {
  curator: "Curator",
  original_annotator: "Original annotator",
  citation: "Citation",
  color_configuration: "Colors",
  extraction: "Extraction",
  sentence_review: "Sentences",
};
let reviewDocument = null;
let visibleSentences = [];
let currentSentencePage = 1;
let editingRecord = null;
const excludedEntityIndices = new Set();
const selectedSentenceIds = new Set();

function routeWorkflowLink(link) {
  if (document.body.classList.contains("embedded-review")) {
    link.target = "_top";
  }
  return link;
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
  const sentence = record.curated_sentence || record.sentence;
  const boundaries = new Set([0, sentence.length]);
  record.entities.forEach((entity) => {
    boundaries.add(entity.start);
    boundaries.add(entity.end);
  });
  const positions = [...boundaries].sort((left, right) => left - right);
  for (let index = 0; index < positions.length - 1; index += 1) {
    const start = positions[index];
    const end = positions[index + 1];
    const text = sentence.slice(start, end);
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

/**
 * Reveal the source PDF at the one-based page retained by extraction evidence.
 * The current schema does not retain annotation rectangles, so HEVA deliberately
 * promises page navigation rather than an inaccurate coordinate highlight.
 */
function navigatePdfEvidence(record) {
  const page = Number(record.page);
  if (!Number.isInteger(page) || page < 1) return;
  if (document.body.classList.contains("embedded-review")) {
    window.parent.postMessage(
      {type: "heva-pdf-evidence", documentId, page},
      window.location.origin,
    );
    return;
  }
  app.classList.remove("pdf-hidden");
  const toggle = document.getElementById("toggle-review-pdf");
  toggle.textContent = "Hide PDF";
  toggle.setAttribute("aria-expanded", "true");
  document.getElementById("review-pdf-frame").src =
    `/api/review/${encodeURIComponent(documentId)}/source#page=${page}`;
  document.getElementById("review-pdf").scrollIntoView({block: "nearest"});
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

async function acceptWarning(sentenceId, code) {
  const response = await fetch(
    `/api/review/${encodeURIComponent(documentId)}/sentences/${sentenceId}/warnings/${encodeURIComponent(code)}`,
    {
      method: "PUT",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({}),
    },
  );
  const result = await response.json();
  if (!response.ok) {
    statusBox.className = "notice error";
    statusBox.textContent = `${result.message} ${result.action}`;
    return;
  }
  reviewDocument = result;
  render();
  statusBox.className = "notice success";
  statusBox.textContent = `Warning ${code} was accepted and retained in the audit history.`;
}

async function removeAllWarnings() {
  const button = document.getElementById("remove-all-warnings");
  button.disabled = true;
  const response = await fetch(
    `/api/review/${encodeURIComponent(documentId)}/warnings`,
    {method: "PUT"},
  );
  const result = await response.json();
  if (!response.ok) {
    statusBox.className = "notice error";
    statusBox.textContent = `${result.message} ${result.action}`;
    button.disabled = false;
    return;
  }
  reviewDocument = result;
  render();
  statusBox.className = "notice success";
  statusBox.textContent = result.removed_warning_count
    ? `${result.removed_warning_count} warnings removed.`
    : "There were no active warnings to remove.";
}

function renderReadiness() {
  const panel = document.getElementById("review-readiness");
  const gates = document.getElementById("review-gates");
  const blockers = document.getElementById("review-blockers");
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
  panel.classList.remove("submitted");
  document.getElementById("review-readiness-title").textContent =
    reviewDocument.annotation_complete
      ? "Ready for validation"
      : "Complete the annotation gates";
}

/** Group validator findings by the researcher-facing document configuration area. */
function validationCategory(issue) {
  const evidence = `${issue.code} ${issue.path}`.toLowerCase();
  if (evidence.includes("annotator")) return "People and roles";
  if (evidence.includes("citation") || evidence.includes("source_title") || evidence.includes("source_creator") || evidence.includes("findability")) return "Citation";
  if (evidence.includes("color")) return "Color configuration";
  if (evidence.includes("right") || evidence.includes("license") || evidence.includes("authoriz") || evidence.includes("access")) return "Rights and access";
  if (evidence.includes("review")) return "Sentence review";
  if (evidence.includes("annotation") || evidence.includes("extraction")) return "Annotations";
  return "Document metadata";
}

/** Return the safest corrective view for one validation category. */
function validationFixLink(category) {
  if (category === "Citation") return `/create?document_id=${encodeURIComponent(documentId)}&section=citation`;
  if (category === "Color configuration") return `/create?document_id=${encodeURIComponent(documentId)}&section=colors`;
  if (category === "Rights and access") return `/documents/${encodeURIComponent(documentId)}/rights`;
  if (category === "People and roles") return "/people";
  if (["Annotations", "Sentence review"].includes(category)) return `/create?document_id=${encodeURIComponent(documentId)}&section=annotations`;
  return null;
}

/** Render a timestamped, actionable result without modifying project data. */
function renderDocumentValidation(payload) {
  const panel = document.getElementById("document-validation-result");
  const report = payload.document;
  panel.hidden = false;
  panel.className = `document-validation-result ${report.valid ? "valid" : "invalid"}`;
  const heading = textElement("h2", "", report.valid ? "Document is valid" : "Document needs attention");
  const checked = textElement(
    "p",
    "muted",
    `Checked ${new Date(payload.checked_at).toLocaleString()}`,
  );
  panel.replaceChildren(heading, checked);
  if (report.valid) {
    panel.appendChild(textElement("p", "", "This document passes the current HEVA structural and semantic checks."));
    if (!report.issues.length) return;
  }
  const grouped = new Map();
  report.issues.forEach((issue) => {
    const category = validationCategory(issue);
    if (!grouped.has(category)) grouped.set(category, []);
    grouped.get(category).push(issue);
  });
  const groups = document.createElement("div");
  groups.className = "validation-groups";
  [...grouped.entries()].forEach(([category, issues]) => {
    const section = document.createElement("section");
    section.className = "validation-group";
    section.appendChild(textElement("h3", "", category));
    const findings = document.createElement("ul");
    findings.className = "validation-findings";
    issues.forEach((issue) => {
      const item = document.createElement("li");
      const location = [
        `Document ${issue.document_id}`,
        issue.sentence_id == null ? null : `Sentence ${issue.sentence_id}`,
        issue.path,
      ].filter(Boolean).join(" · ");
      item.append(
        textElement("strong", `validation-severity ${issue.severity}`, `${issue.severity}: ${issue.code}`),
        textElement("small", "validation-location", location),
        textElement("span", "", issue.message),
        textElement("small", "", `Fix: ${issue.action}`),
      );
      if (issue.sentence_id != null) {
        const link = textElement("a", "validation-fix-link", `Go to sentence ${issue.sentence_id}`);
        link.href = `#sentence-${issue.sentence_id}`;
        link.addEventListener("click", () => {
          document.getElementById("review-filter").value = "all";
          const index = reviewDocument.sentences.findIndex(
            (entry) => entry.record.sentence_id === issue.sentence_id,
          );
          currentSentencePage = Math.floor(index / Number(document.getElementById("page-size").value)) + 1;
          render();
          window.requestAnimationFrame(() => {
            document.getElementById(`sentence-${issue.sentence_id}`)?.scrollIntoView({behavior: "smooth", block: "center"});
          });
        });
        item.appendChild(link);
      }
      findings.appendChild(item);
    });
    section.appendChild(findings);
    const href = validationFixLink(category);
    if (href) {
      const link = textElement("a", "validation-fix-link", `Open ${category.toLowerCase()}`);
      link.href = href;
      if (document.body.classList.contains("embedded-review")) link.target = "_top";
      section.appendChild(link);
    }
    groups.appendChild(section);
  });
  panel.appendChild(groups);
}

/** Run document validation with an explicit finite loading and failure state. */
async function validateDocument() {
  const button = document.getElementById("validate-document");
  const panel = document.getElementById("document-validation-result");
  button.disabled = true;
  button.textContent = "Validating…";
  panel.hidden = false;
  panel.className = "document-validation-result";
  panel.textContent = "Running structural and semantic checks…";
  try {
    const response = await fetch(
      `/api/review/${encodeURIComponent(documentId)}/validate`,
      {method: "POST"},
    );
    const result = await response.json();
    if (!response.ok) {
      panel.className = "document-validation-result error";
      panel.textContent = `${result.message} ${result.action}`;
      return;
    }
    renderDocumentValidation(result);
    if (window.parent !== window) {
      window.parent.postMessage(
        {type: "heva-review-updated", documentId},
        window.location.origin,
      );
    }
  } catch (error) {
    panel.className = "document-validation-result error";
    panel.textContent = `Document validation failed: ${error.message}`;
  } finally {
    button.disabled = false;
    button.textContent = "Validate document";
  }
}

function entityRow(entity = {}, originalIndex = -1) {
  const row = document.createElement("div");
  row.className = "entity-row";
  row.dataset.originalStart = entity.start ?? "-1";
  row.dataset.label = entity.label ?? "";
  row.dataset.color = entity.color ?? "";
  row.dataset.originalIndex = originalIndex;
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
  const excludeButton = textElement("button", "button danger", "Exclude annotation");
  excludeButton.type = "button";
  excludeButton.addEventListener("click", () => {
    excludedEntityIndices.add(Number(row.dataset.originalIndex));
    row.remove();
  });
  row.appendChild(excludeButton);
  return row;
}

function closeEditor() {
  editor.close();
  document.body.classList.remove("editor-open");
  if (document.body.classList.contains("embedded-review")) {
    window.parent.postMessage(
      {type: "heva-annotation-editor-closed", documentId},
      window.location.origin,
    );
  }
  editingRecord = null;
  excludedEntityIndices.clear();
}

function openEditor(record) {
  editingRecord = structuredClone(record);
  excludedEntityIndices.clear();
  editorError.hidden = true;
  document.getElementById("edit-sentence-id").value = record.sentence_id;
  document.getElementById("edit-page").value = record.page;
  document.getElementById("edit-source-sentence").textContent = record.sentence;
  document.getElementById("edit-curated-sentence").value =
    record.curated_sentence || record.sentence;
  entityRows.replaceChildren(
    ...record.entities.map((entity, index) => entityRow(entity, index)),
  );
  if (reviewDocument.source_path.toLowerCase().endsWith(".pdf")) {
    navigatePdfEvidence(record);
  }
  if (document.body.classList.contains("embedded-review")) {
    window.parent.postMessage(
      {type: "heva-annotation-editor-opened", documentId, page: record.page},
      window.location.origin,
    );
  }
  document.body.classList.add("editor-open");
  editor.show();
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

function tokenizeSentence(sentence) {
  return sentence.match(/[\p{L}\p{N}]+(?:['’][\p{L}\p{N}]+)*|[^\s\p{L}\p{N}]/gu) || [];
}

function correctedRecord() {
  const sourceSentence = editingRecord.sentence;
  const editedSentence = document.getElementById("edit-curated-sentence").value.trim();
  if (!editedSentence) {
    throw new Error("The curated sentence cannot be empty.");
  }
  const effectiveSentence = editedSentence === sourceSentence ? sourceSentence : editedSentence;
  const tokens = effectiveSentence === sourceSentence
    ? editingRecord.tokens
    : tokenizeSentence(effectiveSentence);
  const entities = [...entityRows.querySelectorAll(".entity-row")].map((row) => {
    const value = (name) => row.querySelector(`[data-entity-field="${name}"]`).value;
    const text = value("text").trim();
    const start = locateExtraction(
      effectiveSentence,
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
    curated_sentence: effectiveSentence === sourceSentence ? null : effectiveSentence,
    sentence_id: Number(document.getElementById("edit-sentence-id").value),
    page: Number(document.getElementById("edit-page").value),
    values: [...new Set(entities.map((entity) => entity.label))],
    entities,
    tokens,
    ner_tags: deriveBioTags(effectiveSentence, tokens, entities),
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
        body: JSON.stringify({
          record,
          excluded_entity_indices: [...excludedEntityIndices].sort((left, right) => left - right),
        }),
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
  const editable = reviewDocument.editability?.editable ?? !reviewDocument.draft_only;
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
  const removeWarnings = document.getElementById("remove-all-warnings");
  const activeWarnings = reviewDocument.sentences.some((item) =>
    item.flags.some((flag) => flag.severity === "warning")
  );
  removeWarnings.disabled = !editable || !activeWarnings;
}

function sentenceCard(item) {
  const record = item.record;
  const card = document.createElement("article");
  card.className = `sentence-card${item.flags.length ? " problematic" : ""}`;
  card.dataset.status = item.review.status;
  card.id = `sentence-${record.sentence_id}`;
  card.dataset.problematic = String(Boolean(item.flags.length));
  if (selectedSentenceIds.has(record.sentence_id)) card.classList.add("selected");
  const selection = document.createElement("label");
  selection.className = "sentence-selection";
  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  const editability = reviewDocument.editability || {editable: !reviewDocument.draft_only};
  checkbox.disabled = !editability.editable;
  if (!editability.editable) checkbox.title = editability.message || "Sentence review is locked.";
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
    item.flags.forEach((flag) => {
      const row = document.createElement("div");
      row.className = "flag-row";
      row.appendChild(textElement("span", "flag", `${flag.code}: ${flag.message}`));
      if (flag.severity === "warning" && editability.editable) {
        const accept = textElement("button", "button secondary compact", "Remove warning");
        accept.type = "button";
        accept.addEventListener("click", () => acceptWarning(record.sentence_id, flag.code));
        row.appendChild(accept);
      }
      flags.appendChild(row);
    });
    card.appendChild(flags);
  }
  const actions = document.createElement("div");
  actions.className = "decision-actions";
  if (reviewDocument.source_path.toLowerCase().endsWith(".pdf")) {
    const evidenceButton = textElement(
      "button",
      "button secondary",
      `View page ${record.page} in PDF`,
    );
    evidenceButton.type = "button";
    evidenceButton.title = "Exact annotation coordinates are not retained yet; HEVA will open the persisted source page.";
    evidenceButton.addEventListener("click", () => navigatePdfEvidence(record));
    actions.appendChild(evidenceButton);
  }
  const editable = editability.editable;
  const editButton = textElement("button", "button secondary", "Edit annotation");
  editButton.type = "button";
  editButton.disabled = !editable;
  if (!editable) editButton.title = editability.message || "Sentence editing is locked.";
  editButton.addEventListener("click", () => openEditor(record));
  actions.appendChild(editButton);
  [["Approve", "approved"], ["Needs correction", "needs_correction"], ["Exclude", "excluded"]].forEach(([label, status]) => {
    const button = textElement("button", `button${status === "approved" ? "" : " secondary"}`, label);
    button.type = "button";
    button.disabled = !editable;
    if (!editable) button.title = editability.message || "Sentence review is locked.";
    button.addEventListener("click", () => decide([record.sentence_id], status));
    actions.appendChild(button);
  });
  card.appendChild(actions);
  return card;
}

function render() {
  const editability = reviewDocument.editability || {editable: !reviewDocument.draft_only};
  const lock = document.getElementById("review-edit-lock");
  lock.hidden = editability.editable;
  if (!editability.editable) {
    document.getElementById("review-edit-lock-message").textContent = editability.message;
    document.getElementById("review-edit-lock-action").textContent = editability.action;
    const link = document.getElementById("review-edit-lock-link");
    link.href = editability.href;
    routeWorkflowLink(link);
  }
  const filter = document.getElementById("review-filter").value;
  const limit = Number(document.getElementById("page-size").value);
  const filteredSentences = reviewDocument.sentences.filter((item) => {
    if (filter === "to_check") {
      return ["pending", "needs_correction"].includes(item.review.status);
    }
    if (filter === "problematic") return item.flags.length > 0 || item.review.status === "needs_correction";
    if (filter === "checked") {
      return ["approved", "excluded"].includes(item.review.status);
    }
    return true;
  });
  const pageCount = Math.max(1, Math.ceil(filteredSentences.length / limit));
  currentSentencePage = Math.min(Math.max(currentSentencePage, 1), pageCount);
  const pageStart = (currentSentencePage - 1) * limit;
  visibleSentences = filteredSentences.slice(pageStart, pageStart + limit);
  document.getElementById("sentence-page-status").textContent =
    `Page ${currentSentencePage} of ${pageCount}`;
  document.getElementById("previous-sentence-page").disabled = currentSentencePage === 1;
  document.getElementById("next-sentence-page").disabled =
    currentSentencePage === pageCount || filteredSentences.length === 0;
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
    ? `Showing ${visibleSentences.length} of ${filteredSentences.length} matching raw extracted sentences. Colors are visible, but review decisions remain locked until Color config resolves their HEVA labels.`
    : `Showing ${visibleSentences.length} of ${filteredSentences.length} matching sentences from this document. ${completed} of ${reviewDocument.sentences.length} have final decisions.`;
  if (window.parent !== window) {
    window.parent.postMessage(
      {type: "heva-review-updated", documentId},
      window.location.origin,
    );
  }
}

function navigationLink(documentIdValue, label) {
  const link = textElement("a", "button secondary", label);
  link.href = document.body.classList.contains("embedded-review")
    ? `/create?document_id=${encodeURIComponent(documentIdValue)}&section=annotations`
    : `/review/${encodeURIComponent(documentIdValue)}`;
  return routeWorkflowLink(link);
}

function reviewWait(milliseconds) {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

async function loadReviewExtractionScope() {
  const response = await fetch(
    `/api/documents/${encodeURIComponent(documentId)}/extraction`,
  );
  const status = document.getElementById("review-extraction-status");
  if (!response.ok) {
    status.className = "notice error";
    status.textContent = "The current extraction scope could not be loaded.";
    return;
  }
  const extraction = await response.json();
  const pages = extraction.extraction_scope?.selected_pages || [];
  document.getElementById("review-page-start").value = pages.length ? pages[0] : "";
  document.getElementById("review-page-end").value = pages.length
    ? pages[pages.length - 1]
    : "";
  status.className = "notice neutral";
  status.textContent = pages.length
    ? `Current extraction scope: PDF pages ${pages[0]}–${pages[pages.length - 1]}.`
    : "Current extraction scope: complete source document.";
  const candidateResponse = await fetch(
    `/api/documents/${encodeURIComponent(documentId)}/ocr-candidate`,
  );
  const ocrReplacement = document.getElementById("review-run-ocr-extraction");
  const normalReplacement = document.getElementById("review-run-extraction");
  ocrReplacement.hidden = !candidateResponse.ok;
  normalReplacement.hidden = candidateResponse.ok;
  if (candidateResponse.ok) {
    status.textContent += " These annotations came through OCR assistance; replacement will re-run OCR.";
  }
}

async function waitForReviewExtraction() {
  const progress = document.getElementById("review-extraction-progress");
  const cancel = document.getElementById("review-cancel-extraction");
  const status = document.getElementById("review-extraction-status");
  const deadline = Date.now() + 10 * 60 * 1000;
  while (Date.now() < deadline) {
    const response = await fetch(
      `/api/documents/${encodeURIComponent(documentId)}/extraction/progress`,
    );
    const job = await response.json();
    if (!response.ok) throw new Error(job.detail || "Extraction progress is unavailable.");
    cancel.hidden = !["queued", "extracting"].includes(job.stage);
    if (job.stage === "extracting" && job.total_pages) {
      progress.max = job.total_pages;
      progress.value = job.completed_pages;
    } else {
      progress.max = job.total_steps;
      progress.value = job.completed_steps;
    }
    status.textContent = job.message;
    if (["completed", "draft_saved", "failed", "cancelled"].includes(job.state)) {
      return job;
    }
    await reviewWait(750);
  }
  throw new Error("Extraction is still running after ten minutes.");
}

async function runReviewExtraction() {
  const start = document.getElementById("review-page-start").value.trim();
  const end = document.getElementById("review-page-end").value.trim();
  const status = document.getElementById("review-extraction-status");
  if ((start && !end) || (!start && end)) {
    status.className = "notice error";
    status.textContent = "Provide both the first and last PDF page, or leave both blank.";
    return;
  }
  if (!window.confirm(
    "Re-extract annotations? Current annotations, OCR candidate data, and sentence-review decisions will be reset. HEVA will keep a local backup of the replaced data.",
  )) return;
  const scope = start && end
    ? `&page_start=${encodeURIComponent(start)}&page_end=${encodeURIComponent(end)}`
    : "";
  const run = document.getElementById("review-run-extraction");
  const progress = document.getElementById("review-extraction-progress");
  run.disabled = true;
  progress.hidden = false;
  status.className = "notice neutral";
  status.textContent = "Extraction is starting…";
  try {
    const response = await fetch(
      `/api/documents/${encodeURIComponent(documentId)}/extract?force=true${scope}`,
      {method: "POST"},
    );
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || result.message || "Extraction failed.");
    const job = await waitForReviewExtraction();
    status.className = job.state === "completed"
      ? "notice success"
      : job.state === "failed" ? "notice error" : "notice warning";
    status.textContent = job.error?.action
      ? `${job.message} ${job.error.action}`
      : job.message;
    if (job.state === "failed" && job.error?.code === "pdf_text_unreadable") {
      window.location.assign(
        `/create?document_id=${encodeURIComponent(documentId)}&section=annotations&extraction_failure=pdf_text_unreadable`,
      );
      return;
    }
    if (["completed", "draft_saved"].includes(job.state)) {
      await loadReviewExtractionScope();
      await loadDocument();
    }
  } catch (error) {
    status.className = "notice error";
    status.textContent = error.message;
  } finally {
    run.disabled = false;
    progress.hidden = true;
    document.getElementById("review-cancel-extraction").hidden = true;
  }
}

async function runReviewOcrExtraction() {
  const start = document.getElementById("review-page-start").value.trim();
  const end = document.getElementById("review-page-end").value.trim();
  const status = document.getElementById("review-extraction-status");
  if ((start && !end) || (!start && end)) {
    status.className = "notice error";
    status.textContent = "Provide both the first and last PDF page, or leave both blank.";
    return;
  }
  if (!window.confirm(
    "Re-run OCR-assisted extraction? Current annotations, the prior OCR candidate, and sentence-review decisions will be reset. HEVA will keep a local backup of the replaced data.",
  )) return;
  const scope = start && end
    ? `&page_start=${encodeURIComponent(start)}&page_end=${encodeURIComponent(end)}`
    : "";
  const run = document.getElementById("review-run-ocr-extraction");
  run.disabled = true;
  run.textContent = "Running OCR…";
  status.className = "notice neutral";
  status.textContent = "Resetting the current review data and creating a new OCR candidate…";
  try {
    const response = await fetch(
      `/api/documents/${encodeURIComponent(documentId)}/ocr-candidate?replace=true${scope}`,
      {method: "POST"},
    );
    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.detail || `${result.message || "OCR replacement failed."} ${result.action || ""}`);
    }
    list.replaceChildren();
    status.className = "notice success";
    status.textContent = `Created ${result.record_count} replacement OCR candidates. Opening candidate review…`;
    window.location.assign(
      `/create?document_id=${encodeURIComponent(documentId)}&section=annotations`,
    );
  } catch (error) {
    status.className = "notice error";
    status.textContent = error.message;
  } finally {
    run.disabled = false;
    run.textContent = "Re-run OCR-assisted extraction";
  }
}

async function cancelReviewExtraction() {
  const response = await fetch(
    `/api/documents/${encodeURIComponent(documentId)}/extraction/cancel`,
    {method: "POST"},
  );
  const result = await response.json();
  const status = document.getElementById("review-extraction-status");
  status.textContent = result.message || result.detail || "Cancellation could not be requested.";
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
  const citationLink = document.getElementById("review-citation-link");
  citationLink.href = `/create?document_id=${encodeURIComponent(documentId)}&section=citation`;
  routeWorkflowLink(citationLink);
  const colorsLink = document.getElementById("review-colors-link");
  colorsLink.href = `/create?document_id=${encodeURIComponent(documentId)}&section=colors`;
  routeWorkflowLink(colorsLink);
  const rightsLink = document.getElementById("review-rights-link");
  rightsLink.href = `/documents/${encodeURIComponent(documentId)}/rights`;
  routeWorkflowLink(rightsLink);
  document.getElementById("review-pdf-frame").src = `/api/review/${encodeURIComponent(documentId)}/source`;
  const navigation = document.getElementById("document-navigation");
  navigation.replaceChildren();
  if (result.previous_document_id) navigation.appendChild(navigationLink(result.previous_document_id, "← Previous document"));
  else navigation.appendChild(document.createElement("span"));
  if (result.next_document_id) navigation.appendChild(navigationLink(result.next_document_id, "Next document →"));
  const isDocx = result.source_path.toLowerCase().endsWith(".docx");
  document.getElementById("review-page-start").disabled = isDocx;
  document.getElementById("review-page-end").disabled = isDocx;
  render();
  await loadReviewExtractionScope();
}

document.getElementById("toggle-review-pdf").addEventListener("click", (event) => {
  const hidden = app.classList.toggle("pdf-hidden");
  event.currentTarget.textContent = hidden ? "Show PDF" : "Hide PDF";
  event.currentTarget.setAttribute("aria-expanded", String(!hidden));
});
document.getElementById("review-filter").addEventListener("change", () => {
  currentSentencePage = 1;
  render();
});
document.getElementById("page-size").addEventListener("change", () => {
  currentSentencePage = 1;
  render();
});
document.getElementById("previous-sentence-page").addEventListener("click", () => {
  currentSentencePage -= 1;
  render();
  list.scrollIntoView({block: "start"});
});
document.getElementById("next-sentence-page").addEventListener("click", () => {
  currentSentencePage += 1;
  render();
  list.scrollIntoView({block: "start"});
});
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
document.getElementById("validate-document").addEventListener("click", validateDocument);
document.getElementById("remove-all-warnings").addEventListener("click", removeAllWarnings);
document.getElementById("review-run-extraction").addEventListener("click", runReviewExtraction);
document.getElementById("review-run-ocr-extraction").addEventListener("click", runReviewOcrExtraction);
document.getElementById("review-cancel-extraction").addEventListener("click", cancelReviewExtraction);
document.getElementById("close-sentence-editor").addEventListener("click", closeEditor);
document.getElementById("cancel-sentence-editor").addEventListener("click", closeEditor);
editorForm.addEventListener("submit", (event) => {
  event.preventDefault();
  saveCorrection();
});
loadDocument();
