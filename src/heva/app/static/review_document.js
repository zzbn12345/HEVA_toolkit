const documentId = document.body.dataset.documentId;
const app = document.getElementById("review-app");
const list = document.getElementById("sentence-list");
const statusBox = document.getElementById("review-status");
let reviewDocument = null;

function textElement(tag, className, text) {
  const element = document.createElement(tag);
  element.className = className;
  element.textContent = text;
  return element;
}

async function decide(sentenceId, status) {
  const response = await fetch(`/api/review/${encodeURIComponent(documentId)}/decisions`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sentence_ids: [sentenceId], status }),
  });
  const result = await response.json();
  if (!response.ok) {
    statusBox.className = "notice error";
    statusBox.textContent = `${result.message} ${result.action}`;
    return;
  }
  reviewDocument = result;
  render();
}

function sentenceCard(item) {
  const record = item.record;
  const card = document.createElement("article");
  card.className = `sentence-card${item.flags.length ? " problematic" : ""}`;
  card.dataset.status = item.review.status;
  card.dataset.problematic = String(Boolean(item.flags.length));
  card.appendChild(textElement("div", "sentence-meta", `Sentence ${record.sentence_id} · Page ${record.page} · ${item.review.status}`));
  card.appendChild(textElement("p", "sentence-text", record.sentence));
  const entities = document.createElement("div");
  entities.className = "entity-list";
  for (const entity of record.entities) {
    const wrapper = textElement("span", "entity", `${entity.text} · ${entity.label}`);
    if (entity.color) {
      const color = textElement("span", "entity-color", entity.color);
      color.style.background = entity.color;
      const rgb = entity.color.slice(1).match(/../g).map((value) => parseInt(value, 16));
      const luminance = 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2];
      color.style.color = luminance > 145 ? "#000000" : "#FFFFFF";
      wrapper.prepend(color);
    }
    entities.appendChild(wrapper);
  }
  card.appendChild(entities);
  if (item.flags.length) {
    const flags = document.createElement("div");
    flags.className = "flag-list";
    item.flags.forEach((flag) => flags.appendChild(textElement("span", "flag", `${flag.code}: ${flag.message}`)));
    card.appendChild(flags);
  }
  const actions = document.createElement("div");
  actions.className = "decision-actions";
  [["Approve", "approved"], ["Needs correction", "needs_correction"], ["Exclude", "excluded"]].forEach(([label, status]) => {
    const button = textElement("button", `button${status === "approved" ? "" : " secondary"}`, label);
    button.type = "button";
    button.addEventListener("click", () => decide(record.sentence_id, status));
    actions.appendChild(button);
  });
  card.appendChild(actions);
  return card;
}

function render() {
  const filter = document.getElementById("review-filter").value;
  const limit = Number(document.getElementById("page-size").value);
  const visible = reviewDocument.sentences.filter((item) => {
    if (filter === "pending") return item.review.status === "pending";
    if (filter === "problematic") return item.flags.length > 0 || item.review.status === "needs_correction";
    return true;
  }).slice(0, limit);
  list.replaceChildren(...visible.map(sentenceCard));
  statusBox.className = "notice success";
  statusBox.textContent = `Showing ${visible.length} of ${reviewDocument.sentences.length} sentences from this document only.`;
}

function navigationLink(documentIdValue, label) {
  const link = textElement("a", "button secondary", label);
  link.href = `/review/${encodeURIComponent(documentIdValue)}`;
  return link;
}

async function loadDocument() {
  const response = await fetch(`/api/review/${encodeURIComponent(documentId)}`);
  const result = await response.json();
  if (!response.ok) {
    statusBox.className = "notice error";
    statusBox.textContent = `${result.message} ${result.action}`;
    return;
  }
  reviewDocument = result;
  document.getElementById("document-name").textContent = result.source_path;
  document.getElementById("review-pdf-frame").src = `/api/review/${encodeURIComponent(documentId)}/source`;
  const navigation = document.getElementById("document-navigation");
  if (result.previous_document_id) navigation.appendChild(navigationLink(result.previous_document_id, "← Previous document"));
  else navigation.appendChild(document.createElement("span"));
  if (result.next_document_id) navigation.appendChild(navigationLink(result.next_document_id, "Next document →"));
  render();
}

document.getElementById("toggle-review-pdf").addEventListener("click", (event) => {
  const hidden = app.classList.toggle("pdf-hidden");
  event.currentTarget.textContent = hidden ? "Show PDF" : "Hide PDF";
  event.currentTarget.setAttribute("aria-expanded", String(!hidden));
});
document.getElementById("review-filter").addEventListener("change", render);
document.getElementById("page-size").addEventListener("change", render);
loadDocument();
