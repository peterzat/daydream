"use strict";

// The front door (SPEC 2026-09-27 criteria 2 and 8): sign in, or redeem an
// invitation. Every URL is relative to the page's <base href>, like main.js.
(function () {
  const invite = location.pathname.match(/\/invite\/([^/?#]+)\/?$/);
  // This instance's words, filled in by the server (docs/INSTANCES.md).
  const place = document.body.dataset.place || "the village";
  const Place = document.body.dataset.placeCapital || "The village";

  async function post(path, data) {
    let r;
    try {
      r = await fetch(path, {
        method: "POST",
        credentials: "same-origin",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(data),
      });
    } catch (e) {
      return { ok: false, status: 0, body: { error: `${place} can't be reached just now` } };
    }
    let body = {};
    try { body = await r.json(); } catch (e) { body = {}; }
    return { ok: r.ok, status: r.status, body };
  }

  function say(form, message) {
    const p = form.querySelector(".door-error");
    p.textContent = message || "";
    p.hidden = !message;
  }

  function enter() {
    location.replace(document.baseURI);
  }

  function busy(form, on) {
    form.querySelectorAll("button, input").forEach((el) => { el.disabled = on; });
  }

  // ---- sign in ----
  const login = document.getElementById("login-form");
  login.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    say(login, "");
    const f = new FormData(login); // before busy(): FormData skips disabled inputs
    busy(login, true);
    const r = await post("api/login", { username: f.get("username"), password: f.get("password") });
    busy(login, false);
    if (r.ok) return enter();
    say(login, r.body.error || "that didn't work");
  });

  if (!invite) return;

  // ---- an invitation ----
  const slug = decodeURIComponent(invite[1]);
  document.getElementById("door-login").hidden = true;
  document.getElementById("door-invite").hidden = false;
  const greeting = document.getElementById("invite-greeting");
  const form = document.getElementById("invite-form");
  const note = document.getElementById("invite-note");

  (async () => {
    const r = await post("api/invite/peek", { slug });
    if (!r.ok) {
      greeting.textContent = r.body.error || "that invitation can't be used";
      document.getElementById("door-login").hidden = false;
      return;
    }
    const first = (r.body.for || "").split(/\s+/)[0] || "friend";
    const who = r.body.operator || "the person who invited you";
    if (r.body.kind === "reset") {
      greeting.textContent = `Welcome back, ${first}. Choose a new password.`;
      document.getElementById("invite-username-field").hidden = true;
      document.getElementById("invite-button").textContent = "set password";
    } else {
      greeting.textContent = `Welcome, ${first}. A place in ${place} has been kept for you.`;
      // Plainly, and warmly (SPEC 2026-09-27 criterion 8; reworded after the
      // operator's first evening read the old line as a little creepy).
      note.textContent = `${Place} remembers what you say and do here, so its people `
        + `can come to know you, and the other dreamers can see when you were last `
        + `here and where. From time to time, ${who} reads over a summary `
        + "of its days and writes what happens next.";
      note.hidden = false;
    }
    form.hidden = false;
  })();

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    say(form, "");
    const f = new FormData(form); // before busy(): FormData skips disabled inputs
    busy(form, true);
    const r = await post("api/invite/redeem", {
      slug, username: (f.get("username") || "").trim().toLowerCase(), password: f.get("password"),
    });
    busy(form, false);
    if (r.ok) return enter();
    say(form, r.body.error || "that didn't work");
  });
})();
