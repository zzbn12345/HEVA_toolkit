async function loadProject() {
  const state = document.getElementById("project-state");
  const summary = document.getElementById("summary");
  const counts = document.getElementById("summary-counts");
  try {
    const response = await fetch("/api/project");
    const result = await response.json();
    if (!response.ok) {
      state.textContent = `${result.message} ${result.action}`;
      return;
    }
    state.textContent = `${result.summary.total} registered document${result.summary.total === 1 ? "" : "s"}`;
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
    summary.hidden = false;
  } catch (error) {
    state.textContent = "The local HEVA service is not responding. Reload this page.";
  }
}

loadProject();
