const documentId = document.body.dataset.documentId;
const form = document.getElementById("rights-form");
const statusBox = document.getElementById("rights-status");

/** Show one safe, researcher-facing rights persistence result. */
function showStatus(kind, message) {
  statusBox.className = `notice ${kind}`;
  statusBox.textContent = message;
}

/** Render backend validation details without exposing or accepting raw JSON. */
function errorMessage(result) {
  if (typeof result.detail === "string") return result.detail;
  if (Array.isArray(result.detail)) {
    return result.detail.map((issue) =>
      `${issue.loc?.at(-1) || "field"}: ${issue.msg}`
    ).join("; ");
  }
  return "Document rights could not be saved.";
}

function booleanValue(value) {
  if (value === "true") return true;
  if (value === "false") return false;
  return null;
}

/** Load the current document rights into constrained form controls. */
async function loadRights() {
  const response = await fetch(`/api/documents/${encodeURIComponent(documentId)}/rights`);
  const result = await response.json();
  if (!response.ok) {
    showStatus("error", errorMessage(result));
    return;
  }
  Object.entries(result).forEach(([name, value]) => {
    if (!form.elements[name] || value === null) return;
    form.elements[name].value = typeof value === "boolean" ? String(value) : value;
  });
  showStatus("success", "Current document rights are loaded.");
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!form.reportValidity()) return;
  const payload = {
    access_level: form.elements.access_level.value,
    authorization_status: form.elements.authorization_status.value,
    authorization_date: form.elements.authorization_date.value,
    authorized_by: form.elements.authorized_by.value.trim(),
    evidence_reference: form.elements.evidence_reference.value.trim(),
    source_distribution_allowed: booleanValue(form.elements.source_distribution_allowed.value),
    extracted_text_distribution_allowed: booleanValue(form.elements.extracted_text_distribution_allowed.value),
    annotation_distribution_allowed: booleanValue(form.elements.annotation_distribution_allowed.value),
    license: form.elements.license.value.trim(),
    embargo_until: form.elements.embargo_until.value || null,
  };
  const response = await fetch(`/api/documents/${encodeURIComponent(documentId)}/rights`, {
    method: "PUT",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload),
  });
  const result = await response.json();
  if (!response.ok) {
    showStatus("error", errorMessage(result));
    return;
  }
  showStatus("success", "Document authorization and distribution decisions were saved.");
});

const reviewUrl = `/review/${encodeURIComponent(documentId)}`;
document.getElementById("return-to-review").href = reviewUrl;
document.getElementById("continue-review").href = reviewUrl;
loadRights();
