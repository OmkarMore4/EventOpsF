// Admin dashboard "live" updates via lightweight polling (not WebSockets —
// see routes/admin.py's dashboard_live() for why: this way it behaves the
// same on Render and on Vercel's serverless functions).
(function () {
  var POLL_INTERVAL_MS = 8000;
  var pollTimer = null;

  function escapeHtml(value) {
    var div = document.createElement("div");
    div.textContent = value == null ? "" : String(value);
    return div.innerHTML;
  }

  function methodTag(method) {
    if (method === "manual") return " <span class=\"text-ink/40\">(manual)</span>";
    if (method === "qr") return " <span class=\"text-ink/40\">(QR)</span>";
    return "";
  }

  function renderActivity(items) {
    var feed = document.getElementById("live-activity-feed");
    if (!feed) return;
    if (!items.length) {
      feed.innerHTML = '<p class="text-sm text-ink/40 py-4 text-center">No check-ins yet today.</p>';
      return;
    }
    feed.innerHTML = items.map(function (item) {
      return (
        '<li class="flex items-center justify-between py-2.5 border-b border-ink/6 last:border-0">' +
        '<span class="text-sm text-ink">' + escapeHtml(item.volunteer_name) + " &mdash; " + escapeHtml(item.action) + methodTag(item.method) + "</span>" +
        '<span class="text-xs text-ink/40 coord-text flex-shrink-0 ml-3">' + escapeHtml(item.time_label) + "</span>" +
        "</li>"
      );
    }).join("");
  }

  function applyUpdate(data) {
    var presentEl = document.getElementById("live-present-count");
    var barEl = document.getElementById("live-present-bar");
    var pendingEl = document.getElementById("live-pending-tasks");
    var issuesEl = document.getElementById("live-open-issues");
    var updatedEl = document.getElementById("live-updated-at");

    if (presentEl) presentEl.textContent = data.present_today;
    if (barEl) {
      var pct = data.total_volunteers ? Math.round((data.present_today / data.total_volunteers) * 100) : 0;
      barEl.style.width = pct + "%";
    }
    if (pendingEl) pendingEl.textContent = data.pending_tasks;
    if (issuesEl) issuesEl.textContent = data.open_issues;
    if (updatedEl) updatedEl.textContent = "Updated " + data.updated_at;

    renderActivity(data.recent_activity || []);
  }

  function poll(url) {
    fetch(url, { headers: { "X-Requested-With": "fetch" } })
      .then(function (res) { return res.ok ? res.json() : null; })
      .then(function (data) { if (data) applyUpdate(data); })
      .catch(function () { /* transient network hiccup -- just try again next interval */ });
  }

  document.addEventListener("DOMContentLoaded", function () {
    var root = document.getElementById("live-dashboard-root");
    if (!root) return;
    var url = root.dataset.liveUrl;
    if (!url) return;

    function start() {
      if (pollTimer) return;
      poll(url);
      pollTimer = setInterval(function () { poll(url); }, POLL_INTERVAL_MS);
    }
    function stop() {
      if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
    }

    start();
    document.addEventListener("visibilitychange", function () {
      if (document.hidden) stop(); else start();
    });
  });
})();
