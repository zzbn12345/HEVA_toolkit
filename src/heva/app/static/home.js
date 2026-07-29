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
    lead.textContent = "Manage only the documents, annotators, packages, and validation state belonging to the active project.";
    state.textContent = `${result.summary.total} registered document${result.summary.total === 1 ? "" : "s"}`;
    document.getElementById("active-project-name").textContent =
      result.project_root.split("/").filter(Boolean).at(-1) || result.project_root;
    document.getElementById("active-project-path").textContent = result.project_root;
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

async function selectProject(event, operation) {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector("button");
  const message = document.getElementById("project-message");
  const path = new FormData(form).get("path").trim();
  button.disabled = true;
  message.className = "notice neutral";
  message.textContent = operation === "create"
    ? "Creating the project and registering source documents…"
    : "Opening the project…";
  try {
    const response = await fetch(`/api/projects/${operation}`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({path}),
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
    message.textContent = "The local HEVA service could not select this project.";
  } finally {
    button.disabled = false;
  }
}

document.getElementById("open-project-form").addEventListener(
  "submit",
  (event) => selectProject(event, "open"),
);
document.getElementById("create-project-form").addEventListener(
  "submit",
  (event) => selectProject(event, "create"),
);
document.getElementById("close-project").addEventListener("click", async () => {
  await fetch("/api/projects/close", {method: "POST"});
  await loadProject();
});
loadProject();
