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
      const card = document.createElement("article");
      card.className = "document-result";
      const title = document.createElement("h2");
      title.textContent = item.source_path;
      const progress = document.createElement("p");
      progress.textContent = item.review_available
        ? `${item.counts.approved} approved · ${item.counts.pending} pending · ${item.counts.needs_correction} need correction · ${item.counts.flagged} flagged`
        : "Extraction or review initialization is still required.";
      card.append(title, progress);
      if (item.review_available) {
        const link = document.createElement("a");
        link.className = "button";
        link.href = `/review/${encodeURIComponent(item.document_id)}`;
        link.textContent = "Review this document";
        card.appendChild(link);
      }
      return card;
    }));
  } catch (error) {
    statusBox.className = "notice error";
    statusBox.textContent = "The review queue could not be loaded.";
  }
}

loadQueue();
