"use strict";

const wsUrl =
  (location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws";
const PLACEHOLDER_BG = "/assets/placeholder-meadow.png";
let ws = null;
let lastSeq = 0;
let actorNames = {};

function connect() {
  ws = new WebSocket(wsUrl);
  ws.onopen = () => systemLine("(connected)");
  ws.onclose = () => {
    systemLine("(disconnected; reconnecting in a moment)");
    setTimeout(connect, 1500);
  };
  ws.onerror = () => systemLine("(connection error)");
  ws.onmessage = (msg) => {
    const data = JSON.parse(msg.data);
    if (data.kind === "state_snapshot") renderSnapshot(data);
    else if (data.kind === "event") renderEvent(data.event);
  };
}

function renderSnapshot(snap) {
  document.getElementById("room-title").textContent =
    snap.room ? snap.room.title : "drifting...";
  setRoomBackground(snap.room);
  // Map actor IDs to display names so 'say' events can name the speaker.
  actorNames = {};
  const toons = document.getElementById("toons");
  toons.innerHTML = "";
  for (const t of snap.toons) {
    actorNames[t.id] = t.name;
    const span = document.createElement("span");
    span.className = "toon";
    span.textContent = `${t.name} (${t.mood})`;
    toons.appendChild(span);
  }
  // Re-hydrate the chat from the snapshot's recent events.
  const chat = document.getElementById("chat");
  chat.innerHTML = "";
  lastSeq = 0; // allow snapshot replays to render
  for (const e of snap.events) renderEvent(e);
  lastSeq = snap.last_seq;
  // Skill buttons (canonical-form bypass: button click sends the skill name
  // as input so the server skips the LLM round-trip).
  const bar = document.getElementById("skill-bar");
  bar.innerHTML = "";
  for (const s of snap.skills) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = s.ui_hint;
    btn.dataset.skill = s.name;
    btn.onclick = () => sendInput(s.name);
    bar.appendChild(btn);
  }
  // Exit buttons: one per direction in the current room's exits_json.
  // Clicks send `go <direction>` which hits the canonical bypass too —
  // no LLM on navigation.
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
    div.textContent = e.payload.text || "";
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
    } else {
      li.innerHTML = `<span class="slot-num">slot ${entry.slot}</span> ${escape(t.name)} <em>(taken)</em>`;
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

function reconnectAfterSlotChange() {
  if (ws) {
    try { ws.close(); } catch (_) {}
  }
  // The onclose handler reconnects after a short delay; that path also
  // refreshes the slots list once the new state_snapshot lands.
  document.getElementById("slots-panel").classList.add("hidden");
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

connect();
