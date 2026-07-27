const button = document.getElementById("validate-project");
const statusBox = document.getElementById("validation-status");
const results = document.getElementById("validation-results");

function showReport(report) {
  results.replaceChildren();
  for (const documentReport of report.documents || []) {
    const card = document.createElement("article");
    card.className = "document-result";
    const heading = document.createElement("h2");
    heading.textContent = `${documentReport.document_id} · ${documentReport.valid ? "valid" : "needs attention"}`;
    card.appendChild(heading);
    if (!documentReport.issues.length) {
      const message = document.createElement("p");
      message.textContent = "All validation levels passed.";
      card.appendChild(message);
    } else {
      const list = document.createElement("ul");
      for (const issue of documentReport.issues) {
        const item = document.createElement("li");
        const code = document.createElement("span");
        code.className = "issue-code";
        code.textContent = `${issue.severity.toUpperCase()} · ${issue.code}`;
        const message = document.createElement("div");
        message.textContent = issue.message;
        const action = document.createElement("span");
        action.className = "issue-action";
        action.textContent = `Next step: ${issue.action}`;
        item.append(code, message, action);
        list.appendChild(item);
      }
      card.appendChild(list);
    }
    results.appendChild(card);
  }
}

button.addEventListener("click", async () => {
  button.disabled = true;
  statusBox.className = "notice neutral";
  statusBox.textContent = "Checking the project…";
  results.replaceChildren();
  try {
    const response = await fetch("/api/validate", { method: "POST" });
    const report = await response.json();
    if (report.documents) {
      showReport(report);
      statusBox.className = report.valid ? "notice success" : "notice error";
      statusBox.textContent = report.valid
        ? "The project passed every current HEVA validation level."
        : "The project needs attention before it can be approved.";
    } else {
      statusBox.className = "notice error";
      statusBox.textContent = `${report.message} ${report.action}`;
    }
  } catch (error) {
    statusBox.className = "notice error";
    statusBox.textContent = "Validation could not run. Check that the local HEVA service is running.";
  } finally {
    button.disabled = false;
  }
});
