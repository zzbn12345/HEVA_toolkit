const form = document.getElementById("dataset-form");
const statusBox = document.getElementById("dataset-status");

/** Show one plain-language persistence or validation result. */
function showStatus(kind, message) {
  statusBox.className = `notice ${kind}`;
  statusBox.textContent = message;
}

/** Convert the safe one-value-per-line fields into JSON arrays. */
function lines(value) {
  return value.split("\n").map((item) => item.trim()).filter(Boolean);
}

/** Convert FastAPI validation details into readable field-specific feedback. */
function errorMessage(result) {
  if (typeof result.detail === "string") return result.detail;
  if (Array.isArray(result.detail)) {
    return result.detail.map((issue) => {
      const field = issue.loc?.at(-1) || "field";
      return `${field}: ${issue.msg}`;
    }).join("; ");
  }
  return "The dataset details could not be saved.";
}

/** Load existing validated metadata and populate the form without exposing raw JSON. */
async function loadMetadata() {
  const response = await fetch("/api/dataset-metadata");
  const result = await response.json();
  if (!response.ok) {
    showStatus("error", errorMessage(result));
    return;
  }
  if (!result.configured) {
    showStatus("warning", "Dataset details are required before generating a Data Package.");
    return;
  }
  Object.entries(result.metadata).forEach(([name, value]) => {
    if (!form.elements[name]) return;
    form.elements[name].value = Array.isArray(value) ? value.join("\n") : value;
  });
  showStatus("success", "Validated dataset details are loaded from this project.");
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!form.reportValidity()) return;
  const payload = {
    name: form.elements.name.value.trim(),
    title: form.elements.title.value.trim(),
    description: form.elements.description.value.trim(),
    creators: lines(form.elements.creators.value),
    contributors: lines(form.elements.contributors.value),
    license: form.elements.license.value.trim(),
    rights: form.elements.rights.value.trim(),
    known_limitations: lines(form.elements.known_limitations.value),
  };
  const response = await fetch("/api/dataset-metadata", {
    method: "PUT",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload),
  });
  const result = await response.json();
  if (!response.ok) {
    showStatus("error", errorMessage(result));
    return;
  }
  showStatus("success", "Dataset details were validated and saved in dataset-metadata.json.");
});

loadMetadata();
