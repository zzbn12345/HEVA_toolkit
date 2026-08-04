const status = document.getElementById("annotator-status");
const list = document.getElementById("annotator-list");
const filter = document.getElementById("annotator-filter");
const generatedFields = document.getElementById("generated-fields");
const dataEditor = document.getElementById("data-json");
let schema = null;
let uiSchema = null;
let registry = { annotators: [], active_annotator_id: null };
let selectedId = null;

function showStatus(kind, message) {
  status.className = `notice ${kind}`;
  status.textContent = message;
}

function editableData(record = {}) {
  return Object.fromEntries(
    Object.keys(schema.properties).map((key) => [key, record[key] ?? null]),
  );
}

function syncDataEditor() {
  dataEditor.textContent = JSON.stringify(editableData(readForm()), null, 2);
}

function concreteDefinition(definition) {
  if (definition.type) return definition;
  return (definition.anyOf || []).find((option) => option.type !== "null") || {};
}

function propertyType(definition) {
  if (definition.type) return definition.type;
  return concreteDefinition(definition).type || "string";
}

function showFieldValidity(input, error) {
  const message = input.validity.valid ? "" : input.validationMessage;
  input.setAttribute("aria-invalid", String(Boolean(message)));
  error.textContent = message;
}

function renderForm(data = {}) {
  const required = new Set(schema.required || []);
  const controls = uiSchema.elements || Object.keys(schema.properties).map(
    (key) => ({ type: "Control", scope: `#/properties/${key}` }),
  );
  generatedFields.replaceChildren(...controls.map((control) => {
    const key = control.scope.split("/").at(-1);
    const definition = schema.properties[key];
    const wrapper = document.createElement("div");
    wrapper.className = "generated-control";
    const label = document.createElement("label");
    label.htmlFor = `field-${key}`;
    label.textContent = definition.title || key;
    if (!required.has(key)) {
      const optional = document.createElement("small");
      optional.textContent = " (optional)";
      label.append(optional);
    }
    const input = document.createElement("input");
    input.id = `field-${key}`;
    input.name = key;
    input.type = definition.format === "email" ? "email" : propertyType(definition);
    if (input.type === "string") input.type = "text";
    input.required = required.has(key);
    const concrete = concreteDefinition(definition);
    if (concrete.pattern) input.pattern = concrete.pattern;
    if (concrete.minLength) input.minLength = concrete.minLength;
    if (concrete.maxLength) input.maxLength = concrete.maxLength;
    input.value = data[key] || "";
    const error = document.createElement("p");
    error.id = `error-${key}`;
    error.className = "field-error";
    input.setAttribute("aria-describedby", error.id);
    input.addEventListener("input", () => {
      showFieldValidity(input, error);
      syncDataEditor();
    });
    input.addEventListener("invalid", () => showFieldValidity(input, error));
    wrapper.append(label, input);
    if (definition.description) {
      const description = document.createElement("p");
      description.textContent = definition.description;
      wrapper.append(description);
    }
    wrapper.append(error);
    return wrapper;
  }));
  syncDataEditor();
}

function readForm() {
  return Object.fromEntries(
    [...generatedFields.querySelectorAll("input")].map((input) => [
      input.name,
      input.value.trim() || null,
    ]),
  );
}

function selectRecord(record) {
  selectedId = record?.annotator_id || null;
  document.getElementById("editor-title").textContent = record?.name || "Add annotator";
  const isActive = selectedId && selectedId === registry.active_annotator_id;
  document.getElementById("active-badge").hidden = !isActive;
  const activate = document.getElementById("activate-annotator");
  activate.hidden = !selectedId || isActive;
  document.getElementById("remove-annotator").hidden = !selectedId;
  renderForm(editableData(record));
  renderList();
}

function filteredAnnotators() {
  const term = filter.value.trim().toLowerCase();
  if (!term) return registry.annotators;
  return registry.annotators.filter((annotator) =>
    [annotator.name, annotator.affiliation, annotator.email, annotator.orcid]
      .filter(Boolean)
      .some((value) => value.toLowerCase().includes(term)),
  );
}

function renderList() {
  const items = filteredAnnotators();
  if (!items.length) {
    const empty = document.createElement("p");
    empty.className = "panel-help";
    empty.textContent = registry.annotators.length
      ? "No annotators match this filter."
      : "No annotators have been added yet.";
    list.replaceChildren(empty);
    return;
  }
  list.replaceChildren(...items.map((annotator) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `annotator-list-item${annotator.annotator_id === selectedId ? " selected" : ""}`;
    const name = document.createElement("strong");
    name.textContent = annotator.name;
    if (annotator.annotator_id === registry.active_annotator_id) {
      name.textContent += " ●";
      name.className = "active-dot";
    }
    const details = document.createElement("small");
    details.textContent = annotator.affiliation || annotator.email || annotator.annotator_id;
    button.append(name, details);
    button.addEventListener("click", () => selectRecord(annotator));
    return button;
  }));
}

async function loadWorkspace() {
  try {
    const [schemaResponse, recordsResponse] = await Promise.all([
      fetch("/api/annotators/schema"),
      fetch("/api/annotators"),
    ]);
    const schemaResult = await schemaResponse.json();
    const recordsResult = await recordsResponse.json();
    if (!schemaResponse.ok || !recordsResponse.ok) {
      throw new Error(recordsResult.detail || "The annotator data could not be loaded.");
    }
    schema = schemaResult.schema;
    uiSchema = schemaResult.ui_schema;
    registry = recordsResult;
    document.getElementById("schema-json").textContent = JSON.stringify(schemaResult, null, 2);
    const initial = registry.annotators.find(
      (item) => item.annotator_id === registry.active_annotator_id,
    ) || registry.annotators[0];
    selectRecord(initial);
    showStatus(
      registry.annotators.length ? "success" : "warning",
      registry.annotators.length
        ? `${registry.annotators.length} project annotator${registry.annotators.length === 1 ? "" : "s"} loaded.`
        : "No annotators exist yet. Add the first project annotator.",
    );
  } catch (error) {
    showStatus("error", `${error.message} Correct the annotator JSON or reload this page.`);
  }
}

document.getElementById("schema-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!event.currentTarget.reportValidity()) return;
  const response = await fetch(
    selectedId ? `/api/annotators/${encodeURIComponent(selectedId)}` : "/api/annotators",
    {
      method: selectedId ? "PUT" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(readForm()),
    },
  );
  const result = await response.json();
  if (!response.ok) {
    const detail = Array.isArray(result.detail)
      ? result.detail.map((issue) => `${issue.loc.at(-1)}: ${issue.msg}`).join(" ")
      : result.detail;
    showStatus("error", detail || "The annotator could not be saved.");
    return;
  }
  await loadWorkspace();
  selectRecord(registry.annotators.find((item) => item.annotator_id === result.annotator_id));
  showStatus("success", `${result.name} was saved.`);
});

document.getElementById("new-annotator").addEventListener("click", () => selectRecord(null));
filter.addEventListener("input", renderList);

document.getElementById("activate-annotator").addEventListener("click", async () => {
  if (!selectedId) return;
  const response = await fetch(`/api/annotators/${encodeURIComponent(selectedId)}/activate`, {
    method: "POST",
  });
  if (!response.ok) {
    showStatus("error", "The active annotator could not be changed.");
    return;
  }
  registry.active_annotator_id = selectedId;
  selectRecord(registry.annotators.find((item) => item.annotator_id === selectedId));
  showStatus("success", "This annotator will be reused for new documents.");
});

document.getElementById("remove-annotator").addEventListener("click", async () => {
  if (!selectedId) return;
  const selected = registry.annotators.find((item) => item.annotator_id === selectedId);
  if (!window.confirm(`Remove ${selected.name} from this project? Historical review records will be preserved.`)) {
    return;
  }
  const response = await fetch(`/api/annotators/${encodeURIComponent(selectedId)}`, {
    method: "DELETE",
  });
  const result = await response.json();
  if (!response.ok) {
    showStatus("error", result.detail || "The annotator could not be removed.");
    return;
  }
  registry = result;
  const initial = registry.annotators.find(
    (item) => item.annotator_id === registry.active_annotator_id,
  ) || registry.annotators[0];
  selectRecord(initial);
  showStatus("success", `${selected.name} was removed from project configuration. Historical decisions were not changed.`);
});

document.querySelectorAll(".editor-tab").forEach((tab) => tab.addEventListener("click", () => {
  document.querySelectorAll(".editor-tab").forEach((item) => {
    const active = item === tab;
    item.classList.toggle("active", active);
    item.setAttribute("aria-selected", String(active));
  });
  document.querySelectorAll(".editor-panel").forEach((panel) => {
    panel.classList.toggle("active", panel.id === tab.dataset.panel);
  });
}));

loadWorkspace();
