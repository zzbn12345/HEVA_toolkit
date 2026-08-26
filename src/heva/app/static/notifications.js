/** Shared, accessible feedback for consequential HEVA application events. */
(function initializeNotifications() {
  const durations = {info: 6000, success: 6000, warning: 10000, error: null};
  const timers = new Map();

  function container() {
    let notifications = document.getElementById("heva-notifications");
    if (notifications) return notifications;
    notifications = document.createElement("section");
    notifications.id = "heva-notifications";
    notifications.className = "heva-notifications";
    notifications.setAttribute("aria-label", "Application notifications");
    document.body.appendChild(notifications);
    return notifications;
  }

  function dismiss(id) {
    window.clearTimeout(timers.get(id));
    timers.delete(id);
    const item = document.querySelector(`[data-notification-id="${CSS.escape(id)}"]`);
    if (!item) return;
    item.classList.add("notification-leaving");
    window.setTimeout(() => item.remove(), 180);
  }

  function schedule(item, id, duration) {
    window.clearTimeout(timers.get(id));
    timers.delete(id);
    if (duration == null) return;
    const start = () => {
      window.clearTimeout(timers.get(id));
      timers.set(id, window.setTimeout(() => dismiss(id), duration));
    };
    item.onmouseenter = () => window.clearTimeout(timers.get(id));
    item.onmouseleave = start;
    item.onfocusin = () => window.clearTimeout(timers.get(id));
    item.onfocusout = start;
    start();
  }

  function notify({id, type = "info", title, message = "", duration, action = null}) {
    const notificationId = id || `event-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    let item = document.querySelector(
      `[data-notification-id="${CSS.escape(notificationId)}"]`,
    );
    if (!item) {
      item = document.createElement("article");
      item.dataset.notificationId = notificationId;
      container().appendChild(item);
    }
    item.className = `heva-notification notification-${type}`;
    item.setAttribute("role", type === "error" ? "alert" : "status");
    item.setAttribute("aria-live", type === "error" ? "assertive" : "polite");
    const content = document.createElement("div");
    const heading = document.createElement("strong");
    heading.textContent = title;
    content.appendChild(heading);
    if (message) {
      const detail = document.createElement("p");
      detail.textContent = message;
      content.appendChild(detail);
    }
    if (action?.href && action?.label) {
      const link = document.createElement("a");
      link.className = "notification-action";
      link.href = action.href;
      link.textContent = action.label;
      content.appendChild(link);
    }
    const close = document.createElement("button");
    close.className = "notification-dismiss";
    close.type = "button";
    close.setAttribute("aria-label", `Dismiss ${title}`);
    close.textContent = "×";
    close.addEventListener("click", () => dismiss(notificationId));
    item.replaceChildren(content, close);
    schedule(item, notificationId, duration === undefined ? durations[type] : duration);
    return notificationId;
  }

  window.hevaNotifications = {notify, dismiss};
  if (document.body) container();
  else document.addEventListener("DOMContentLoaded", container, {once: true});
}());
