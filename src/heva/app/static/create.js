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
