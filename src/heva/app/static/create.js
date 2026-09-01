const app = document.getElementById("create-app");
const content = document.getElementById("create-content");
const steps = [...document.querySelectorAll(".create-step")];
const stepButtons = [...document.querySelectorAll(".step-button")];
const automaticCompilationAttempts = new Set();

/** Reflect persisted readiness without implying that merely visiting a section completes it. */
function setReadiness(key, complete, missingMessage) {
  const button = document.querySelector(`[data-readiness-key="${key}"]`);
  if (!button) return;
  button.classList.toggle("complete", complete);
  button.classList.toggle("missing", !complete);
  button.querySelector("b").textContent = complete ? "✓" : "×";
  button.setAttribute(
    "aria-label",
    `${button.querySelector("span").textContent}: ${complete ? "complete" : "missing"}`,
  );
  button.title = complete ? "Complete" : missingMessage;
}

function showStep(number) {
  steps.forEach((step) => step.classList.toggle("active", step.dataset.step === String(number)));
  stepButtons.forEach((button) => button.classList.toggle("active", button.dataset.stepTarget === String(number)));
  updateAnnotationsLayout(number);
  content.scrollTop = 0;
}

/** Expand the existing sentence-review workspace across the document area. */
function updateAnnotationsLayout(activeStep = null) {
  const review = document.getElementById("annotations-review");
  const step = activeStep || document.querySelector(".create-step.active")?.dataset.step;
  const reviewActive = String(step) === "4" && !review.hidden;
  app.classList.toggle("annotations-review-active", reviewActive);
  content.classList.toggle("annotations-review-active", reviewActive);
}

/** Show extraction, compilation, or review controls according to persisted evidence. */
function showAnnotationsWorkspace(
  documentId,
  canonicalReady,
  draftAvailable = false,
  compilationReady = false,
) {
  const setup = document.getElementById("annotation-setup");
  const review = document.getElementById("annotations-review");
  const compilation = document.getElementById("draft-compilation");
  const reviewAvailable = canonicalReady || draftAvailable;
  setup.hidden = reviewAvailable;
  review.hidden = !reviewAvailable;
  compilation.hidden = !(draftAvailable && !canonicalReady && compilationReady);
  if (reviewAvailable && !review.src) {
    review.src = `/review/${encodeURIComponent(documentId)}?embedded=1`;
  }
  updateAnnotationsLayout();
}

/** Reload readiness and sentence evidence after document configuration changes. */
function refreshAnnotationsReview() {
  const review = document.getElementById("annotations-review");
  if (!review.src) return;
  const refreshed = new URL(review.src);
  refreshed.searchParams.set("refresh", Date.now().toString());
  review.src = refreshed.toString();
}

/** Load sentence-curation and validator outcomes for the selected document. */
async function loadDocumentReadiness(documentId) {
  try {
    const response = await fetch("/api/review-queue");
    const result = await response.json();
    const document = response.ok
      ? result.documents.find((item) => item.document_id === documentId)
      : null;
    setReadiness(
      "curated",
      Boolean(document?.readiness_gates?.sentence_review),
      "Approve or exclude every extracted sentence.",
    );
  } catch (error) {
    setReadiness("curated", false, "Sentence curation status could not be loaded.");
  }
  try {
    const response = await fetch("/api/validate", {method: "POST"});
    const result = await response.json();
    const document = response.ok
      ? result.documents.find((item) => item.document_id === documentId)
      : null;
    setReadiness(
      "validated",
      Boolean(document?.valid),
      "Resolve this document's validation findings.",
    );
  } catch (error) {
    setReadiness("validated", false, "Document validation could not be run.");
  }
}

window.addEventListener("message", (event) => {
  if (event.origin !== window.location.origin) return;
  const documentId = document.getElementById("selected-document-id").value;
  if (!documentId || event.data.documentId !== documentId) return;
  if (event.data?.type === "heva-review-updated") {
    loadDocumentReadiness(documentId);
    return;
  }
  if (event.data?.type === "heva-pdf-evidence") {
    const page = Number(event.data.page);
    if (!Number.isInteger(page) || page < 1) return;
    app.classList.remove("pdf-hidden");
    const toggle = document.getElementById("toggle-pdf");
    toggle.textContent = "Hide PDF";
    toggle.setAttribute("aria-expanded", "true");
    openPreview(
      `/api/documents/${encodeURIComponent(documentId)}/source#page=${event.data.page}`,
      `Source evidence · page ${page}`,
    );
  }
});

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
    const response = await fetch("/api/people");
    const result = await response.json();
    if (!response.ok) {
      status.className = "notice error";
      status.textContent = `${result.message} ${result.action}`;
      return;
    }
    const curator = result.people?.find((person) => person.person_id === result.active_curator_id);
    if (curator) {
      status.className = "notice success";
      status.textContent = `Active project curator: ${curator.name}`;
      setReadiness("curator", true, "Select an active curator.");
    } else {
      status.className = "notice warning";
      status.textContent = "No active curator is selected. You can register a document now, but curator identity is required before accountable workflow actions.";
      setReadiness("curator", false, "Select an active curator.");
    }
  } catch (error) {
    status.className = "notice error";
    status.textContent = "Project people and roles could not be loaded.";
    setReadiness("curator", false, "Project people and roles could not be loaded.");
  }
}

/** Load eligible project people and explicit original annotators for one document. */
async function loadDocumentAnnotators(documentId) {
  const options = document.getElementById("document-annotator-options");
  const status = document.getElementById("document-annotator-status");
  const save = document.getElementById("save-document-annotators");
  try {
    const response = await fetch(`/api/documents/${encodeURIComponent(documentId)}/annotators`);
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Original annotators could not be loaded.");
    const selected = new Set(result.assigned_person_ids);
    options.replaceChildren(...result.annotators.map((person) => {
      const label = document.createElement("label");
      const input = document.createElement("input");
      input.type = "checkbox";
      input.value = person.person_id;
      input.checked = selected.has(person.person_id);
      label.append(input, document.createTextNode(` ${person.name}${person.affiliation ? ` — ${person.affiliation}` : ""}`));
      return label;
    }));
    status.className = `notice ${selected.size ? "success" : "warning"}`;
    status.textContent = result.annotators.length
      ? (selected.size ? `${selected.size} original annotator${selected.size === 1 ? " is" : "s are"} assigned.` : "No original annotator is assigned to this document.")
      : "No project person has the original annotator role. Add one under People and roles.";
    save.disabled = !result.annotators.length;
    setReadiness("original-annotator", selected.size > 0, "Assign at least one original annotator.");
  } catch (error) {
    options.replaceChildren();
    status.className = "notice error";
    status.textContent = error.message;
    save.disabled = true;
    setReadiness("original-annotator", false, "Original annotators could not be loaded.");
  }
}

document.getElementById("save-document-annotators").addEventListener("click", async () => {
  const documentId = document.getElementById("selected-document-id").value;
  const personIds = [...document.querySelectorAll("#document-annotator-options input:checked")]
    .map((input) => input.value);
  const response = await fetch(`/api/documents/${encodeURIComponent(documentId)}/annotators`, {
    method: "PUT",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({person_ids: personIds}),
  });
  const result = await response.json();
  if (!response.ok) {
    const status = document.getElementById("document-annotator-status");
    status.className = "notice error";
    status.textContent = result.detail || "Original annotators could not be saved.";
    return;
  }
  await loadDocumentAnnotators(documentId);
  await loadDocumentReadiness(documentId);
});

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

/** Apply the same citation release gate used by the backend review projection. */
function citationIsReady(result) {
  const data = result.data || {};
  return Boolean(
    result.human_confirmed
    && data.title
    && data.creators?.length
    && data.citation
    && (data.reference || data.not_findable_reason)
  );
}

function displayCitation(result) {
  const data = result.data;
  document.getElementById("source-title").value = data.title || "";
  document.getElementById("source-creators").value = (data.creators || []).join("\n");
  document.getElementById("source-citation").value = data.citation || "";
  document.getElementById("source-reference").value = data.reference || "";
  document.getElementById("source-not-findable").value = data.not_findable_reason || "";
  const status = document.getElementById("citation-status");
  const ready = citationIsReady(result);
  if (ready) {
    status.className = "notice success";
    status.textContent = `Citation confirmed by ${result.confirmed_by}. Editing and saving will require confirmation again.`;
  } else if (result.human_confirmed) {
    status.className = "notice warning";
    status.textContent = "Citation confirmed, but it still needs a DOI/public URL or an explanation of why the source is not publicly findable.";
  } else if (result.proposed_fields.length) {
    status.className = "notice warning";
    status.textContent = `HEVA proposed ${result.proposed_fields.join(", ")} from ${result.proposal_method}. Review every value before confirming.`;
  } else {
    status.className = "notice warning";
    status.textContent = "Citation details are saved but not confirmed.";
  }
  setReadiness("citation", ready, "Complete and confirm the document citation.");
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
  await loadDocumentReadiness(documentId);
  refreshAnnotationsReview();
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

/** Summarize the supervised document-specific hex-to-label decisions as a live legend. */
function renderDocumentColorCode() {
  const code = document.getElementById("color-code-list");
  const records = [...document.querySelectorAll(".color-record")];
  if (!records.length) {
    const empty = document.createElement("p");
    empty.className = "muted";
    empty.textContent = "Discover document colors to build this code.";
    code.replaceChildren(empty);
    return;
  }
  const groups = new Map();
  records.forEach((record) => {
    const selected = record.querySelector("select").value;
    const meaning = selected === "__ignore__"
      ? "Ignored color"
      : selected || "HEVA label not assigned";
    if (!groups.has(meaning)) groups.set(meaning, []);
    groups.get(meaning).push({
      hex: record.dataset.hex,
      textColor: record.querySelector(".color-swatch").style.getPropertyValue("--swatch-text"),
    });
  });
  code.replaceChildren(...[...groups.entries()].map(([meaning, colors]) => {
    const entry = document.createElement("div");
    entry.className = "color-code-entry";
    const chips = document.createElement("span");
    chips.className = "color-code-chips";
    colors.forEach((color) => {
      const chip = document.createElement("span");
      chip.className = "color-code-chip";
      chip.style.setProperty("--swatch", color.hex);
      chip.style.setProperty("--swatch-text", color.textColor);
      chip.textContent = color.hex;
      chip.setAttribute("aria-label", `Observed color ${color.hex}`);
      chips.append(chip);
    });
    const arrow = document.createElement("span");
    arrow.className = "color-code-arrow";
    arrow.textContent = "means";
    const label = document.createElement("strong");
    label.textContent = meaning;
    entry.append(chips, arrow, label);
    return entry;
  }));
}

/** Return black or white according to WCAG relative luminance contrast. */
function contrastingTextColor(hex) {
  const channels = hex.slice(1).match(/.{2}/g).map((value) => parseInt(value, 16) / 255);
  const [red, green, blue] = channels.map((value) =>
    value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4,
  );
  const luminance = (0.2126 * red) + (0.7152 * green) + (0.0722 * blue);
  return luminance > 0.179 ? "#111111" : "#FFFFFF";
}

/** Render the repository-owned HEVA visual reference without treating it as exact evidence. */
async function loadReferenceColorCode() {
  const list = document.getElementById("reference-color-list");
  try {
    const response = await fetch("/static/heva-reference-palette.json");
    if (!response.ok) throw new Error("Reference palette unavailable");
    const reference = await response.json();
    list.replaceChildren(...reference.values.map((value) => {
      const card = document.createElement("article");
      card.className = "reference-color-card";
      card.style.setProperty("--reference-color", value.hex);
      card.style.setProperty("--reference-text", contrastingTextColor(value.hex));
      const label = document.createElement("strong");
      label.textContent = value.label;
      const hex = document.createElement("code");
      hex.textContent = value.hex;
      const children = document.createElement("small");
      children.textContent = value.subcategories.join(" · ");
      card.append(label, hex, children);
      return card;
    }));
  } catch (error) {
    list.textContent = "The HEVA reference palette could not be loaded.";
  }
}

/**
 * Render persisted color decisions and preselect supervised automatic suggestions.
 * Model reasoning remains provenance data and is not presented as a fixed specification.
 * @param {object} result
 */
function renderColorConfiguration(result) {
  const configuration = result.configuration;
  const occurrencesByColor = result.occurrences || {};
  const list = document.getElementById("color-list");
  list.replaceChildren(...configuration.colors.map((color) => {
    const record = document.createElement("article");
    record.className = "color-record";
    record.dataset.hex = color.hex;
    record.style.setProperty("--swatch", color.hex);

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
    if (
      color.status === "pending_review"
      && color.suggested_label
      && result.labels.includes(color.suggested_label)
    ) {
      select.value = color.suggested_label;
    }

    const reason = document.createElement("textarea");
    reason.className = "ignore-reason";
    reason.rows = 2;
    reason.placeholder = "Reason this observed color should be ignored";
    reason.value = color.ignore_reason || "";
    reason.hidden = select.value !== "__ignore__";
    select.addEventListener("change", () => {
      reason.hidden = select.value !== "__ignore__";
      document.getElementById("mapping-confirmed").checked = false;
      renderDocumentColorCode();
    });

    label.append(select);
    fields.append(label, reason);

    const occurrences = occurrencesByColor[color.hex] || [];
    const evidence = document.createElement("section");
    evidence.className = "color-occurrences";
    const evidenceSummary = document.createElement("p");
    evidenceSummary.className = "color-occurrence-summary";
    if (!occurrences.length) {
      evidenceSummary.textContent = "No source occurrence evidence is available for this color.";
      evidence.append(evidenceSummary);
    } else {
      const pages = [...new Set(occurrences.map((occurrence) => occurrence.page))];
      evidenceSummary.textContent =
        `${occurrences.length} occurrence${occurrences.length === 1 ? "" : "s"} on `
        + `${pages.length === 1 ? "page" : "pages"} ${pages.join(", ")}.`;
      const snippet = document.createElement("blockquote");
      snippet.className = "color-occurrence-snippet";
      const controls = document.createElement("div");
      controls.className = "color-occurrence-controls";
      const position = document.createElement("span");
      position.className = "muted";
      const previous = document.createElement("button");
      previous.className = "button secondary";
      previous.type = "button";
      previous.textContent = "Previous occurrence";
      const open = document.createElement("button");
      open.className = "button secondary";
      open.type = "button";
      const next = document.createElement("button");
      next.className = "button secondary";
      next.type = "button";
      next.textContent = "Next occurrence";
      let occurrenceIndex = 0;
      const renderOccurrence = () => {
        const occurrence = occurrences[occurrenceIndex];
        snippet.replaceChildren();
        snippet.append(
          document.createTextNode(occurrence.sentence.slice(0, occurrence.start)),
        );
        const mark = document.createElement("mark");
        mark.style.setProperty("--occurrence-color", color.hex);
        mark.style.setProperty(
          "--occurrence-text",
          color.text_color || contrastingTextColor(color.hex),
        );
        mark.textContent = occurrence.sentence.slice(occurrence.start, occurrence.end);
        snippet.append(
          mark,
          document.createTextNode(occurrence.sentence.slice(occurrence.end)),
        );
        position.textContent = `Occurrence ${occurrenceIndex + 1} of ${occurrences.length}`;
        open.textContent = `View page ${occurrence.page} in source`;
        previous.disabled = occurrenceIndex === 0;
        next.disabled = occurrenceIndex === occurrences.length - 1;
      };
      previous.addEventListener("click", () => {
        occurrenceIndex -= 1;
        renderOccurrence();
      });
      next.addEventListener("click", () => {
        occurrenceIndex += 1;
        renderOccurrence();
      });
      open.addEventListener("click", () => {
        const occurrence = occurrences[occurrenceIndex];
        const documentId = document.getElementById("selected-document-id").value;
        app.classList.remove("pdf-hidden");
        const toggle = document.getElementById("toggle-pdf");
        toggle.textContent = "Hide PDF";
        toggle.setAttribute("aria-expanded", "true");
        openPreview(
          `/api/documents/${encodeURIComponent(documentId)}/source#page=${occurrence.page}`,
          `Source evidence · page ${occurrence.page}`,
        );
      });
      controls.append(previous, position, next, open);
      evidence.append(evidenceSummary, snippet, controls);
      renderOccurrence();
    }
    fields.append(evidence);
    if (color.method === "document_legend" && color.suggested_label) {
      const specification = document.createElement("p");
      specification.className = "color-evidence";
      specification.textContent =
        `Document legend mapping: ${color.hex} → ${color.suggested_label}.`;
      fields.append(specification);
    }
    record.append(swatch, fields);
    return record;
  }));
  renderDocumentColorCode();

  const status = document.getElementById("color-status");
  const confirmed = configuration.human_confirmed;
  setReadiness("colors", confirmed, "Resolve and confirm every observed color.");
  status.className = `notice ${confirmed ? "success" : "warning"}`;
  status.textContent = confirmed
    ? `Color configuration confirmed by ${configuration.confirmed_by}.`
    : `${configuration.colors.length} observed color${configuration.colors.length === 1 ? "" : "s"} require explicit human decisions. Suggestions are not approvals.`;
  document.getElementById("mapping-confirmed").disabled = !configuration.colors.length;
  document.getElementById("mapping-confirmed").checked = confirmed;
  document.getElementById("propose-colors").disabled =
    !result.automatic_proposal_available;
  document.getElementById("confirm-colors").disabled = !configuration.colors.length;
  document.getElementById("extract-annotations").disabled = false;
}

async function loadColors(documentId, discoverIfEmpty = true) {
  const status = document.getElementById("color-status");
  try {
    const response = await fetch(`/api/documents/${encodeURIComponent(documentId)}/colors`);
    const result = await response.json();
    if (!response.ok) {
      setReadiness("colors", false, "The color configuration could not be loaded.");
      status.className = "notice error";
      status.textContent = result.detail || "The color configuration could not be loaded.";
      return;
    }
    renderColorConfiguration(result);
    if (discoverIfEmpty && result.configuration.colors.length === 0) {
      await discoverColors();
      return;
    }
    await loadBatchCandidates(documentId, result.configuration.human_confirmed);
  } catch (error) {
    setReadiness("colors", false, "The color configuration could not be loaded.");
    status.className = "notice error";
    status.textContent = "The color configuration could not be loaded.";
  }
}

/** Extract raw document evidence and expose every observed hex for review. */
async function discoverColors() {
  const documentId = document.getElementById("selected-document-id").value;
  if (!documentId) return;
  const button = document.getElementById("discover-colors");
  const progress = document.getElementById("proposal-progress");
  const progressLabel = document.getElementById("color-progress-label");
  const status = document.getElementById("color-status");
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 120000);
  button.disabled = true;
  button.textContent = "Discovering…";
  progressLabel.textContent = "Reading highlighted colors from the document…";
  progress.hidden = false;
  status.className = "notice neutral";
  status.textContent = "Discovering highlighted colors and saving raw annotation evidence.";
  try {
    const response = await fetch(
      `/api/documents/${encodeURIComponent(documentId)}/colors/discover`,
      {method: "POST", signal: controller.signal},
    );
    const result = await response.json();
    if (!response.ok) {
      setReadiness("extracted", false, "Extract annotation evidence from this document.");
      status.className = "notice error";
      status.textContent = `${result.message || "Color discovery failed."} ${result.action || ""}`;
      return;
    }
    await loadColors(documentId, false);
    await loadExtractionStatus(documentId);
    status.className = "notice warning";
    status.textContent = `${result.color_count} observed color${result.color_count === 1 ? "" : "s"} found in ${result.sentence_count} extracted sentence${result.sentence_count === 1 ? "" : "s"}. Assign or confirm a HEVA label for every color.`;
  } catch (error) {
    status.className = "notice error";
    status.textContent = error.name === "AbortError"
      ? "Color discovery did not finish within two minutes. Check the source and try again."
      : "Color discovery could not contact the local extraction service.";
  } finally {
    window.clearTimeout(timeout);
    progress.hidden = true;
    button.disabled = false;
    button.textContent = "Discover colors";
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
    const eligibleCandidates = result.candidates.filter((candidate) => candidate.eligible);
    list.replaceChildren(...eligibleCandidates.map((candidate) => {
      const row = document.createElement("label");
      row.className = `batch-candidate ${candidate.eligible ? "" : "incompatible"}`;
      const input = document.createElement("input");
      input.type = "checkbox";
      input.value = candidate.document_id;
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
    const eligible = eligibleCandidates.length;
    status.className = `notice ${eligible ? "success" : "warning"}`;
    status.textContent = eligible
      ? `${eligible} document${eligible === 1 ? "" : "s"} have an exact palette match.`
      : "No other registered document has an eligible matching palette.";
    document.getElementById("batch-confirmed").checked = false;
    document.getElementById("batch-confirmed").closest("label").hidden = !eligible;
    document.getElementById("apply-batch-mapping").hidden = !eligible;
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
  document.getElementById("color-progress-label").textContent =
    "Asking local Ollama for optional label suggestions…";
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
  await loadExtractionStatus(documentId);
  refreshAnnotationsReview();
  if (result.canonical_annotations?.status === "failed") {
    status.className = "notice error";
    status.textContent = `The color configuration was confirmed, but canonical annotations could not be built. ${result.canonical_annotations.warnings.join(" ")}`;
  }
}

async function loadExtractionStatus(documentId) {
  const status = document.getElementById("extraction-status");
  const rebuild = document.getElementById("rebuild-annotations");
  try {
    const response = await fetch(
      `/api/documents/${encodeURIComponent(documentId)}/extraction`,
    );
    const result = await response.json();
    if (!response.ok) {
      setReadiness("extracted", false, "Extract annotation evidence from this document.");
      showAnnotationsWorkspace(documentId, false);
      status.className = "notice error";
      status.textContent = result.detail || "Extraction status could not be loaded.";
      return;
    }
    rebuild.hidden = result.state === "not_extracted";
    rebuild.disabled = document.getElementById("extract-annotations").disabled;
    if (result.state === "not_extracted") {
      status.className = result.draft_record_count ? "notice warning" : "notice neutral";
      status.textContent = result.draft_record_count
        ? `${result.draft_record_count} raw sentence record${result.draft_record_count === 1 ? " is" : "s are"} saved. Select a complete project color configuration to create canonical annotations.`
        : "No persisted extraction exists for this document.";
    } else if (result.state === "current") {
      status.className = result.warnings.length ? "notice warning" : "notice success";
      status.textContent = `Current checkpoint contains ${result.record_count} sentence record${result.record_count === 1 ? "" : "s"}.${result.warnings.length ? ` ${result.warnings.join(" ")}` : ""}`;
    } else {
      status.className = result.state === "invalid" ? "notice error" : "notice warning";
      status.textContent = `Persisted extraction contains ${result.record_count} record${result.record_count === 1 ? "" : "s"} but must be rebuilt. ${result.stale_reasons.join(" ")}`;
    }
    const canonicalReady = result.record_count > 0;
    const draftAvailable = result.draft_record_count > 0;
    const mappingConfirmed = document.getElementById("mapping-confirmed").checked;
    if (
      draftAvailable
      && !canonicalReady
      && mappingConfirmed
      && !automaticCompilationAttempts.has(documentId)
    ) {
      automaticCompilationAttempts.add(documentId);
      await compileAnnotations();
      return;
    }
    showAnnotationsWorkspace(
      documentId,
      canonicalReady,
      draftAvailable,
      mappingConfirmed,
    );
    setReadiness(
      "extracted",
      result.record_count > 0,
      "Extract annotation evidence from this document.",
    );
    await loadDocumentReadiness(documentId);
  } catch (error) {
    setReadiness("extracted", false, "Extraction status could not be loaded.");
    showAnnotationsWorkspace(documentId, false);
    status.className = "notice error";
    status.textContent = "Extraction status could not be loaded.";
  }
}

/** Compile persisted raw evidence after the researcher confirms its color semantics. */
async function compileAnnotations() {
  const documentId = document.getElementById("selected-document-id").value;
  const button = document.getElementById("compile-annotations");
  const status = document.getElementById("extraction-status");
  button.disabled = true;
  button.textContent = "Building…";
  status.className = "notice neutral";
  status.textContent = "Building canonical annotations from the saved raw evidence…";
  try {
    const response = await fetch(
      `/api/documents/${encodeURIComponent(documentId)}/annotations/compile`,
      {method: "POST"},
    );
    const result = await response.json();
    if (!response.ok) {
      status.className = "notice error";
      status.textContent = `${result.message || "Canonical annotations were not created."} ${result.action || ""}`;
      return;
    }
    status.className = result.warnings.length ? "notice warning" : "notice success";
    status.textContent = `Created ${result.record_count} canonical annotation record${result.record_count === 1 ? "" : "s"}.`;
    await loadExtractionStatus(documentId);
    refreshAnnotationsReview();
  } catch (error) {
    status.className = "notice error";
    status.textContent = "Canonical annotations could not be created. The saved raw evidence was preserved.";
  } finally {
    button.disabled = false;
    button.textContent = "Build canonical annotations";
  }
}

function wait(milliseconds) {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

/** Poll the background extraction job and render its current, non-invented stage. */
async function waitForExtraction(documentId) {
  const progress = document.getElementById("extraction-progress");
  const progressBar = document.getElementById("extraction-progress-bar");
  const progressMessage = document.getElementById("extraction-progress-message");
  const cancelButton = document.getElementById("cancel-extraction");
  const status = document.getElementById("extraction-status");
  const deadline = Date.now() + 10 * 60 * 1000;
  while (Date.now() < deadline) {
    const response = await fetch(
      `/api/documents/${encodeURIComponent(documentId)}/extraction/progress`,
    );
    const job = await response.json();
    if (!response.ok) throw new Error(job.detail || "Extraction progress could not be loaded.");
    cancelButton.hidden = !["queued", "extracting"].includes(job.stage);
    if (job.stage === "extracting" && job.total_pages) {
      progressBar.max = job.total_pages;
      progressBar.value = job.completed_pages;
      progressMessage.textContent = `${job.message} Extracted ${job.completed_pages} of ${job.total_pages} source pages.`;
    } else {
      progressBar.max = job.total_steps;
      progressBar.value = job.completed_steps;
      progressMessage.textContent = `${job.message} Stage ${Math.min(job.completed_steps + 1, job.total_steps)} of ${job.total_steps}.`;
    }
    status.className = "notice neutral";
    status.textContent = job.message;
    if (["completed", "draft_saved", "failed", "cancelled"].includes(job.state)) return job;
    await wait(750);
  }
  throw new Error("Extraction is still running after ten minutes. Its work was not cancelled; reopen this document to check its status.");
}

async function extractAnnotations(force = false) {
  const documentId = document.getElementById("selected-document-id").value;
  const button = document.getElementById(
    force ? "rebuild-annotations" : "extract-annotations",
  );
  const progress = document.getElementById("extraction-progress");
  const status = document.getElementById("extraction-status");
  const cancelButton = document.getElementById("cancel-extraction");
  const pageStart = document.getElementById("extraction-page-start").value.trim();
  const pageEnd = document.getElementById("extraction-page-end").value.trim();
  if ((pageStart && !pageEnd) || (!pageStart && pageEnd)) {
    status.className = "notice error";
    status.textContent = "Provide both the first and last PDF page, or leave both blank.";
    return;
  }
  const scope = pageStart && pageEnd
    ? `&page_start=${encodeURIComponent(pageStart)}&page_end=${encodeURIComponent(pageEnd)}`
    : "";
  button.disabled = true;
  button.textContent = force ? "Rebuilding…" : "Extracting…";
  progress.hidden = false;
  cancelButton.hidden = false;
  cancelButton.disabled = false;
  cancelButton.textContent = "Cancel extraction";
  status.className = "notice neutral";
  status.textContent = "Extraction is running. Keep this page open.";
  try {
    const response = await fetch(
      `/api/documents/${encodeURIComponent(documentId)}/extract?force=${force}${scope}`,
      { method: "POST" },
    );
    const result = await response.json();
    if (!response.ok) {
      status.className = "notice error";
      status.textContent = `${result.message || "Extraction failed."} ${result.action || ""}`;
      return;
    }
    const job = await waitForExtraction(documentId);
    if (job.state === "cancelled") {
      status.className = "notice warning";
      status.textContent = job.message;
      return;
    }
    if (job.state === "failed") {
      status.className = "notice error";
      status.textContent = `${job.message} ${job.error?.action || ""}`;
      return;
    }
    if (job.state === "draft_saved") {
      status.className = "notice warning";
      status.textContent = job.message;
      await loadColors(documentId);
      await loadExtractionStatus(documentId);
      return;
    }
    const extraction = job.result;
    status.className = extraction.warnings.length ? "notice warning" : "notice success";
    status.textContent = `${extraction.reused_checkpoint ? "Reused" : "Created"} ${extraction.record_count} extracted sentence records.${extraction.warnings.length ? ` ${extraction.warnings.join(" ")}` : ""}`;
    await loadExtractionStatus(documentId);
  } catch (error) {
    status.className = "notice error";
    status.textContent = error.message || "Extraction could not be completed. Check the local service and try again.";
  } finally {
    progress.hidden = true;
    cancelButton.hidden = true;
    button.textContent = force ? "Rebuild extraction" : "Extract annotations";
    button.disabled = false;
  }
}

async function cancelExtraction() {
  const documentId = document.getElementById("selected-document-id").value;
  const button = document.getElementById("cancel-extraction");
  button.disabled = true;
  button.textContent = "Cancelling…";
  try {
    const response = await fetch(
      `/api/documents/${encodeURIComponent(documentId)}/extraction/cancel`,
      {method: "POST"},
    );
    const result = await response.json();
    if (!response.ok) throw new Error(result.message || "Extraction is not running.");
    document.getElementById("extraction-status").textContent = result.message;
  } catch (error) {
    document.getElementById("extraction-status").textContent = error.message;
  }
}

async function loadSelectedDocument() {
  const parameters = new URLSearchParams(window.location.search);
  const documentId = parameters.get("document_id");
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
    await loadDocumentAnnotators(documentId);
    await loadCitation(documentId);
    await loadColors(documentId);
    await loadExtractionStatus(documentId);
    const requestedSection = parameters.get("section");
    if (requestedSection === "citation") showStep(2);
    if (requestedSection === "colors") showStep(3);
    if (requestedSection === "annotations") showStep(4);
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

async function chooseExternalSource() {
  const selected = document.getElementById("selected-files");
  selected.textContent = "Waiting for you to choose a file…";
  const response = await fetch("/api/files/select-source", {method: "POST"});
  const result = await response.json();
  if (!response.ok) {
    selected.textContent = result.detail || "The source could not be registered.";
    return;
  }
  if (!result.selected) {
    selected.textContent = "No file was selected.";
    return;
  }
  window.location.assign(`/create?document_id=${encodeURIComponent(result.document_id)}`);
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
document.getElementById("discover-colors").addEventListener("click", discoverColors);
document.getElementById("confirm-colors").addEventListener("click", confirmColors);
document.getElementById("choose-external-source").addEventListener("click", chooseExternalSource);
document.getElementById("batch-confirmed").addEventListener("change", updateBatchAction);
document.getElementById("apply-batch-mapping").addEventListener(
  "click",
  applyBatchMapping,
);
document.getElementById("extract-annotations").addEventListener(
  "click",
  () => extractAnnotations(false),
);
document.getElementById("rebuild-annotations").addEventListener(
  "click",
  () => extractAnnotations(true),
);
document.getElementById("cancel-extraction").addEventListener(
  "click",
  cancelExtraction,
);
document.getElementById("compile-annotations").addEventListener(
  "click",
  compileAnnotations,
);

document.querySelectorAll("[name='processing-mode']").forEach((radio) => radio.addEventListener("change", () => {
  const batch = document.querySelector("[name='processing-mode']:checked").value === "batch";
  document.getElementById("source-help").textContent = batch
    ? "Choose and register external files one at a time; batch extraction can run after registration."
    : "The source may remain outside this dataset repository. HEVA stores only a local binding and does not copy it.";
}));
restoreAnnotator();
loadReferenceColorCode();
loadSelectedDocument();
