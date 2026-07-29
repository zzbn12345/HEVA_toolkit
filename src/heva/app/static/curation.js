const statusBox = document.getElementById("curation-status");
const queue = document.getElementById("curation-queue");
let curatorDocuments = [];
let curatorFilter = "in_review";

function textElement(tag, className, text) {
  const element = document.createElement(tag);
  element.className = className;
  element.textContent = text;
  return element;
}

function visibleDocuments() {
  if (curatorFilter === "in_review") {
    return curatorDocuments.filter((item) => item.status === "in_review");
  }
  if (curatorFilter === "attention") {
    return curatorDocuments.filter((item) => !item.validation.valid);
  }
  if (curatorFilter === "valid") {
    return curatorDocuments.filter((item) => item.validation.valid);
  }
  return curatorDocuments;
}

function issueList(issues) {
  const list = document.createElement("ul");
  list.className = "curation-issues";
  issues.forEach((issue) => {
    const item = document.createElement("li");
    item.append(
      textElement("strong", `issue-${issue.severity}`, `${issue.severity} · ${issue.code}`),
      textElement("span", "", issue.message),
      textElement("small", "", `Next step: ${issue.action}`),
    );
    list.appendChild(item);
  });
  return list;
}

function curatorCard(item) {
  const card = document.createElement("article");
  card.className = "curation-card";
  const heading = document.createElement("div");
  heading.className = "curation-heading";
  const identity = document.createElement("div");
  identity.append(
    textElement("h2", "", item.source_path),
    textElement("small", "", item.document_id),
  );
  const badges = document.createElement("div");
  badges.className = "curation-badges";
  badges.append(
    textElement("span", `status-pill status-${item.status.replace("_", "-")}`, item.status.replace("_", " ")),
    textElement(
      "span",
      `validation-badge ${item.validation.valid ? "valid" : "invalid"}`,
      item.validation.valid ? "Validator passed" : "Validation blocked",
    ),
  );
  heading.append(identity, badges);
  card.appendChild(heading);

  if (item.validation.issues.length) {
    const details = document.createElement("details");
    const summary = document.createElement("summary");
    summary.textContent = `${item.validation.issues.length} validation finding${item.validation.issues.length === 1 ? "" : "s"}`;
    details.append(summary, issueList(item.validation.issues));
    card.appendChild(details);
  } else {
    card.appendChild(textElement("p", "notice success", "All current HEVA validation layers passed."));
  }

  const actions = document.createElement("div");
  actions.className = "curation-actions";
  const evidence = textElement("a", "button secondary", "Open annotation evidence");
  evidence.href = `/review/${encodeURIComponent(item.document_id)}`;
  actions.appendChild(evidence);
  card.appendChild(actions);
  return card;
}

function renderQueue() {
  const visible = visibleDocuments();
  if (!visible.length) {
    queue.replaceChildren(
      textElement("p", "notice neutral", "No documents match this curator filter."),
    );
    return;
  }
  queue.replaceChildren(...visible.map(curatorCard));
}

async function loadCuration() {
  try {
    const [projectResponse, validationResponse] = await Promise.all([
      fetch("/api/project"),
      fetch("/api/validate", {method: "POST"}),
    ]);
    const project = await projectResponse.json();
    const validation = await validationResponse.json();
    if (!projectResponse.ok || !validation.documents) {
      statusBox.className = "notice error";
      statusBox.textContent =
        validation.action || project.action || "The curator queue could not be loaded.";
      return;
    }
    const reports = new Map(
      validation.documents.map((item) => [item.document_id, item]),
    );
    curatorDocuments = project.documents.map((document) => ({
      ...document,
      validation: reports.get(document.document_id),
    })).filter((item) => item.validation);
    const awaiting = curatorDocuments.filter((item) => item.status === "in_review").length;
    const valid = curatorDocuments.filter((item) => item.validation.valid).length;
    statusBox.className = "notice success";
    statusBox.textContent =
      `${awaiting} document${awaiting === 1 ? "" : "s"} awaiting curator review; ${valid} of ${curatorDocuments.length} pass validation.`;
    renderQueue();
  } catch (error) {
    statusBox.className = "notice error";
    statusBox.textContent = "The curator queue could not be loaded from the local project.";
  }
}

document.querySelectorAll("[data-curation-filter]").forEach((button) => {
  button.addEventListener("click", () => {
    curatorFilter = button.dataset.curationFilter;
    document.querySelectorAll("[data-curation-filter]").forEach((item) => {
      item.classList.toggle("active", item === button);
    });
    renderQueue();
  });
});

loadCuration();
