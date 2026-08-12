const statusBox = document.getElementById("people-status");
const list = document.getElementById("people-list");
const filter = document.getElementById("people-filter");
const form = document.getElementById("person-form");
let registry = {people: [], active_curator_id: null};
let selectedId = null;

function showStatus(kind, message) {
  statusBox.className = `notice ${kind}`;
  statusBox.textContent = message;
}

function selectedPerson() {
  return registry.people.find((person) => person.person_id === selectedId) || null;
}

function renderList() {
  const query = filter.value.trim().toLowerCase();
  const visible = registry.people.filter((person) =>
    [person.name, person.affiliation, person.email, ...person.roles]
      .filter(Boolean).join(" ").toLowerCase().includes(query),
  );
  if (!visible.length) {
    const empty = document.createElement("p");
    empty.className = "notice neutral";
    empty.textContent = query ? "No people match this filter." : "No people have been added yet.";
    list.replaceChildren(empty);
    return;
  }
  list.replaceChildren(...visible.map((person) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `annotator-list-item${person.person_id === selectedId ? " selected" : ""}`;
    const name = document.createElement("strong");
    name.textContent = `${person.name}${person.person_id === registry.active_curator_id ? " ●" : ""}`;
    const detail = document.createElement("small");
    detail.textContent = person.roles.map((role) => role.replace("_", " ")).join(" · ");
    button.append(name, detail);
    button.addEventListener("click", () => selectPerson(person.person_id));
    return button;
  }));
}

function selectPerson(personId) {
  selectedId = personId;
  const person = selectedPerson();
  form.reset();
  form.elements.name.value = person?.name || "";
  form.elements.affiliation.value = person?.affiliation || "";
  form.elements.email.value = person?.email || "";
  form.elements.orcid.value = person?.orcid || "";
  [...form.querySelectorAll("[name='roles']")].forEach((input) => {
    input.checked = person?.roles.includes(input.value) || false;
  });
  document.getElementById("person-editor-title").textContent = person ? `Edit ${person.name}` : "Add person";
  const isActive = person?.person_id === registry.active_curator_id;
  document.getElementById("curator-badge").hidden = !isActive;
  document.getElementById("activate-curator").hidden = !person?.roles.includes("curator") || isActive;
  document.getElementById("remove-person").hidden = !person;
  renderList();
}

function formPayload() {
  const roles = [...form.querySelectorAll("[name='roles']:checked")].map((input) => input.value);
  return {
    ...(selectedId ? {person_id: selectedId} : {}),
    name: form.elements.name.value.trim(),
    roles,
    affiliation: form.elements.affiliation.value.trim() || null,
    email: form.elements.email.value.trim() || null,
    orcid: form.elements.orcid.value.trim() || null,
  };
}

async function loadPeople(preferredId = selectedId) {
  const response = await fetch("/api/people");
  const result = await response.json();
  if (!response.ok) {
    showStatus("error", result.detail || "Project people could not be loaded.");
    return;
  }
  registry = result;
  const initial = registry.people.find((person) => person.person_id === preferredId)
    || registry.people.find((person) => person.person_id === registry.active_curator_id)
    || registry.people[0];
  selectPerson(initial?.person_id || null);
  showStatus(
    registry.people.length ? "success" : "warning",
    registry.people.length
      ? `${registry.people.length} project person${registry.people.length === 1 ? "" : "s"} loaded.`
      : "Add the first project person and assign at least one role.",
  );
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!form.reportValidity()) return;
  const payload = formPayload();
  if (!payload.roles.length) {
    showStatus("error", "Select at least one workflow role.");
    return;
  }
  const response = await fetch(selectedId ? `/api/people/${encodeURIComponent(selectedId)}` : "/api/people", {
    method: selectedId ? "PUT" : "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload),
  });
  const result = await response.json();
  if (!response.ok) {
    const detail = Array.isArray(result.detail)
      ? result.detail.map((issue) => issue.msg).join(" ")
      : result.detail;
    showStatus("error", detail || "The person was not saved.");
    return;
  }
  await loadPeople(result.person_id);
  showStatus("success", `${result.name} was saved with explicit workflow roles.`);
});

document.getElementById("activate-curator").addEventListener("click", async () => {
  const response = await fetch(`/api/people/${encodeURIComponent(selectedId)}/activate-curator`, {method: "POST"});
  const result = await response.json();
  if (!response.ok) {
    showStatus("error", result.detail || "The active curator was not changed.");
    return;
  }
  await loadPeople(selectedId);
  showStatus("success", `${selectedPerson().name} is now the active curator.`);
});

document.getElementById("remove-person").addEventListener("click", async () => {
  const person = selectedPerson();
  if (!person || !window.confirm(`Remove ${person.name} from current project configuration? Historical evidence remains unchanged.`)) return;
  const response = await fetch(`/api/people/${encodeURIComponent(person.person_id)}`, {method: "DELETE"});
  const result = await response.json();
  if (!response.ok) {
    showStatus("error", result.detail || "The person was not removed.");
    return;
  }
  selectedId = null;
  await loadPeople();
  showStatus("success", `${person.name} was removed from current configuration.`);
});

document.getElementById("new-person").addEventListener("click", () => selectPerson(null));
filter.addEventListener("input", renderList);
loadPeople();
