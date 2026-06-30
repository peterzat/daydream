"use strict";

const wsUrl =
  (location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws";
const PLACEHOLDER_BG = "/assets/placeholder-meadow.png";
let ws = null;
let lastSeq = 0;
let actorNames = {};
let awaitingPick = false; // showing the picker after leaving; suppresses auto-reconnect
let entities = []; // in-scope {alias, object_id, kind} for narration linking
let stagedVerb = null; // the verb-bar verb awaiting an object click

function connect(isReconnect) {
  // A fresh page load omits `since` and starts with an empty log; a reconnect
  // resumes from the last event the client rendered.
  const url = isReconnect ? wsUrl + "?since=" + lastSeq : wsUrl;
  ws = new WebSocket(url);
  ws.onopen = () => systemLine("(connected)");
  ws.onclose = () => {
    if (awaitingPick) return; // left the dream: wait for a toon pick
    systemLine("(disconnected; reconnecting in a moment)");
    setTimeout(() => connect(true), 1500);
  };
  ws.onerror = () => systemLine("(connection error)");
  ws.onmessage = (msg) => {
    const data = JSON.parse(msg.data);
    if (data.kind === "state_snapshot") renderSnapshot(data);
    else if (data.kind === "event") renderEvent(data.event);
    else if (data.kind === "needs_toon") enterPicker();
  };
}

function renderSnapshot(snap) {
  document.getElementById("room-title").textContent =
    snap.room ? snap.room.title : "drifting...";
  document.getElementById("room-desc").textContent =
    snap.room && snap.room.description ? snap.room.description : "";
  setRoomBackground(snap.room);
  // In-scope object mentions become clickable in narration.
  entities = (snap.entities || []).slice().sort(
    (a, b) => (b.alias || "").length - (a.alias || "").length
  );
  clearStagedVerb();
  // Map actor IDs to display names so 'say' events can name the speaker.
  actorNames = {};
  // Toons present: clickable, carrying object id + kind + mood.
  const toons = document.getElementById("toons");
  toons.innerHTML = "";
  for (const t of snap.toons) {
    actorNames[t.id] = t.name;
    toons.appendChild(objectChip(t, `${t.name} (${t.mood})`));
  }
  // Things on the ground here (previously sent but never rendered).
  renderObjects("things", snap.items || []);
  // The player's carried inventory.
  renderObjects("inventory", snap.inventory || []);
  // Re-hydrate the chat from the snapshot's recent events.
  const chat = document.getElementById("chat");
  chat.innerHTML = "";
  lastSeq = 0; // allow snapshot replays to render
  for (const e of snap.events) renderEvent(e);
  lastSeq = snap.last_seq;
  // Verb bar: Examine / Take / Drop / Talk. Click a verb to stage it, then
  // click an object; clicking an object with no staged verb defaults to
  // Examine. There is deliberately no generic "go" control here — the
  // per-direction exit buttons are the only nav affordance.
  const verbBar = document.getElementById("verb-bar");
  verbBar.innerHTML = "";
  for (const v of snap.verb_bar || []) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = v.ui_hint;
    btn.dataset.verb = v.name;
    btn.onclick = () => toggleStagedVerb(v.name, btn);
    verbBar.appendChild(btn);
  }
  // Affordance buttons: room-anchored DATA skills only (e.g. forge). Core
  // verbs (look/say/examine/take/drop/talk/go) are NOT rendered as buttons —
  // the verb bar, clickable objects, text input, and exits cover them.
  const bar = document.getElementById("skill-bar");
  bar.innerHTML = "";
  for (const s of snap.skills) {
    if (s.kind !== "data") continue;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = s.ui_hint;
    btn.dataset.skill = s.name;
    btn.onclick = () => sendInput(s.name);
    bar.appendChild(btn);
  }
  // Exit buttons: one per direction. Clicks send `go <direction>` (the
  // parser fast-path resolves it with no LLM call).
  const exitBar = document.getElementById("exit-bar");
  exitBar.innerHTML = "";
  const exits = (snap.room && snap.room.exits) || {};
  for (const dir of Object.keys(exits)) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = dir;
    btn.dataset.direction = dir;
    btn.onclick = () => sendInput("go " + dir);
    exitBar.appendChild(btn);
  }
}

function renderObjects(containerId, objs) {
  const el = document.getElementById(containerId);
  el.innerHTML = "";
  for (const o of objs) el.appendChild(objectChip(o, o.name));
}

function objectChip(o, label) {
  // A distinct, clickable scene element carrying its object id + kind, so
  // the verb bar / default-Examine can target it.
  const span = document.createElement("span");
  span.className = "obj obj-" + o.kind;
  span.dataset.objectId = o.id;
  span.dataset.kind = o.kind;
  span.textContent = label;
  span.onclick = () => onObjectClick(o.id);
  return span;
}

function toggleStagedVerb(verb, btn) {
  if (stagedVerb === verb) {
    clearStagedVerb();
    return;
  }
  clearStagedVerb();
  stagedVerb = verb;
  btn.classList.add("verb-staged");
}

function clearStagedVerb() {
  stagedVerb = null;
  document
    .querySelectorAll("#verb-bar button.verb-staged")
    .forEach((b) => b.classList.remove("verb-staged"));
}

function onObjectClick(objectId) {
  // Staged verb wins; a bare object click defaults to Examine.
  const verb = stagedVerb || "examine";
  if (verb === "talk") {
    const msg = (window.prompt("say what to them?") || "").trim();
    sendCommand("talk", objectId, msg);
  } else {
    sendCommand(verb, objectId);
  }
  clearStagedVerb();
}

function renderEvent(e) {
  if (e.seq <= lastSeq && lastSeq > 0) return; // dedupe on reconnect overlap
  lastSeq = Math.max(lastSeq, e.seq);

  // room_image_ready does not flow into the chat log; it just updates the bg.
  if (e.kind === "room_image_ready") {
    handleRoomImageReady(e);
    return;
  }

  const chat = document.getElementById("chat");
  const div = document.createElement("div");
  div.className = "evt evt-" + e.kind;
  if (e.kind === "say") {
    const who = actorNames[e.actor_id] || e.actor_id || "someone";
    div.innerHTML = `<span class="speaker">${escape(who)}:</span> &ldquo;${escape(
      e.payload.text || ""
    )}&rdquo;`;
  } else if (e.kind === "narrate") {
    div.innerHTML = linkifyEntities(e.payload.text || "");
    div.querySelectorAll(".entity-link").forEach((span) => {
      span.onclick = () => onObjectClick(span.dataset.objectId);
    });
  } else if (e.kind === "move") {
    const dir = e.payload.direction || "somewhere";
    div.textContent = "you go " + dir + ".";
  } else {
    div.textContent = `[${e.kind}] ${JSON.stringify(e.payload)}`;
  }
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
}

function setRoomBackground(room) {
  const bg = document.getElementById("room-bg");
  const overlay = document.getElementById("painting-overlay");
  if (room && room.image_url) {
    bg.src = room.image_url;
    overlay.classList.add("hidden");
  } else {
    bg.src = PLACEHOLDER_BG;
    overlay.classList.remove("hidden");
  }
}

function handleRoomImageReady(event) {
  const bg = document.getElementById("room-bg");
  const overlay = document.getElementById("painting-overlay");
  overlay.classList.add("hidden");
  if (event.payload && event.payload.image_url) {
    bg.src = event.payload.image_url;
  }
  // image_url null means generation failed; leave the placeholder showing.
  // The error string is in event.payload.error if anything wants to surface it.
}

function sendInput(text) {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  ws.send(JSON.stringify({ kind: "input", text: text }));
}

function sendCommand(verb, dobjId, args) {
  // The structured command frame: the click path. Bypasses the parser, so a
  // deterministic verb makes no LLM call (the server's verb handler may).
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  ws.send(
    JSON.stringify({
      kind: "command",
      verb: verb,
      dobj_id: dobjId || null,
      args: args || "",
    })
  );
}

function escapeRegex(s) {
  return String(s).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function linkifyEntities(text) {
  // Wrap in-scope object mentions in clickable spans (after escaping, so the
  // injected markup is the only HTML). Longest aliases first (entities is
  // pre-sorted) to prefer "sheaf of papers" over a bare "papers".
  let html = escape(text);
  for (const ent of entities) {
    if (!ent.alias) continue;
    const re = new RegExp("\\b(" + escapeRegex(escape(ent.alias)) + ")\\b", "gi");
    html = html.replace(
      re,
      '<span class="entity-link" data-object-id="' +
        escape(ent.object_id) +
        '">$1</span>'
    );
  }
  return html;
}

function systemLine(msg) {
  const chat = document.getElementById("chat");
  const div = document.createElement("div");
  div.className = "evt evt-system";
  div.textContent = msg;
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
}

function escape(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

document.getElementById("input-form").addEventListener("submit", (ev) => {
  ev.preventDefault();
  const inp = document.getElementById("input-text");
  const text = inp.value.trim();
  if (!text) return;
  sendInput(text);
  inp.value = "";
});

// ---- slot picker (toon-slot-management spec, 2026-05-07) -------------
//
// Toggles the slots panel; fetches /api/slots and renders one row per
// slot with the appropriate action button. Create / claim / kick all
// re-fetch and re-render. After a successful claim or create, the
// player reconnects the WS so the new connection's session→toon
// resolution picks up the new claim.

async function fetchSlots() {
  const r = await fetch("/api/slots", { credentials: "same-origin" });
  if (!r.ok) {
    systemLine(`(slots fetch failed: ${r.status})`);
    return null;
  }
  return r.json();
}

async function postSlotAction(slot, action, body) {
  const r = await fetch(`/api/slots/${slot}/${action}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    credentials: "same-origin",
    body: body ? JSON.stringify(body) : null,
  });
  if (!r.ok) {
    let detail = `${r.status}`;
    try {
      const j = await r.json();
      if (j.detail) detail = `${r.status} ${j.detail}`;
    } catch (_) {}
    systemLine(`(slot ${action} failed: ${detail})`);
    return null;
  }
  return r.json();
}

async function renderSlots() {
  const data = await fetchSlots();
  const list = document.getElementById("slots-list");
  list.innerHTML = "";
  if (!data) return;
  for (const entry of data.slots) {
    const li = document.createElement("li");
    li.className = "slot-row";
    const t = entry.toon;
    if (!t) {
      li.innerHTML = `<span class="slot-num">slot ${entry.slot}</span> <span class="slot-empty">empty</span>`;
      const btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = "create";
      btn.onclick = () => createInSlot(entry.slot);
      li.appendChild(btn);
    } else if (t.claimed_by_me) {
      li.innerHTML = `<span class="slot-num">slot ${entry.slot}</span> <strong>${escape(t.name)}</strong> <em>(yours)</em>`;
      const btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = "kick";
      btn.onclick = () => kickSlot(entry.slot);
      li.appendChild(btn);
    } else if (t.kicked_at) {
      li.innerHTML = `<span class="slot-num">slot ${entry.slot}</span> ${escape(t.name)} <em>(resting)</em>`;
      const btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = "claim";
      btn.onclick = () => claimSlot(entry.slot);
      li.appendChild(btn);
    } else if (!t.is_human_controlled) {
      // An uncontrolled toon (e.g. a seed character no one is playing): the
      // server allows claiming it, so offer claim here too (not just delete).
      li.innerHTML = `<span class="slot-num">slot ${entry.slot}</span> ${escape(t.name)} <em>(available)</em>`;
      const btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = "claim";
      btn.onclick = () => claimSlot(entry.slot);
      li.appendChild(btn);
    } else {
      li.innerHTML = `<span class="slot-num">slot ${entry.slot}</span> ${escape(t.name)} <em>(taken)</em>`;
    }
    if (t) {
      // A permanent delete sits alongside the slot's primary action.
      const del = document.createElement("button");
      del.type = "button";
      del.textContent = "delete";
      del.className = "slot-delete";
      del.onclick = () => deleteSlot(entry.slot);
      li.appendChild(del);
    }
    list.appendChild(li);
  }
}

async function createInSlot(slot) {
  const name = (window.prompt("name for the new toon?") || "").trim();
  if (!name) return;
  const appearance = (
    window.prompt("a few words of appearance?") || ""
  ).trim();
  if (!appearance) return;
  const result = await postSlotAction(slot, "create", {
    name,
    appearance_seed: appearance,
  });
  if (result) reconnectAfterSlotChange();
}

async function claimSlot(slot) {
  const result = await postSlotAction(slot, "claim", null);
  if (result) reconnectAfterSlotChange();
}

async function kickSlot(slot) {
  const result = await postSlotAction(slot, "kick", null);
  if (result) {
    await renderSlots();
    // After kicking yourself, the WS still holds the old toon for the
    // current session until reconnect; reconnect so subsequent input
    // routes to the legacy fallback (or whatever new claim follows).
    reconnectAfterSlotChange();
  }
}

async function deleteSlot(slot) {
  if (!window.confirm("permanently delete this toon? this cannot be undone.")) return;
  const result = await postSlotAction(slot, "delete", null);
  if (result) await renderSlots();
}

function reconnectAfterSlotChange() {
  // Any slot change (claim / create / switch / wake) re-enters as the new toon
  // with a CLEAN log: close the current socket while suppressing its onclose
  // auto-reconnect, then connect fresh (no ?since, so no replayed history).
  // (A transient network drop still auto-resumes via onclose -> connect(true).)
  document.getElementById("slots-panel").classList.add("hidden");
  awaitingPick = false;
  if (ws) {
    const old = ws;
    ws = null;
    try { old.onclose = null; old.close(); } catch (_) {}
  }
  connect(false);
}

document.getElementById("slots-toggle").addEventListener("click", async () => {
  const panel = document.getElementById("slots-panel");
  const opening = panel.classList.contains("hidden");
  panel.classList.toggle("hidden");
  if (opening) await renderSlots();
});

document.getElementById("slots-close").addEventListener("click", () => {
  document.getElementById("slots-panel").classList.add("hidden");
});

// "Leave the dream": a brief wake beat, release this session's toon, and
// return to the character picker (rather than the old no-op logout POST).
function enterPicker() {
  awaitingPick = true;
  document.getElementById("slots-panel").classList.remove("hidden");
  renderSlots();
}

document.getElementById("leave-dream").addEventListener("click", async () => {
  awaitingPick = true;
  systemLine("you wake...");
  try {
    await fetch("/api/session/leave", { method: "POST", credentials: "same-origin" });
  } catch (_) {}
  if (ws) { try { ws.close(); } catch (_) {} }
  enterPicker();
});

connect(false);
