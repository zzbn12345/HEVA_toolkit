const form = document.getElementById("annotator-form");
const status = document.getElementById("annotator-status");
const fields = {
  name: document.getElementById("annotator-name"),
  affiliation: document.getElementById("annotator-affiliation"),
  email: document.getElementById("annotator-email"),
  orcid: document.getElementById("annotator-orcid"),
};

function showStatus(kind, message) {
  status.className = `notice ${kind}`;
  status.textContent = message;
}

async function loadAnnotator() {
  try {
    const response = await fetch("/api/annotator");
    const result = await response.json();
    if (!response.ok) {
      showStatus("error", `${result.message} ${result.action}`);
      return;
    }
    Object.entries(fields).forEach(([key, input]) => {
      input.value = result.annotator[key] || "";
    });
    showStatus(
      result.configured ? "success" : "warning",
      result.configured
        ? `Active project annotator: ${result.annotator.name}`
        : `${result.message} ${result.action}`,
    );
  } catch (error) {
    showStatus("error", "The annotator profile could not be loaded. Reload this page.");
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!form.reportValidity()) return;
  const payload = Object.fromEntries(
    Object.entries(fields).map(([key, input]) => [key, input.value.trim() || null]),
  );
  try {
    const response = await fetch("/api/annotator", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const result = await response.json();
    if (!response.ok) {
      const detail = result.detail || result;
      showStatus("error", `${detail.message} ${detail.action}`);
      return;
    }
    showStatus("success", `Saved. ${result.annotator.name} is the active project annotator.`);
  } catch (error) {
    showStatus("error", "The annotator profile could not be saved. Try again.");
  }
});

loadAnnotator();
