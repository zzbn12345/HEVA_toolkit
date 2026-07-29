const statusBox = document.getElementById("curation-status");
const queue = document.getElementById("curation-queue");
let curatorDocuments = [];
let curatorFilter = "in_review";

/**
 * Build a text-only element so package content is never interpreted as HTML.
 * @param {string} tag
 * @param {string} className
 * @param {string} text
 * @returns {HTMLElement}
 */
function textElement(tag, className, text) {
  const element = document.createElement(tag);
  element.className = className;
  element.textContent = text;
  return element;
}

/**
 * Return queue records matching the currently selected curator filter.
 * @returns {Array<object>}
 */
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

/**
 * Render actionable validator findings for one candidate.
 * @param {Array<object>} issues
 * @returns {HTMLUListElement}
 */
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

/**
 * Submit one audited curator action and refresh the queue.
 * @param {object} item
 * @param {HTMLFormElement} form
 * @param {string} decision
 * @returns {Promise<void>}
 */
async function submitDecision(item, form, decision) {
  const status = form.querySelector("[data-decision-status]");
  const requestedChanges = form.elements.requested_changes.value
    .split("\n")
    .map((value) => value.trim())
    .filter(Boolean);
  status.className = "notice neutral";
  status.textContent = "Saving curator decision…";
  try {
    const response = await fetch(
      `/api/curation/${encodeURIComponent(item.document_id)}/decisions`,
      {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          decision,
          actor: form.elements.actor.value,
          evidence: form.elements.evidence.value,
          requested_changes: requestedChanges,
        }),
      },
    );
    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.action || result.detail || "Decision was not saved.");
    }
    await loadCuration();
  } catch (error) {
    status.className = "notice error";
    status.textContent = error.message;
  }
}

/**
 * Build decision controls only for an undecided immutable candidate.
 * @param {object} item
 * @returns {HTMLElement}
 */
function decisionPanel(item) {
  const container = document.createElement("section");
  container.className = "decision-panel";
  const candidate = item.curation?.candidates?.at(-1);
  const decision = item.curation?.decisions
    ?.filter((entry) => entry.candidate_id === candidate?.candidate_id)
    .at(-1);
  if (!candidate) {
    container.appendChild(
      textElement("p", "notice neutral", "No immutable candidate snapshot is recorded."),
    );
    return container;
  }
  container.append(
    textElement(
      "p",
      "candidate-id",
      `Candidate ${candidate.candidate_id.slice(0, 12)}… · submitted by ${candidate.submitted_by}`,
    ),
  );
  if (decision) {
    container.append(
      textElement(
        "p",
        "notice success",
        `${decision.decision.replace("_", " ")} by ${decision.actor}: ${decision.evidence}`,
      ),
    );
    return container;
  }
  if (item.status !== "in_review") {
    return container;
  }
  const form = document.createElement("form");
  form.className = "decision-form";
  form.innerHTML = `
    <label>Curator name <span aria-hidden="true">*</span>
      <input name="actor" required>
    </label>
    <label>Decision evidence or rationale <span aria-hidden="true">*</span>
      <textarea name="evidence" rows="3" required></textarea>
    </label>
    <label>Requested changes <small>(one per line; required only for Request changes)</small>
      <textarea name="requested_changes" rows="3"></textarea>
    </label>
    <div class="decision-buttons">
      <button class="button" type="button" data-decision="accepted">Accept</button>
      <button class="button secondary" type="button" data-decision="changes_requested">Request changes</button>
      <button class="button secondary" type="button" data-decision="rejected">Reject</button>
      <button class="button secondary warning" type="button" data-decision="quarantined">Quarantine</button>
    </div>
    <p class="notice neutral" data-decision-status aria-live="polite">Choose a decision after inspecting the evidence.</p>
  `;
  form.querySelectorAll("[data-decision]").forEach((button) => {
    button.addEventListener("click", () => {
      if (!form.reportValidity()) {
        return;
      }
      submitDecision(item, form, button.dataset.decision);
    });
  });
  container.appendChild(form);
  return container;
}

/**
 * Build one curator queue card from registry, validation, and snapshot evidence.
 * @param {object} item
 * @returns {HTMLElement}
 */
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
  card.appendChild(decisionPanel(item));
  return card;
}

/** Render the current filter without requesting new project state. */
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

/** Load registry, current validation, and local curation evidence. */
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
    curatorDocuments = await Promise.all(
      project.documents.map(async (document) => {
        const curationResponse = await fetch(
          `/api/curation/${encodeURIComponent(document.document_id)}`,
        );
        return {
          ...document,
          validation: reports.get(document.document_id),
          curation: curationResponse.ok ? await curationResponse.json() : null,
        };
      }),
    );
    curatorDocuments = curatorDocuments.filter((item) => item.validation);
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
