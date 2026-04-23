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

connect();
