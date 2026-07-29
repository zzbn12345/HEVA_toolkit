const documentId = document.body.dataset.documentId;
const app = document.getElementById("review-app");
const list = document.getElementById("sentence-list");
const statusBox = document.getElementById("review-status");
const editor = document.getElementById("sentence-editor");
const editorForm = document.getElementById("sentence-editor-form");
const editorError = document.getElementById("sentence-editor-error");
const entityRows = document.getElementById("edit-entities");
const hevaLabels = [
  "social", "economic", "political", "historic", "aesthetical",
  "scientific", "age", "ecological",
];
let reviewDocument = null;
let visibleSentences = [];
let editingRecord = null;
const selectedSentenceIds = new Set();

function textElement(tag, className, text) {
  const element = document.createElement(tag);
  element.className = className;
  element.textContent = text;
  return element;
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

function lineValues(value) {
  return value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean);
}

function entityRow(entity = {}) {
  const row = document.createElement("div");
  row.className = "entity-row";
  const fields = [
    ["Text", "text", "text"],
    ["Start", "start", "number"],
    ["End", "end", "number"],
  ];
  fields.forEach(([labelText, name, type]) => {
    const label = textElement("label", "", labelText);
    const input = document.createElement("input");
    input.type = type;
    input.dataset.entityField = name;
    input.required = true;
    if (type === "number") input.min = "0";
    input.value = entity[name] ?? "";
    label.appendChild(input);
    row.appendChild(label);
  });
  const labelWrapper = textElement("label", "", "HEVA label");
  const labelSelect = document.createElement("select");
  labelSelect.dataset.entityField = "label";
  labelSelect.required = true;
  hevaLabels.forEach((value) => {
    const option = new Option(value, value, false, value === entity.label);
    labelSelect.appendChild(option);
  });
  labelWrapper.appendChild(labelSelect);
  row.appendChild(labelWrapper);
  const colorWrapper = textElement("label", "", "Color");
  const color = document.createElement("input");
  color.type = "text";
  color.pattern = "#[0-9A-Fa-f]{6}";
  color.placeholder = "#RRGGBB";
  color.dataset.entityField = "color";
  color.value = entity.color ?? "";
  colorWrapper.appendChild(color);
  row.appendChild(colorWrapper);
  const remove = textElement("button", "button secondary", "Remove");
  remove.type = "button";
  remove.addEventListener("click", () => row.remove());
  row.appendChild(remove);
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
  document.getElementById("edit-sentence").value = record.sentence;
  document.getElementById("edit-tokens").value = record.tokens.join("\n");
  document.getElementById("edit-ner-tags").value = record.ner_tags.join("\n");
  entityRows.replaceChildren(...record.entities.map(entityRow));
  editor.showModal();
}

function correctedRecord() {
  const entities = [...entityRows.querySelectorAll(".entity-row")].map((row) => {
    const value = (name) => row.querySelector(`[data-entity-field="${name}"]`).value;
    const entity = {
      text: value("text"),
      start: Number(value("start")),
      end: Number(value("end")),
      label: value("label"),
    };
    const color = value("color").trim();
    if (color) entity.color = color.toUpperCase();
    return entity;
  });
  return {
    ...editingRecord,
    sentence_id: Number(document.getElementById("edit-sentence-id").value),
    page: Number(document.getElementById("edit-page").value),
    sentence: document.getElementById("edit-sentence").value,
    tokens: lineValues(document.getElementById("edit-tokens").value),
    values: [...new Set(entities.map((entity) => entity.label))],
    entities,
    ner_tags: lineValues(document.getElementById("edit-ner-tags").value),
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
  const selectedCount = visibleSentences.filter((item) =>
    selectedSentenceIds.has(item.record.sentence_id)
  ).length;
  document.getElementById("selected-count").textContent =
    `${selectedCount} selected`;
  document.querySelectorAll("[data-batch-status]").forEach((button) => {
    button.disabled = selectedCount === 0;
  });
  const selectVisible = document.getElementById("select-visible");
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
  card.appendChild(textElement("p", "sentence-text", record.sentence));
  const entities = document.createElement("div");
  entities.className = "entity-list";
  for (const entity of record.entities) {
    const wrapper = textElement("span", "entity", `${entity.text} · ${entity.label}`);
    if (entity.color) {
      const color = textElement("span", "entity-color", entity.color);
      color.style.background = entity.color;
      const rgb = entity.color.slice(1).match(/../g).map((value) => parseInt(value, 16));
      const luminance = 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2];
      color.style.color = luminance > 145 ? "#000000" : "#FFFFFF";
      wrapper.prepend(color);
    }
    entities.appendChild(wrapper);
  }
  card.appendChild(entities);
  if (item.flags.length) {
    const flags = document.createElement("div");
    flags.className = "flag-list";
    item.flags.forEach((flag) => flags.appendChild(textElement("span", "flag", `${flag.code}: ${flag.message}`)));
    card.appendChild(flags);
  }
  const actions = document.createElement("div");
  actions.className = "decision-actions";
  const editButton = textElement("button", "button secondary", "Edit sentence");
  editButton.type = "button";
  editButton.addEventListener("click", () => openEditor(record));
  actions.appendChild(editButton);
  [["Approve", "approved"], ["Needs correction", "needs_correction"], ["Exclude", "excluded"]].forEach(([label, status]) => {
    const button = textElement("button", `button${status === "approved" ? "" : " secondary"}`, label);
    button.type = "button";
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
  const completed = reviewDocument.sentences.filter((item) =>
    ["approved", "excluded"].includes(item.review.status)
  ).length;
  statusBox.className = "notice success";
  statusBox.textContent = `Showing ${visibleSentences.length} of ${reviewDocument.sentences.length} sentences from this document only. ${completed} have final decisions.`;
}

function navigationLink(documentIdValue, label) {
  const link = textElement("a", "button secondary", label);
  link.href = `/review/${encodeURIComponent(documentIdValue)}`;
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
document.getElementById("add-entity").addEventListener("click", () => {
  entityRows.appendChild(entityRow());
});
document.getElementById("close-sentence-editor").addEventListener("click", closeEditor);
document.getElementById("cancel-sentence-editor").addEventListener("click", closeEditor);
editorForm.addEventListener("submit", (event) => {
  event.preventDefault();
  saveCorrection();
});
loadDocument();
