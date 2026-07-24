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
      document.getElementById("annotator-name").value = result.annotator.name || "";
      document.getElementById("annotator-orcid").value = result.annotator.orcid || "";
      status.className = "notice success";
      status.textContent = `Active project annotator: ${result.annotator.name}`;
    } else {
      status.textContent = "No annotator has been saved for this project.";
    }
  } catch (error) {
    status.className = "notice error";
    status.textContent = "The annotator profile could not be loaded.";
  }
}

document.getElementById("save-annotator").addEventListener("click", async () => {
  const name = document.getElementById("annotator-name");
  if (!name.reportValidity()) return;
  const status = document.getElementById("annotator-status");
  const response = await fetch("/api/annotator", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name: name.value.trim(),
      orcid: document.getElementById("annotator-orcid").value.trim() || null,
    }),
  });
  const result = await response.json();
  if (!response.ok) {
    const detail = result.detail || result;
    status.className = "notice error";
    status.textContent = `${detail.message} ${detail.action}`;
    return;
  }
  status.className = "notice success";
  status.textContent = `Active project annotator: ${result.annotator.name}`;
});

function openPreview(url, name) {
  const frame = document.getElementById("pdf-preview");
  frame.src = url;
  frame.style.display = "block";
  document.getElementById("preview-empty").style.display = "none";
  document.getElementById("preview-name").textContent = name;
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
    ? "Choose multiple PDFs and inspect each one in the side viewer."
    : "Choose one PDF. It will open in the side viewer.";
}));

window.addEventListener("beforeunload", () => previewUrls.forEach((item) => URL.revokeObjectURL(item.url)));
restoreAnnotator();
