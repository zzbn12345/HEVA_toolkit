const app = document.getElementById("create-app");
const content = document.getElementById("create-content");
const steps = [...document.querySelectorAll(".create-step")];
const stepButtons = [...document.querySelectorAll(".step-button")];
const pdfInput = document.getElementById("pdf-files");
let previewUrls = [];

function showStep(number) {
  steps.forEach((step) => step.classList.toggle("active", step.dataset.step === String(number)));
  stepButtons.forEach((button) => button.classList.toggle("active", button.dataset.stepTarget === String(number)));
  content.scrollTop = 0;
}

function currentStepIsValid(button) {
  const step = button.closest(".create-step");
  return [...step.querySelectorAll("[required]")].every((input) => input.reportValidity());
}

stepButtons.forEach((button) => button.addEventListener("click", () => showStep(button.dataset.stepTarget)));
document.querySelectorAll("[data-next]").forEach((button) => button.addEventListener("click", () => {
  if (currentStepIsValid(button)) showStep(button.dataset.next);
}));
document.querySelectorAll("[data-back]").forEach((button) => button.addEventListener("click", () => showStep(button.dataset.back)));

document.getElementById("toggle-pdf").addEventListener("click", (event) => {
  const hidden = app.classList.toggle("pdf-hidden");
  event.currentTarget.textContent = hidden ? "Show PDF" : "Hide PDF";
  event.currentTarget.setAttribute("aria-expanded", String(!hidden));
});

async function restoreAnnotator() {
  const status = document.getElementById("annotator-status");
  try {
    const response = await fetch("/api/annotator");
    const result = await response.json();
    if (!response.ok) {
      status.className = "notice error";
      status.textContent = `${result.message} ${result.action}`;
      return;
    }
    if (result.configured) {
      status.className = "notice success";
      status.textContent = `Active project annotator: ${result.annotator.name}`;
    } else {
      status.className = "notice warning";
      status.textContent = `${result.message} You can register a document now, but the profile is required before submission.`;
    }
  } catch (error) {
    status.className = "notice error";
    status.textContent = "The annotator profile could not be loaded.";
  }
}

function openPreview(url, name) {
  const frame = document.getElementById("pdf-preview");
  frame.src = url;
  frame.style.display = "block";
  document.getElementById("preview-empty").style.display = "none";
  document.getElementById("preview-name").textContent = name;
}

function citationDraft() {
  return {
    title: document.getElementById("source-title").value.trim() || null,
    creators: document.getElementById("source-creators").value
      .split("\n")
      .map((value) => value.trim())
      .filter(Boolean),
    citation: document.getElementById("source-citation").value.trim() || null,
    reference: document.getElementById("source-reference").value.trim() || null,
    not_findable_reason:
      document.getElementById("source-not-findable").value.trim() || null,
  };
}

function displayCitation(result) {
  const data = result.data;
  document.getElementById("source-title").value = data.title || "";
  document.getElementById("source-creators").value = (data.creators || []).join("\n");
  document.getElementById("source-citation").value = data.citation || "";
  document.getElementById("source-reference").value = data.reference || "";
  document.getElementById("source-not-findable").value = data.not_findable_reason || "";
  const status = document.getElementById("citation-status");
  if (result.human_confirmed) {
    status.className = "notice success";
    status.textContent = `Citation confirmed by ${result.confirmed_by}. Editing and saving will require confirmation again.`;
  } else if (result.proposed_fields.length) {
    status.className = "notice warning";
    status.textContent = `HEVA proposed ${result.proposed_fields.join(", ")} from ${result.proposal_method}. Review every value before confirming.`;
  } else {
    status.className = "notice warning";
    status.textContent = "Citation details are saved but not confirmed.";
  }
}

async function loadCitation(documentId) {
  const status = document.getElementById("citation-status");
  try {
    const response = await fetch(
      `/api/documents/${encodeURIComponent(documentId)}/citation`,
    );
    const result = await response.json();
    if (!response.ok) {
      status.className = "notice error";
      status.textContent = result.detail || "Citation details could not be loaded.";
      return;
    }
    displayCitation(result);
    document.getElementById("save-citation").disabled = false;
    document.getElementById("confirm-citation").disabled = false;
  } catch (error) {
    status.className = "notice error";
    status.textContent = "Citation details could not be loaded.";
  }
}

async function persistCitation(confirm) {
  const documentId = document.getElementById("selected-document-id").value;
  if (!documentId) return;
  const status = document.getElementById("citation-status");
  const citationStep = document.querySelector('[data-step="2"]');
  if (confirm && ![...citationStep.querySelectorAll("[required]")].every(
    (input) => input.reportValidity(),
  )) return;
  const suffix = confirm ? "/confirm" : "";
  const response = await fetch(
    `/api/documents/${encodeURIComponent(documentId)}/citation${suffix}`,
    {
      method: confirm ? "POST" : "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(citationDraft()),
    },
  );
  const result = await response.json();
  if (!response.ok) {
    status.className = "notice error";
    status.textContent = result.detail || "Citation details could not be saved.";
    return;
  }
  displayCitation(result);
}

function colorDecisions() {
  return [...document.querySelectorAll(".color-record")].map((record) => {
    const value = record.querySelector("select").value;
    return {
      hex: record.dataset.hex,
      label: value && value !== "__ignore__" ? value : null,
      ignore_reason: value === "__ignore__"
        ? record.querySelector(".ignore-reason").value.trim() || null
        : null,
    };
  });
}

function renderColorConfiguration(result) {
  const configuration = result.configuration;
  const list = document.getElementById("color-list");
  list.replaceChildren(...configuration.colors.map((color) => {
    const record = document.createElement("article");
    record.className = "color-record";
    record.dataset.hex = color.hex;

    const swatch = document.createElement("span");
    swatch.className = "color-swatch";
    swatch.style.setProperty("--swatch", color.hex);
    swatch.style.setProperty("--swatch-text", color.text_color || "#000000");
    swatch.textContent = color.hex;

    const fields = document.createElement("div");
    fields.className = "color-fields";
    const label = document.createElement("label");
    label.textContent = "HEVA label or ignore decision";
    const select = document.createElement("select");
    const undecided = document.createElement("option");
    undecided.value = "";
    undecided.textContent = "Choose a decision…";
    select.append(undecided, ...result.labels.map((value) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = value;
      return option;
    }));
    const ignore = document.createElement("option");
    ignore.value = "__ignore__";
    ignore.textContent = "Ignore this color";
    select.append(ignore);
    if (color.status === "approved") select.value = color.label;
    if (color.status === "ignored") select.value = "__ignore__";

    const reason = document.createElement("textarea");
    reason.className = "ignore-reason";
    reason.rows = 2;
    reason.placeholder = "Reason this observed color should be ignored";
    reason.value = color.ignore_reason || "";
    reason.hidden = select.value !== "__ignore__";
    select.addEventListener("change", () => {
      reason.hidden = select.value !== "__ignore__";
      document.getElementById("mapping-confirmed").checked = false;
    });

    const evidence = document.createElement("p");
    evidence.className = "color-evidence";
    evidence.textContent = color.suggested_label
      ? `Automatic suggestion: ${color.suggested_label}. ${color.reasoning || "No explanation was recorded."}`
      : "No automatic label suggestion is available.";
    label.append(select);
    fields.append(label, reason, evidence);
    record.append(swatch, fields);
    return record;
  }));

  const status = document.getElementById("color-status");
  const confirmed = configuration.human_confirmed;
  status.className = `notice ${confirmed ? "success" : "warning"}`;
  status.textContent = confirmed
    ? `Color configuration confirmed by ${configuration.confirmed_by}.`
    : `${configuration.colors.length} observed color${configuration.colors.length === 1 ? "" : "s"} require explicit human decisions. Suggestions are not approvals.`;
  document.getElementById("mapping-confirmed").disabled = !configuration.colors.length;
  document.getElementById("mapping-confirmed").checked = confirmed;
  document.getElementById("propose-colors").disabled =
    !result.automatic_proposal_available;
  document.getElementById("confirm-colors").disabled = !configuration.colors.length;
  document.getElementById("extract-annotations").disabled = !confirmed;
}

async function loadColors(documentId) {
  const status = document.getElementById("color-status");
  try {
    const response = await fetch(`/api/documents/${encodeURIComponent(documentId)}/colors`);
    const result = await response.json();
    if (!response.ok) {
      status.className = "notice error";
      status.textContent = result.detail || "The color configuration could not be loaded.";
      return;
    }
    renderColorConfiguration(result);
    await loadBatchCandidates(documentId, result.configuration.human_confirmed);
  } catch (error) {
    status.className = "notice error";
    status.textContent = "The color configuration could not be loaded.";
  }
}

function updateBatchAction() {
  const selected = document.querySelectorAll(".batch-candidate input:checked").length;
  document.getElementById("apply-batch-mapping").disabled =
    !selected || !document.getElementById("batch-confirmed").checked;
}

async function loadBatchCandidates(documentId, sourceConfirmed) {
  const panel = document.getElementById("batch-mapping");
  const list = document.getElementById("batch-candidates");
  const status = document.getElementById("batch-status");
  panel.hidden = !sourceConfirmed;
  if (!sourceConfirmed) {
    list.replaceChildren();
    return;
  }
  try {
    const response = await fetch(
      `/api/documents/${encodeURIComponent(documentId)}/colors/batch`,
    );
    const result = await response.json();
    if (!response.ok) {
      status.className = "notice error";
      status.textContent = result.detail || "Batch compatibility could not be checked.";
      return;
    }
    list.replaceChildren(...result.candidates.map((candidate) => {
      const row = document.createElement("label");
      row.className = `batch-candidate ${candidate.eligible ? "" : "incompatible"}`;
      const input = document.createElement("input");
      input.type = "checkbox";
      input.value = candidate.document_id;
      input.disabled = !candidate.eligible;
      input.addEventListener("change", updateBatchAction);
      const details = document.createElement("span");
      const name = document.createElement("strong");
      name.textContent = candidate.source_path;
      const reason = document.createElement("small");
      reason.textContent = candidate.reason;
      details.append(name, reason);
      row.append(input, details);
      return row;
    }));
    const eligible = result.candidates.filter((item) => item.eligible).length;
    status.className = `notice ${eligible ? "success" : "warning"}`;
    status.textContent = eligible
      ? `${eligible} document${eligible === 1 ? "" : "s"} have an exact palette match.`
      : "No other registered document has an eligible matching palette.";
    document.getElementById("batch-confirmed").checked = false;
    updateBatchAction();
  } catch (error) {
    status.className = "notice error";
    status.textContent = "Batch compatibility could not be checked.";
  }
}

async function applyBatchMapping() {
  const documentId = document.getElementById("selected-document-id").value;
  const button = document.getElementById("apply-batch-mapping");
  const status = document.getElementById("batch-status");
  const documentIds = [...document.querySelectorAll(".batch-candidate input:checked")]
    .map((input) => input.value);
  button.disabled = true;
  button.textContent = "Applying…";
  try {
    const response = await fetch(
      `/api/documents/${encodeURIComponent(documentId)}/colors/batch`,
      {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          document_ids: documentIds,
          confirmed: document.getElementById("batch-confirmed").checked,
        }),
      },
    );
    const result = await response.json();
    if (!response.ok) {
      status.className = "notice error";
      status.textContent = result.detail || "The shared mapping was not applied.";
      return;
    }
    await loadBatchCandidates(documentId, true);
    status.className = "notice success";
    status.textContent = `Mapping applied to ${result.applied_document_ids.length} document${result.applied_document_ids.length === 1 ? "" : "s"} with separate confirmation records.`;
  } catch (error) {
    status.className = "notice error";
    status.textContent = "The shared mapping could not be applied.";
  } finally {
    button.textContent = "Apply to selected documents";
  }
}

async function proposeColors() {
  const documentId = document.getElementById("selected-document-id").value;
  const button = document.getElementById("propose-colors");
  const progress = document.getElementById("proposal-progress");
  const status = document.getElementById("color-status");
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 75000);
  let proposalsCreated = false;
  button.disabled = true;
  button.textContent = "Requesting…";
  progress.hidden = false;
  status.className = "notice neutral";
  status.textContent = "Automatic suggestions are being generated locally. They will still require your review.";
  try {
    const response = await fetch(
      `/api/documents/${encodeURIComponent(documentId)}/colors/propose`,
      {method: "POST", signal: controller.signal},
    );
    const result = await response.json();
    if (!response.ok) {
      status.className = "notice error";
      status.textContent = `${result.message || "Suggestions were not created."} ${result.action || ""}`;
      return;
    }
    await loadColors(documentId);
    proposalsCreated = true;
    status.className = "notice warning";
    status.textContent = `${result.proposed_color_count} automatic proposal${result.proposed_color_count === 1 ? "" : "s"} generated. Review every suggestion before confirming.`;
  } catch (error) {
    status.className = "notice error";
    status.textContent = error.name === "AbortError"
      ? "Automatic proposals did not finish in time. Check that local Ollama is running and try again."
      : "Automatic proposals could not be requested from the local service.";
  } finally {
    window.clearTimeout(timeout);
    progress.hidden = true;
    button.textContent = "Request automatic proposals";
    if (!proposalsCreated) button.disabled = false;
  }
}

async function confirmColors() {
  const documentId = document.getElementById("selected-document-id").value;
  const status = document.getElementById("color-status");
  if (!document.getElementById("mapping-confirmed").checked) {
    status.className = "notice error";
    status.textContent = "Confirm that you reviewed every observed color.";
    return;
  }
  const decisions = colorDecisions();
  if (decisions.some((item) => !item.label && !item.ignore_reason)) {
    status.className = "notice error";
    status.textContent = "Choose a label or provide an ignore reason for every color.";
    return;
  }
  const response = await fetch(
    `/api/documents/${encodeURIComponent(documentId)}/colors/confirm`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decisions }),
    },
  );
  const result = await response.json();
  if (!response.ok) {
    status.className = "notice error";
    status.textContent = result.detail || "The color configuration could not be confirmed.";
    return;
  }
  await loadColors(documentId);
  document.getElementById("extraction-status").textContent =
    "Color configuration confirmed. Extraction is ready.";
}

async function extractAnnotations() {
  const documentId = document.getElementById("selected-document-id").value;
  const button = document.getElementById("extract-annotations");
  const progress = document.getElementById("extraction-progress");
  const status = document.getElementById("extraction-status");
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 120000);
  button.disabled = true;
  button.textContent = "Extracting…";
  progress.hidden = false;
  status.className = "notice neutral";
  status.textContent = "Extraction is running. Keep this page open.";
  try {
    const response = await fetch(
      `/api/documents/${encodeURIComponent(documentId)}/extract`,
      { method: "POST", signal: controller.signal },
    );
    const result = await response.json();
    if (!response.ok) {
      status.className = "notice error";
      status.textContent = `${result.message || "Extraction failed."} ${result.action || ""}`;
      return;
    }
    status.className = result.warnings.length ? "notice warning" : "notice success";
    status.textContent = `${result.reused_checkpoint ? "Reused" : "Created"} ${result.record_count} extracted sentence records.${result.warnings.length ? ` ${result.warnings.join(" ")}` : ""}`;
  } catch (error) {
    status.className = "notice error";
    status.textContent = error.name === "AbortError"
      ? "Extraction did not finish within two minutes. Check the source and try again."
      : "Extraction could not be completed. Check the local service and try again.";
  } finally {
    window.clearTimeout(timeout);
    progress.hidden = true;
    button.textContent = "Extract annotations";
    button.disabled = false;
  }
}

async function loadSelectedDocument() {
  const documentId = new URLSearchParams(window.location.search).get("document_id");
  if (!documentId) return;
  const status = document.getElementById("selected-document-status");
  status.hidden = false;
  status.textContent = "Loading the registered document…";
  try {
    const response = await fetch(`/api/documents/${encodeURIComponent(documentId)}`);
    const result = await response.json();
    if (!response.ok) {
      status.className = "notice error";
      status.textContent = result.detail || "The selected document could not be loaded.";
      return;
    }
    document.getElementById("selected-document-id").value = result.document_id;
    document.getElementById("new-document-source").hidden = true;
    document.getElementById("existing-document-source").hidden = false;
    const title = document.getElementById("source-title");
    if (!title.value) title.value = result.filename.replace(/\.[^.]+$/, "");
    status.className = "notice success";
    status.textContent = `Editing ${result.filename}. Its existing project state will be reused.`;
    await loadCitation(documentId);
    await loadColors(documentId);
    if (result.preview_available) {
      openPreview(
        `/api/documents/${encodeURIComponent(documentId)}/source`,
        result.filename,
      );
    } else {
      document.getElementById("preview-name").textContent = result.filename;
      document.getElementById("preview-empty").textContent =
        "Inline preview currently supports PDF documents. This source remains registered and editable.";
    }
  } catch (error) {
    status.className = "notice error";
    status.textContent = "The selected document could not be loaded from the project.";
  }
}

document.getElementById("save-citation").addEventListener(
  "click",
  () => persistCitation(false),
);
document.getElementById("confirm-citation").addEventListener(
  "click",
  () => persistCitation(true),
);
document.getElementById("propose-colors").addEventListener("click", proposeColors);
document.getElementById("confirm-colors").addEventListener("click", confirmColors);
document.getElementById("batch-confirmed").addEventListener("change", updateBatchAction);
document.getElementById("apply-batch-mapping").addEventListener(
  "click",
  applyBatchMapping,
);
document.getElementById("extract-annotations").addEventListener(
  "click",
  extractAnnotations,
);

pdfInput.addEventListener("change", () => {
  previewUrls.forEach((item) => URL.revokeObjectURL(item.url));
  previewUrls = [...pdfInput.files].map((file) => ({ file, url: URL.createObjectURL(file) }));
  const list = document.getElementById("selected-files");
  list.replaceChildren(...previewUrls.map((item, index) => {
    const link = document.createElement("a");
    link.className = "selected-file";
    link.href = item.url;
    link.target = "pdf-preview";
    link.textContent = item.file.name;
    link.addEventListener("click", () => openPreview(item.url, item.file.name));
    if (index === 0) openPreview(item.url, item.file.name);
    return link;
  }));
});

document.querySelectorAll("[name='processing-mode']").forEach((radio) => radio.addEventListener("change", () => {
  const batch = document.querySelector("[name='processing-mode']:checked").value === "batch";
  pdfInput.multiple = batch;
  document.getElementById("source-help").textContent = batch
    ? "Choose multiple PDF or DOCX files. Inspect every PDF in the side viewer."
    : "Choose one PDF or DOCX. A PDF will open in the side viewer.";
}));

window.addEventListener("beforeunload", () => previewUrls.forEach((item) => URL.revokeObjectURL(item.url)));
restoreAnnotator();
loadSelectedDocument();
