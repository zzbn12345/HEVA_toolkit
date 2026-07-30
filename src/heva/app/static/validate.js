const button = document.getElementById("validate-project");
const downloadButton = document.getElementById("download-validation");
const statusBox = document.getElementById("validation-status");
const summaryBox = document.getElementById("validation-summary");
const results = document.getElementById("validation-results");
let currentReport = null;
let currentFilter = "all";

/**
 * Create a text-only element so validation evidence cannot inject markup.
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
 * Return documents matching a visual filter without changing report evidence.
 * @param {object} report
 * @returns {Array<object>}
 */
function filteredDocuments(report) {
  const documents = report.documents || [];
  if (currentFilter === "issues") {
    return documents.filter((documentReport) => !documentReport.valid);
  }
  if (currentFilter === "completed") {
    return documents.filter((documentReport) => documentReport.completed);
  }
  if (currentFilter === "incomplete") {
    return documents.filter((documentReport) => !documentReport.completed);
  }
  return documents;
}

/**
 * Render pytest-style aggregate counts while keeping validity and completion separate.
 * @param {object} report
 */
function showSummary(report) {
  const summary = report.summary;
  const values = [
    ["Documents", summary.documents],
    ["Passed", summary.passed],
    ["Failed", summary.failed],
    ["Completed", summary.completed],
    ["Not completed", summary.not_completed],
    ["Errors", summary.errors],
    ["Warnings", summary.warnings],
  ];
  summaryBox.replaceChildren(
    ...values.map(([label, value]) => {
      const item = document.createElement("div");
      item.className = "validation-stat";
      item.append(
        textElement("strong", "", String(value)),
        textElement("span", "", label),
      );
      return item;
    }),
  );
}

/**
 * Render one stable issue with its location, corrective action, and relevant guide.
 * @param {object} issue
 * @returns {HTMLLIElement}
 */
function issueElement(issue) {
  const item = document.createElement("li");
  item.className = `validation-issue issue-${issue.severity}`;
  const guide = textElement("a", "issue-guide", "Read the relevant guide");
  guide.href = `/guide/${issue.guide.split("/").map(encodeURIComponent).join("/")}`;
  item.append(
    textElement("span", "issue-code", `${issue.severity.toUpperCase()} · ${issue.code}`),
    textElement("code", "issue-path", issue.path),
    textElement("div", "issue-message", issue.message),
    textElement("span", "issue-action", `Fix: ${issue.action}`),
    guide,
  );
  return item;
}

/**
 * Render the currently filtered document-by-document report.
 * @param {object} report
 */
function showReport(report) {
  const documents = filteredDocuments(report);
  if (!documents.length) {
    results.replaceChildren(
      textElement("p", "notice neutral", "No documents match this report filter."),
    );
    return;
  }
  results.replaceChildren(
    ...documents.map((documentReport) => {
      const card = document.createElement("article");
      card.className = `document-result ${documentReport.valid ? "passed" : "failed"}`;
      const heading = document.createElement("div");
      heading.className = "validation-document-heading";
      const identity = document.createElement("div");
      identity.append(
        textElement("h2", "", documentReport.source_path),
        textElement("small", "", documentReport.document_id),
      );
      const badges = document.createElement("div");
      badges.className = "validation-badges";
      badges.append(
        textElement(
          "span",
          `validation-badge ${documentReport.valid ? "passed" : "failed"}`,
          documentReport.valid ? "Passed" : "Needs attention",
        ),
        textElement(
          "span",
          `validation-badge ${documentReport.completed ? "completed" : "incomplete"}`,
          documentReport.completed ? "Completed" : "Not completed",
        ),
        textElement(
          "span",
          "validation-badge workflow",
          documentReport.workflow_status.replace("_", " "),
        ),
      );
      heading.append(identity, badges);
      card.appendChild(heading);
      if (!documentReport.issues.length) {
        card.appendChild(
          textElement("p", "notice success", "All current HEVA validation layers passed."),
        );
      } else {
        const details = document.createElement("details");
        const issueSummary = document.createElement("summary");
        const errorCount = documentReport.issues.filter(
          (issue) => issue.severity === "error",
        ).length;
        const warningCount = documentReport.issues.length - errorCount;
        issueSummary.textContent =
          `${errorCount} error${errorCount === 1 ? "" : "s"}` +
          `${warningCount ? `, ${warningCount} warning${warningCount === 1 ? "" : "s"}` : ""}`;
        const list = document.createElement("ul");
        list.className = "validation-issues";
        list.append(...documentReport.issues.map(issueElement));
        details.append(issueSummary, list);
        card.appendChild(details);
      }
      const actions = document.createElement("div");
      actions.className = "validation-actions";
      const edit = textElement("a", "button secondary", "Open document");
      edit.href = `/review/${encodeURIComponent(documentReport.document_id)}`;
      actions.appendChild(edit);
      card.appendChild(actions);
      return card;
    }),
  );
}

/** Run the complete read-only package check and display its report. */
async function runValidation() {
  button.disabled = true;
  downloadButton.disabled = true;
  statusBox.className = "notice neutral";
  statusBox.textContent = "Running all HEVA checks…";
  summaryBox.replaceChildren();
  results.replaceChildren();
  try {
    const response = await fetch("/api/validate", {method: "POST"});
    const report = await response.json();
    if (!response.ok || !report.documents || !report.summary) {
      throw new Error(
        `${report.message || "Validation could not run."} ${report.action || ""}`.trim(),
      );
    }
    currentReport = report;
    showSummary(report);
    showReport(report);
    downloadButton.disabled = false;
    statusBox.className = report.valid ? "notice success" : "notice error";
    statusBox.textContent = report.valid
      ? "Check completed: every document passed the current HEVA specification."
      : "Check completed: review the failed documents and corrective actions below.";
  } catch (error) {
    currentReport = null;
    statusBox.className = "notice error";
    statusBox.textContent = error.message;
  } finally {
    button.disabled = false;
  }
}

/** Download exactly the report displayed by the completed GUI check. */
function downloadReport() {
  if (!currentReport) {
    return;
  }
  const blob = new Blob(
    [`${JSON.stringify(currentReport, null, 2)}\n`],
    {type: "application/json"},
  );
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = "heva-validation-report.json";
  link.click();
  URL.revokeObjectURL(link.href);
}

document.querySelectorAll("[data-validation-filter]").forEach((filterButton) => {
  filterButton.addEventListener("click", () => {
    currentFilter = filterButton.dataset.validationFilter;
    document.querySelectorAll("[data-validation-filter]").forEach((item) => {
      item.classList.toggle("active", item === filterButton);
    });
    if (currentReport) {
      showReport(currentReport);
    }
  });
});

button.addEventListener("click", runValidation);
downloadButton.addEventListener("click", downloadReport);
