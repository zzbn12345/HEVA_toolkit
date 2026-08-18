const statusBox = document.getElementById("queue-status");
const queue = document.getElementById("review-queue");
let documents = [];
let readinessFilter = "all";

const gateLabels = {
  citation: "Citation",
  color_configuration: "Colors",
  extraction: "Extraction",
  sentence_review: "Sentences",
};

function visibleDocuments() {
  if (readinessFilter === "complete") {
    return documents.filter((item) => item.annotation_complete);
  }
  if (readinessFilter === "incomplete") {
    return documents.filter((item) => !item.annotation_complete);
  }
  return documents;
}

function renderQueue() {
  const visible = visibleDocuments();
  if (!visible.length) {
    const empty = document.createElement("p");
    empty.className = "notice neutral";
    empty.textContent = "No documents match this completion filter.";
    queue.replaceChildren(empty);
    return;
  }
  queue.replaceChildren(...visible.map((item) => {
    const row = document.createElement("article");
    row.className = "project-row";

    const documentCell = document.createElement("div");
    documentCell.className = "project-document";
    const title = document.createElement("strong");
    title.textContent = item.source_path;
    const identifier = document.createElement("small");
    identifier.textContent = item.document_id;
    documentCell.append(title, identifier);

    const workflow = document.createElement("span");
    workflow.className = `status-pill status-${item.status.replace("_", "-")}`;
    workflow.textContent = item.status.replace("_", " ");

    const readiness = document.createElement("div");
    readiness.className = "readiness-cell";
    const badge = document.createElement("strong");
    badge.className = `readiness-badge ${item.annotation_complete ? "complete" : "incomplete"}`;
    badge.textContent = item.annotation_complete ? "Complete" : "Incomplete";
    const gates = document.createElement("div");
    gates.className = "readiness-gates";
    Object.entries(item.readiness_gates).forEach(([key, passed]) => {
      const gate = document.createElement("span");
      gate.className = `gate ${passed ? "passed" : "blocked"}`;
      gate.textContent = `${passed ? "✓" : "○"} ${gateLabels[key]}`;
      gates.append(gate);
    });
    readiness.append(badge, gates);
    if (item.blocking_reasons.length) {
      const details = document.createElement("details");
      const summary = document.createElement("summary");
      summary.textContent = `${item.blocking_reasons.length} action${item.blocking_reasons.length === 1 ? "" : "s"} required`;
      const reasons = document.createElement("ul");
      item.blocking_reasons.forEach((reason) => {
        const line = document.createElement("li");
        line.textContent = reason;
        reasons.append(line);
      });
      details.append(summary, reasons);
      readiness.append(details);
    }

    const progressCell = document.createElement("div");
    progressCell.className = "project-progress";
    const progressHeading = document.createElement("div");
    progressHeading.className = "progress-heading";
    const percent = document.createElement("strong");
    percent.textContent = `${item.completion_percent}%`;
    const detail = document.createElement("span");
    detail.textContent = item.review_available
      ? `${item.counts.approved + item.counts.excluded} of ${item.counts.total}`
      : "Not available";
    progressHeading.append(percent, detail);
    const progress = document.createElement("progress");
    progress.max = 100;
    progress.value = item.completion_percent;
    progress.setAttribute("aria-label", `${item.source_path} sentence review completion`);
    progressCell.append(progressHeading, progress);

    const action = document.createElement("div");
    action.className = "project-action";
    const link = document.createElement("a");
    link.className = "button";
    link.href = `/create?document_id=${encodeURIComponent(item.document_id)}&section=annotations`;
    link.textContent = "Edit this annotation";
    action.appendChild(link);
    row.append(documentCell, workflow, readiness, progressCell, action);
    return row;
  }));
}

async function loadQueue() {
  try {
    const response = await fetch("/api/review-queue");
    const result = await response.json();
    if (!response.ok) {
      statusBox.className = "notice error";
      statusBox.textContent = `${result.message} ${result.action}`;
      return;
    }
    documents = result.documents;
    const complete = documents.filter((item) => item.annotation_complete).length;
    statusBox.className = "notice success";
    statusBox.textContent = result.added_document_ids?.length
      ? `${result.added_document_ids.length} new document${result.added_document_ids.length === 1 ? " was" : "s were"} added from the project folder. ${complete} of ${documents.length} documents are annotation-complete.`
      : `${complete} of ${documents.length} documents are annotation-complete.`;
    renderQueue();
  } catch (error) {
    statusBox.className = "notice error";
    statusBox.textContent = "The document dashboard could not be loaded.";
  }
}

document.querySelectorAll("[data-readiness]").forEach((button) => {
  button.addEventListener("click", () => {
    readinessFilter = button.dataset.readiness;
    document.querySelectorAll("[data-readiness]").forEach((item) => {
      item.classList.toggle("active", item === button);
    });
    renderQueue();
  });
});

loadQueue();

/** Close only the active local session; project files remain untouched. */
async function leaveProject() {
  const response = await fetch("/api/projects/close", {method: "POST"});
  if (!response.ok) {
    statusBox.className = "notice error";
    statusBox.textContent = "The project could not be closed.";
    return;
  }
  window.location.assign("/");
}

document.getElementById("open-another-project").addEventListener("click", leaveProject);
document.getElementById("close-project").addEventListener("click", leaveProject);
