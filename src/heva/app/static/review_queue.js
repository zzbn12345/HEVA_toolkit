const statusBox = document.getElementById("queue-status");
const queue = document.getElementById("review-queue");

async function loadQueue() {
  try {
    const response = await fetch("/api/review-queue");
    const result = await response.json();
    if (!response.ok) {
      statusBox.className = "notice error";
      statusBox.textContent = `${result.message} ${result.action}`;
      return;
    }
    const available = result.documents.filter((item) => item.review_available);
    statusBox.className = "notice success";
    statusBox.textContent = `${available.length} document${available.length === 1 ? "" : "s"} available for individual review.`;
    queue.replaceChildren(...result.documents.map((item) => {
      const row = document.createElement("article");
      row.className = "project-row";
      const documentCell = document.createElement("div");
      documentCell.className = "project-document";
      const title = document.createElement("strong");
      title.textContent = item.source_path;
      const identifier = document.createElement("small");
      identifier.textContent = item.document_id;
      documentCell.append(title, identifier);

      const status = document.createElement("span");
      status.className = `status-pill status-${item.status.replace("_", "-")}`;
      status.textContent = item.review_available ? item.status.replace("_", " ") : "not extracted";

      const progressCell = document.createElement("div");
      progressCell.className = "project-progress";
      const progressHeading = document.createElement("div");
      progressHeading.className = "progress-heading";
      const percent = document.createElement("strong");
      percent.textContent = `${item.completion_percent}%`;
      const detail = document.createElement("span");
      detail.textContent = item.review_available
        ? `${item.counts.approved + item.counts.excluded} of ${item.counts.total} complete`
        : "Waiting for extraction";
      progressHeading.append(percent, detail);
      const progress = document.createElement("progress");
      progress.max = 100;
      progress.value = item.completion_percent;
      progress.setAttribute("aria-label", `${item.source_path} review completion`);
      progressCell.append(progressHeading, progress);

      const action = document.createElement("div");
      action.className = "project-action";
      const link = document.createElement("a");
      link.className = "button";
      link.href = item.review_available
        ? `/review/${encodeURIComponent(item.document_id)}`
        : `/create?document_id=${encodeURIComponent(item.document_id)}`;
      link.textContent = "Edit this annotation";
      action.appendChild(link);
      row.append(documentCell, status, progressCell, action);
      return row;
    }));
  } catch (error) {
    statusBox.className = "notice error";
    statusBox.textContent = "The review queue could not be loaded.";
  }
}

loadQueue();
