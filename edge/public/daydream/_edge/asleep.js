"use strict";
// The asleep page's two small jobs: say how long the village has slept, and
// come back to life by itself when it wakes (edge/status turns "awake").
(function () {
  const since = document.querySelector("[data-since]");
  const iso = since && since.dataset.since;
  if (iso) {
    const then = new Date(iso);
    if (!isNaN(then)) {
      const days = Math.floor((Date.now() - then.getTime()) / 86400000);
      const when = then.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" });
      since.textContent = days < 1 ? "It fell asleep earlier today."
        : `It has been asleep since ${when}.`;
    }
  }
  const note = document.querySelector("[data-note]");
  if (note && !note.dataset.note) note.hidden = true;
  const status = new URL("edge/status", document.querySelector('link[rel="stylesheet"]').href
    .replace(/_edge\/asleep\.css.*$/, ""));
  setInterval(async () => {
    try {
      const r = await fetch(status, { cache: "no-store" });
      const s = await r.json();
      if (s.state === "awake") location.reload();
    } catch (_) {}
  }, 60000);
})();
