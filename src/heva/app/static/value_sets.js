const statusBox = document.getElementById("value-set-status");
const list = document.getElementById("value-set-list");
const filter = document.getElementById("value-set-filter");
const form = document.getElementById("value-set-form");
const values = document.getElementById("value-set-values");
let valueSets = [];
let current = null;

function showStatus(kind, message) {
  statusBox.className = `notice ${kind}`;
  statusBox.textContent = message;
}

function sameVersion(left, right) {
  return Boolean(left && right)
    && left.value_set_id === right.value_set_id
    && left.version === right.version;
}

/** Add one label/description row; existing versions are shown read-only. */
function valueRow(value = {label: "", description: null}, readOnly = false) {
  const row = document.createElement("div");
  row.className = "generated-fields";
  const label = document.createElement("label");
  label.textContent = "Value";
  const input = document.createElement("input");
  input.name = "value_label";
  input.value = value.label;
  input.placeholder = "mental";
  input.pattern = "[a-z0-9]+(?:-[a-z0-9]+)*";
  input.required = true;
  input.readOnly = readOnly;
  label.appendChild(input);
  const description = document.createElement("label");
  description.textContent = "Description (optional)";
  const text = document.createElement("input");
  text.name = "value_description";
  text.value = value.description || "";
  text.readOnly = readOnly;
  description.appendChild(text);
  row.append(label, description);
  values.appendChild(row);
}

function renderList() {
  const query = filter.value.trim().toLowerCase();
  const visible = valueSets.filter((valueSet) =>
    [valueSet.value_set_id, valueSet.name, valueSet.description,
      ...valueSet.values.map((value) => `${value.label} ${value.description || ""}`)]
      .filter(Boolean).join(" ").toLowerCase().includes(query),
  );
  if (!visible.length) {
    const empty = document.createElement("p");
    empty.className = "notice neutral";
    empty.textContent = "No value set versions match this filter.";
    list.replaceChildren(empty);
    return;
  }
  list.replaceChildren(...visible.map((valueSet) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `annotator-list-item${sameVersion(current, valueSet) ? " selected" : ""}`;
    const name = document.createElement("strong");
    name.textContent = `${valueSet.name} · v${valueSet.version}`;
    const detail = document.createElement("small");
    detail.textContent = valueSet.built_in
      ? `${valueSet.value_set_id} · built in`
      : `${valueSet.value_set_id} · ${valueSet.values.length} value${valueSet.values.length === 1 ? "" : "s"}`;
    button.append(name, detail);
    button.addEventListener("click", () => showValueSet(valueSet));
    return button;
  }));
}

function showValueSet(valueSet) {
  current = valueSet;
  form.reset();
  values.replaceChildren();
  const readOnly = Boolean(valueSet);
  form.elements.value_set_id.value = valueSet?.value_set_id || "";
  form.elements.name.value = valueSet?.name || "";
  form.elements.description.value = valueSet?.description || "";
  form.elements.value_set_id.readOnly = readOnly;
  form.elements.name.readOnly = readOnly;
  form.elements.description.readOnly = readOnly;
  (valueSet?.values || [{label: "", description: null}]).forEach((value) => valueRow(value, readOnly));
  document.getElementById("value-set-title").textContent = valueSet
    ? `${valueSet.name} · version ${valueSet.version}`
    : "Create value set version";
  document.getElementById("save-value-set").hidden = readOnly;
  document.getElementById("add-value").hidden = readOnly;
  document.getElementById("built-in-badge").hidden = !valueSet?.built_in;
  renderList();
}

async function loadValueSets(preferred = current) {
  const response = await fetch("/api/value-sets");
  const result = await response.json();
  if (!response.ok) {
    showStatus("error", result.detail || "Value sets could not be loaded.");
    return;
  }
  valueSets = result.value_sets;
  const matching = preferred && valueSets.find((item) => sameVersion(item, preferred));
  showValueSet(matching || valueSets.at(-1) || null);
  const custom = valueSets.filter((item) => !item.built_in).length;
  showStatus(
    custom ? "success" : "neutral",
    custom
      ? `${custom} project value set version${custom === 1 ? "" : "s"} loaded alongside the built-in HEVA heritage values.`
      : "Only the built-in HEVA heritage values exist. Create a value set to annotate other kinds of datasets.",
  );
}

document.getElementById("add-value").addEventListener("click", () => valueRow());
document.getElementById("new-value-set").addEventListener("click", () => showValueSet(null));
filter.addEventListener("input", renderList);

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!form.reportValidity()) return;
  const labels = [...form.querySelectorAll("[name='value_label']")];
  const descriptions = [...form.querySelectorAll("[name='value_description']")];
  const payload = {
    value_set_id: form.elements.value_set_id.value.trim(),
    name: form.elements.name.value.trim(),
    description: form.elements.description.value.trim() || null,
    values: labels.map((label, index) => ({
      label: label.value.trim(),
      description: descriptions[index].value.trim() || null,
    })),
  };
  const response = await fetch("/api/value-sets", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload),
  });
  const result = await response.json();
  if (!response.ok) {
    showStatus("error", typeof result.detail === "string" ? result.detail : "The value set version was not created.");
    return;
  }
  await loadValueSets(result);
  showStatus("success", `${result.name} version ${result.version} was created without changing earlier versions. Create a project palette version to map colors to it.`);
});

loadValueSets();
