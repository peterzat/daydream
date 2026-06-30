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
let lastArrivalRoomId = null; // room of the last arrival line shown (suppresses re-show on same-room re-snapshots)
let pendingEl = null; // transient "thinking..." line during a slow (LLM) action
let pendingTimer = null; // its safety timeout
let loadedBuild = null; // server build SHA this page's JS loaded against (redeploy detection)
let loadedWorldVersion = null;
let lastCmd = null; // {key, t} -- debounce an accidental double-fire of one command

// Reconnect backoff: a dropped socket retries on a gentle, capped exponential
// delay behind a single calm "the dream is sleeping" overlay (not a growing
// pile of error lines), and recovers on its own when the server returns
// (SPEC 2026-06-30).
let reconnectDelay = 0;
const RECONNECT_MIN = 1000;
const RECONNECT_MAX = 20000;

function showDreamOverlay(text) {
  const o = document.getElementById("dream-overlay");
  o.textContent = text;
  o.classList.remove("hidden");
}

function hideDreamOverlay() {
  document.getElementById("dream-overlay").classList.add("hidden");
}

function majorOf(v) {
  // MAJOR int of a "MAJOR.MINOR" world_version string (0 when absent/garbled).
  return v ? parseInt(String(v).split(".")[0], 10) || 0 : 0;
}

function triggerUpdateReload() {
  // The server was redeployed under this open tab (it is still running the
  // main.js it loaded earlier — a WS reconnect never refreshes page JS), so the
  // rendering can be stale (this is what caused the forge id-garbage). Reload
  // ONCE into fresh assets. A sessionStorage guard prevents a reload loop if the
  // mismatch somehow persists; show a brief calm beat so the jump is explained.
  // Returns true when it is reloading, false when guarded.
  const KEY = "dd-reloaded-at";
  const now = Date.now();
  const last = parseInt(sessionStorage.getItem(KEY) || "0", 10);
  if (now - last < 15000) return false; // just reloaded — don't thrash
  sessionStorage.setItem(KEY, String(now));
  showDreamOverlay("the dream updated, stepping back in...");
  setTimeout(() => location.reload(), 900);
  return true;
}

function connect(isReconnect) {
  // A fresh page load omits `since` and starts with an empty log; a reconnect
  // resumes from the last event the client rendered.
  const url = isReconnect ? wsUrl + "?since=" + lastSeq : wsUrl;
  ws = new WebSocket(url);
  ws.onopen = () => {
    reconnectDelay = 0; // the dream wakes: reset the backoff
    hideDreamOverlay();
  };
  ws.onclose = () => {
    if (awaitingPick) return; // left the dream: wait for a toon pick
    // One calm state, not a growing pile of disconnect lines. Keep retrying on
    // a gentle, capped backoff; onopen hides the overlay when the server is
    // back, so a tab left open across a restart recovers with no manual reload.
    showDreamOverlay("the dream is sleeping...");
    reconnectDelay = Math.min(
      reconnectDelay ? reconnectDelay * 2 : RECONNECT_MIN,
      RECONNECT_MAX
    );
    setTimeout(() => connect(true), reconnectDelay);
  };
  ws.onerror = () => {}; // onclose drives the retry; no separate error line
  ws.onmessage = (msg) => {
    const data = JSON.parse(msg.data);
    if (data.kind === "state_snapshot") {
      hideDreamOverlay();
      renderSnapshot(data);
    } else if (data.kind === "event") {
      renderEvent(data.event);
    } else if (data.kind === "needs_toon") {
      enterPicker();
    } else if (data.kind === "world_changed") {
      // Live world hot-swap: a brief "the dream shifts" beat, cleared by the
      // fresh state_snapshot that follows.
      showDreamOverlay("the dream shifts...");
    }
  };
}

function renderSnapshot(snap) {
  // Redeploy detection: record the server's build + world version on the first
  // snapshot (when this JS and the server matched); if a later snapshot's build
  // differs (or the world's MAJOR changed), this tab is running stale JS against
  // a redeployed server — reload once into fresh assets.
  if (loadedBuild === null) {
    loadedBuild = snap.build || null;
    loadedWorldVersion = snap.world_version || null;
  } else if (
    (snap.build && snap.build !== loadedBuild) ||
    majorOf(snap.world_version) !== majorOf(loadedWorldVersion)
  ) {
    if (triggerUpdateReload()) return; // reloading into fresh assets; stop here
    // Guarded against a reload loop: adopt the new baseline and render
    // best-effort so the tab isn't frozen on the stale build.
    loadedBuild = snap.build || loadedBuild;
    loadedWorldVersion = snap.world_version || loadedWorldVersion;
  }
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
  // Map actor IDs to display names so 'say' events can name the speaker
  // (built from ALL co-located toons, including yourself).
  actorNames = {};
  for (const t of snap.toons || []) actorNames[t.id] = t.name;
  const selfId = snap.self ? snap.self.id : null;
  // WHO YOU ARE: the controlled toon, shown distinctly (not clickable —
  // it is identity, not a target).
  const selfEl = document.getElementById("self");
  selfEl.innerHTML = "";
  if (snap.self) {
    const span = document.createElement("span");
    span.className = "self-chip";
    span.textContent = `${snap.self.name} (${snap.self.mood})`;
    selfEl.appendChild(span);
  } else {
    selfEl.appendChild(emptyLine("drifting..."));
  }
  // WHO ELSE IS HERE: co-located toons, excluding yourself.
  const others = (snap.toons || []).filter((t) => t.id !== selfId);
  renderObjects("toons", others, "no one else is here", (t) => `${t.name} (${t.mood})`);
  // WHAT'S ON THE GROUND: room things (previously sent but never rendered).
  renderObjects("things", snap.items || [], "nothing around you");
  // WHAT YOU'RE CARRYING: inventory (things located on you).
  renderObjects("inventory", snap.inventory || [], "your hands are empty");
  // Re-hydrate the chat from the snapshot's recent events.
  const chat = document.getElementById("chat");
  clearPending();
  chat.innerHTML = "";
  lastSeq = 0; // allow snapshot replays to render
  for (const e of snap.events) renderEvent(e);
  lastSeq = snap.last_seq;
  // First arrival into a room (fresh connect / claim / a room with no replayed
  // history): the event log would otherwise be empty, so synthesize a look-style
  // arrival line from the snapshot, mirroring the server `look` ("You are in X.
  // You see: ..."). No round-trip and no stored event (look is per-viewer).
  // lastArrivalRoomId guards against re-showing it on same-room re-snapshots.
  const arrivalRoomId = snap.room ? snap.room.id : null;
  if (snap.room && arrivalRoomId !== lastArrivalRoomId && !chat.children.length) {
    let text = "You are in " + snap.room.title + ".";
    const groundItems = snap.items || [];
    if (groundItems.length) {
      text += " You see: " + groundItems.map((o) => o.name).join(", ") + ".";
    }
    const div = document.createElement("div");
    div.className = "evt evt-narrate";
    div.innerHTML = linkifyEntities(text, entities);
    div.querySelectorAll(".entity-link").forEach((span) => {
      span.onclick = () => onObjectClick(span.dataset.objectId);
    });
    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
  }
  lastArrivalRoomId = arrivalRoomId;
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

function renderObjects(containerId, objs, emptyText, labelFn) {
  const el = document.getElementById(containerId);
  el.innerHTML = "";
  if (!objs || !objs.length) {
    if (emptyText) el.appendChild(emptyLine(emptyText));
    return;
  }
  for (const o of objs) el.appendChild(objectChip(o, labelFn ? labelFn(o) : o.name));
}

function emptyLine(text) {
  const span = document.createElement("span");
  span.className = "region-empty";
  span.textContent = text;
  return span;
}

function objectChip(o, label) {
  // A distinct, clickable scene element carrying its object id + kind + the
  // verbs that apply to it, so the verb bar / default-Examine can target it
  // and client-side gating can dim verbs that don't apply.
  const span = document.createElement("span");
  span.className = "obj obj-" + o.kind;
  span.dataset.objectId = o.id;
  span.dataset.kind = o.kind;
  span.dataset.verbs = (o.verbs || []).join(",");
  span.textContent = label;
  span.onclick = () => onObjectClick(o.id, o.verbs || []);
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
  applyVerbGating();
}

function clearStagedVerb() {
  stagedVerb = null;
  document
    .querySelectorAll("#verb-bar button.verb-staged")
    .forEach((b) => b.classList.remove("verb-staged"));
  document
    .querySelectorAll("#scene .obj.obj-ungated")
    .forEach((o) => o.classList.remove("obj-ungated"));
}

function clearSceneAndLog() {
  // Entering the picker (no controllable toon): wipe the previous session's
  // scene + log so stale text doesn't sit visible under the picker (before, it
  // only cleared once a toon was claimed). Mirrors renderSnapshot's empty states.
  clearPending();
  document.getElementById("chat").innerHTML = "";
  document.getElementById("room-title").textContent = "drifting...";
  document.getElementById("room-desc").textContent = "";
  const selfEl = document.getElementById("self");
  selfEl.innerHTML = "";
  selfEl.appendChild(emptyLine("drifting..."));
  renderObjects("toons", [], "no one else is here");
  renderObjects("things", [], "nothing around you");
  renderObjects("inventory", [], "your hands are empty");
  document.getElementById("verb-bar").innerHTML = "";
  document.getElementById("skill-bar").innerHTML = "";
  document.getElementById("exit-bar").innerHTML = "";
  document.getElementById("room-bg").src = PLACEHOLDER_BG;
  document.getElementById("painting-overlay").classList.add("hidden");
  clearStagedVerb();
  lastArrivalRoomId = null;
}

function applyVerbGating() {
  // With a verb staged, dim + disable scene objects the verb can't apply to
  // (Talk -> toons; Take/Drop -> things; Examine -> toons + things). Object
  // chips carry their own verb list, so the verb bar offers a verb only where
  // it applies (SPEC 2026-06-30).
  document.querySelectorAll("#scene .obj").forEach((el) => {
    const verbs = (el.dataset.verbs || "").split(",").filter(Boolean);
    if (stagedVerb && !verbs.includes(stagedVerb)) el.classList.add("obj-ungated");
    else el.classList.remove("obj-ungated");
  });
}

function onObjectClick(objectId, objectVerbs) {
  // Staged verb wins; a bare object click defaults to Examine (valid for every
  // toon + thing). A staged verb the object doesn't support is a no-op, so we
  // never prompt for talk text on a non-toon.
  const verb = stagedVerb || "examine";
  // Gate ONLY when we know the object's verbs (scene chips pass them). Entity-
  // link mentions in narration call this with no verbs list, so don't silently
  // drop their click -- let the server validate the verb (it always does).
  if (stagedVerb && objectVerbs && !objectVerbs.includes(stagedVerb)) return;
  if (verb === "talk") {
    const msg = (window.prompt("say what to them?") || "").trim();
    sendCommand("talk", objectId, msg);
    showPending();
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
    // Attribute by the server-provided display name, falling back to the
    // current room's actor map; NEVER the raw actor id (no object/toon ids in
    // player-visible text — SPEC 2026-06-30).
    const who =
      (e.payload && e.payload.name) || actorNames[e.actor_id] || "someone";
    div.innerHTML = `<span class="speaker">${escape(who)}:</span> &ldquo;${escape(
      e.payload.text || ""
    )}&rdquo;`;
  } else if (e.kind === "narrate") {
    div.innerHTML = linkifyEntities(e.payload.text || "", entities);
    div.querySelectorAll(".entity-link").forEach((span) => {
      span.onclick = () => onObjectClick(span.dataset.objectId);
    });
  } else if (e.kind === "move") {
    const dir = e.payload.direction || "somewhere";
    div.textContent = "you go " + dir + ".";
  } else {
    // Other event kinds (object_moved / object_spawned / item_added /
    // mood_set / ...) are state-sync signals: the accompanying snapshot
    // refresh updates the scene panels and any human-readable line arrives
    // as a narrate. Their payloads carry object ids, so they are NOT dumped
    // to the chat (no raw ids in player-visible text — SPEC 2026-06-30).
    return;
  }
  clearPending(); // a slow action just produced its line; drop the "thinking" beat
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
  // Some browsers fire a click handler twice on a single tap, which would echo
  // the resulting line twice (e.g. a doubled "You examine ..."). Drop an
  // identical command (verb+dobj+args) repeated within 400ms.
  const key = verb + "|" + (dobjId || "") + "|" + (args || "");
  const now = Date.now();
  if (lastCmd && lastCmd.key === key && now - lastCmd.t < 400) return;
  lastCmd = { key, t: now };
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

function linkifyEntities(text, ents) {
  // Wrap in-scope object mentions in clickable spans. ONE pass over the escaped
  // text with a combined, longest-alias-first regex, so a shorter alias
  // ("keeper") never re-matches INSIDE the span already inserted for a longer,
  // overlapping one ("the forge-keeper"). The old per-alias iterative replace
  // nested spans on overlapping aliases, which leaked ids into the rendered
  // text. `ents` is passed explicitly so this stays pure and testable.
  const html = escape(text);
  const valid = (ents || []).filter((e) => e && e.alias);
  if (!valid.length) return html;
  // Escaped, lowercased alias -> object id (first wins on duplicate aliases).
  const byAlias = new Map();
  for (const e of valid) {
    const a = escape(e.alias);
    const k = a.toLowerCase();
    if (!byAlias.has(k)) byAlias.set(k, { alias: a, id: e.object_id });
  }
  const aliases = [...byAlias.values()].sort((a, b) => b.alias.length - a.alias.length);
  const pattern = aliases.map((a) => escapeRegex(a.alias)).join("|");
  const re = new RegExp("\\b(" + pattern + ")\\b", "gi");
  return html.replace(re, (m) => {
    const hit = byAlias.get(m.toLowerCase());
    const id = hit ? hit.id : "";
    return '<span class="entity-link" data-object-id="' + escape(id) + '">' + m + "</span>";
  });
}

function systemLine(msg) {
  const chat = document.getElementById("chat");
  const div = document.createElement("div");
  div.className = "evt evt-system";
  div.textContent = msg;
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
}

function clearPending() {
  // Remove the transient "thinking..." line (and its safety timer). Safe to
  // call when none is showing.
  if (pendingTimer) {
    clearTimeout(pendingTimer);
    pendingTimer = null;
  }
  if (pendingEl) {
    if (pendingEl.parentNode) pendingEl.parentNode.removeChild(pendingEl);
    pendingEl = null;
  }
}

function showPending() {
  // A calm "something is happening" beat for slow (LLM-backed) actions (talk and
  // free text), cleared when the next event renders. ~30s safety timeout in case
  // no event arrives (e.g. the LLM is foggy).
  clearPending();
  const chat = document.getElementById("chat");
  const div = document.createElement("div");
  div.className = "evt evt-pending";
  div.textContent = "the dream stirs...";
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
  pendingEl = div;
  pendingTimer = setTimeout(clearPending, 30000);
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
  showPending();
  inp.value = "";
});

// Backpack control: surface what you're carrying in the chat. Sends the same
// `inventory` command the text input does (the carrying region also lists it
// live in the scene). The click path makes no LLM call.
document.getElementById("backpack-toggle").addEventListener("click", () => {
  sendCommand("inventory");
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
  clearSceneAndLog();
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
