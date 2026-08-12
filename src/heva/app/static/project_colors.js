const HEVA_LABELS = ["social", "economic", "political", "historic", "aesthetical", "scientific", "age", "ecological"];
const statusBox = document.getElementById("palette-status");
const list = document.getElementById("palette-list");
const filter = document.getElementById("palette-filter");
const form = document.getElementById("palette-form");
const mappings = document.getElementById("palette-mappings");
let registry = {selected: null, configurations: []};
let current = null;

function showStatus(kind, message) {
  statusBox.className = `notice ${kind}`;
  statusBox.textContent = message;
}

function isSelected(configuration) {
  return registry.selected?.configuration_id === configuration.configuration_id
    && registry.selected?.version === configuration.version;
}

function mappingRow(mapping = {label: "historic", hexes: []}, readOnly = false) {
  const row = document.createElement("div");
  row.className = "generated-fields";
  const label = document.createElement("label");
  label.textContent = "HEVA label";
  const select = document.createElement("select");
  select.name = "mapping_label";
  select.disabled = readOnly;
  HEVA_LABELS.forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    option.selected = value === mapping.label;
    select.appendChild(option);
  });
  label.appendChild(select);
  const colors = document.createElement("label");
  colors.textContent = "Hex colors";
  const input = document.createElement("input");
  input.name = "mapping_hexes";
  input.value = mapping.hexes.join(", ");
  input.placeholder = "#FFFF00, #FFF200";
  input.required = true;
  input.readOnly = readOnly;
  colors.appendChild(input);
  row.append(label, colors);
  mappings.appendChild(row);
}

function renderList() {
  const query = filter.value.trim().toLowerCase();
  const visible = registry.configurations.filter((configuration) =>
    [configuration.configuration_id, configuration.name, configuration.description,
      ...configuration.mappings.map((mapping) => `${mapping.label} ${mapping.hexes.join(" ")}`)]
      .filter(Boolean).join(" ").toLowerCase().includes(query),
  );
  if (!visible.length) {
    const empty = document.createElement("p");
    empty.className = "notice neutral";
    empty.textContent = query ? "No palette versions match this filter." : "No project palette exists yet.";
    list.replaceChildren(empty);
    return;
  }
  list.replaceChildren(...visible.map((configuration) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `annotator-list-item${current === configuration ? " selected" : ""}`;
    const name = document.createElement("strong");
    name.textContent = `${configuration.name} · v${configuration.version}${isSelected(configuration) ? " ●" : ""}`;
    const detail = document.createElement("small");
    detail.textContent = configuration.configuration_id;
    button.append(name, detail);
    button.addEventListener("click", () => showConfiguration(configuration));
    return button;
  }));
}

function showConfiguration(configuration) {
  current = configuration;
  form.reset();
  mappings.replaceChildren();
  const readOnly = Boolean(configuration);
  form.elements.configuration_id.value = configuration?.configuration_id || "";
  form.elements.name.value = configuration?.name || "";
  form.elements.description.value = configuration?.description || "";
  form.elements.configuration_id.readOnly = readOnly;
  form.elements.name.readOnly = readOnly;
  form.elements.description.readOnly = readOnly;
  (configuration?.mappings || [{label: "historic", hexes: []}]).forEach((mapping) => mappingRow(mapping, readOnly));
  document.getElementById("palette-title").textContent = configuration
    ? `${configuration.name} · version ${configuration.version}`
    : "Create palette version";
  document.getElementById("save-palette").hidden = readOnly;
  document.getElementById("add-palette-mapping").hidden = readOnly;
  document.getElementById("select-palette").hidden = !configuration || isSelected(configuration);
  document.getElementById("selected-palette-badge").hidden = !configuration || !isSelected(configuration);
  renderList();
}

async function loadPalettes(preferred = current) {
  const response = await fetch("/api/project-colors");
  const result = await response.json();
  if (!response.ok) {
    showStatus("error", result.detail || "Project palettes could not be loaded.");
    return;
  }
  registry = result;
  const selected = registry.configurations.find(isSelected);
  const matching = preferred && registry.configurations.find((item) =>
    item.configuration_id === preferred.configuration_id && item.version === preferred.version,
  );
  showConfiguration(matching || selected || registry.configurations.at(-1) || null);
  showStatus(
    registry.configurations.length ? "success" : "warning",
    registry.configurations.length
      ? `${registry.configurations.length} immutable palette version${registry.configurations.length === 1 ? "" : "s"} loaded.`
      : "Create the first project palette after selecting an active curator.",
  );
}

document.getElementById("add-palette-mapping").addEventListener("click", () => mappingRow());
document.getElementById("new-palette").addEventListener("click", () => showConfiguration(null));
filter.addEventListener("input", renderList);

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!form.reportValidity()) return;
  const labels = [...form.querySelectorAll("[name='mapping_label']")];
  const hexFields = [...form.querySelectorAll("[name='mapping_hexes']")];
  const payload = {
    configuration_id: form.elements.configuration_id.value.trim(),
    name: form.elements.name.value.trim(),
    description: form.elements.description.value.trim() || null,
    mappings: labels.map((label, index) => ({
      label: label.value,
      hexes: hexFields[index].value.split(",").map((value) => value.trim()).filter(Boolean),
    })),
  };
  const response = await fetch("/api/project-colors", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload),
  });
  const result = await response.json();
  if (!response.ok) {
    showStatus("error", result.detail || "The palette version was not created.");
    return;
  }
  await loadPalettes(result);
  showStatus("success", `${result.name} version ${result.version} was created without changing earlier versions.`);
});

document.getElementById("select-palette").addEventListener("click", async () => {
  const response = await fetch("/api/project-colors/select", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({configuration_id: current.configuration_id, version: current.version}),
  });
  const result = await response.json();
  if (!response.ok) {
    showStatus("error", result.detail || "The project palette was not selected.");
    return;
  }
  await loadPalettes(current);
  showStatus("success", `${result.name} version ${result.version} is now selected for the project.`);
});

loadPalettes();
