async function loadProject() {
  const state = document.getElementById("project-state");
  const chooser = document.getElementById("project-chooser");
  const activeProject = document.getElementById("active-project");
  const counts = document.getElementById("summary-counts");
  const title = document.getElementById("home-title");
  const lead = document.getElementById("home-lead");
  try {
    const response = await fetch("/api/project");
    const result = await response.json();
    if (!response.ok) {
      chooser.hidden = false;
      activeProject.hidden = true;
      state.textContent = "No project open";
      title.textContent = "Open your heritage annotation project.";
      lead.textContent = "Like opening a working file in a desktop application, HEVA shows documents only after you choose the project they belong to.";
      return;
    }
    chooser.hidden = true;
    activeProject.hidden = false;
    title.textContent = "HEVA project workspace";
    lead.textContent = "Manage only the documents, annotators, analytical data, and validation state belonging to the active project.";
    state.textContent = `${result.summary.total} registered document${result.summary.total === 1 ? "" : "s"}`;
    document.getElementById("active-project-name").textContent = result.project_name;
    const fields = [
      ["Backlog", result.summary.backlog],
      ["In progress", result.summary.in_progress],
      ["In review", result.summary.in_review],
      ["Approved", result.summary.done],
    ];
    counts.replaceChildren(...fields.map(([label, value]) => {
      const item = document.createElement("div");
      const number = document.createElement("strong");
      number.textContent = value;
      item.append(number, label);
      return item;
    }));
  } catch (error) {
    state.textContent = "The local HEVA service is not responding. Reload this page.";
  }
}

/**
 * Ask the local service to show the system folder chooser, then open or create.
 * No selected files are uploaded to the browser or copied by HEVA.
 * @param {"open"|"create"} operation
 * @param {HTMLButtonElement} button
 */
async function selectProject(operation, button) {
  const message = document.getElementById("project-message");
  button.disabled = true;
  message.className = "notice neutral";
  message.textContent = "Waiting for you to choose a folder…";
  try {
    const pickerResponse = await fetch("/api/folders/select", {method: "POST"});
    const selection = await pickerResponse.json();
    if (!pickerResponse.ok) {
      throw new Error(selection.detail || "The folder chooser is not available.");
    }
    if (!selection.selected) {
      message.textContent = "No folder was selected.";
      return;
    }
    message.textContent = operation === "create"
      ? "Creating the project and registering source documents…"
      : "Opening the project…";
    const response = await fetch(`/api/projects/${operation}`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({path: selection.path}),
    });
    const result = await response.json();
    if (!response.ok) {
      message.className = "notice error";
      message.textContent = result.detail || "The project could not be selected.";
      return;
    }
    await loadProject();
  } catch (error) {
    message.className = "notice error";
    message.textContent = error.message || "The local HEVA service could not select this project.";
  } finally {
    button.disabled = false;
  }
}

document.querySelectorAll("[data-select-project]").forEach((button) => {
  button.addEventListener("click", () => selectProject(button.dataset.selectProject, button));
});
document.getElementById("close-project").addEventListener("click", async () => {
  await fetch("/api/projects/close", {method: "POST"});
  await loadProject();
});
loadProject();
