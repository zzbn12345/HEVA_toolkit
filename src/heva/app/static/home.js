/** Redirect an already-open project to its document review queue. */
async function restoreProject() {
  const state = document.getElementById("project-state");
  try {
    const response = await fetch("/api/project");
    if (response.ok) {
      window.location.assign("/review");
      return;
    }
    state.textContent = "No project open";
  } catch (error) {
    state.textContent = "The local HEVA service is unavailable";
  }
}

/**
 * Select a local folder and open or create its HEVA project.
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
      throw new Error(result.detail || "The project could not be selected.");
    }
    window.location.assign("/review");
  } catch (error) {
    message.className = "notice error";
    message.textContent = error.message || "The local HEVA service could not select this project.";
  } finally {
    button.disabled = false;
  }
}

document.querySelectorAll("[data-select-project]").forEach((button) => {
  button.addEventListener("click", () => {
    selectProject(button.dataset.selectProject, button);
  });
});

restoreProject();
