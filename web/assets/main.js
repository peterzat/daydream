"use strict";

// Every URL here is relative to the document's <base href>: the server injects
// "/" in dev and "/daydream/" behind the edge Worker, so one build serves both
// (SPEC 2026-09-27 criterion 6). Never write a root-absolute path in this file;
// tests/test_web_paths.py fails on one.
function assetUrl(u) {
  // Server-emitted asset URLs are origin paths (slash-cache-slash..., some
  // persisted in old events); rebase them onto the document base so they stay
  // inside it.
  if (!u) return u;
  if (/^[a-z][a-z0-9+.-]*:/i.test(u)) return u; // data:, blob:, https:
  return new URL(u.replace(/^\/+/, ""), document.baseURI).href;
}
function wsUrlFor() {
  const u = new URL("ws", document.baseURI);
  u.protocol = u.protocol === "https:" ? "wss:" : "ws:";
  return u.href;
}
const wsUrl = wsUrlFor();
const PLACEHOLDER_BG = assetUrl("assets/placeholder-meadow.png");
let ws = null;
let lastSeq = 0;
let actorNames = {};
let selfToonId = null;
let awaitingPick = false; // showing the picker after leaving; suppresses auto-reconnect
let entities = []; // in-scope {alias, object_id, kind} for narration linking
let stagedVerb = null; // the verb-bar verb awaiting an object click
let stagedDobjId = null; // step-1 direct object of a two-object (give/use) verb, awaiting the iobj click
let verbSpecs = {}; // verb name -> {needs_iobj, valid_iobj_kinds} from the snapshot's verb_bar
let lastArrivalRoomId = null; // room of the last arrival line shown (suppresses re-show on same-room re-snapshots)
let pendingEl = null; // transient "thinking..." line during a slow (LLM) action
let pendingTimer = null; // its safety timeout
let loadedBuild = null; // server build SHA this page's JS loaded against (redeploy detection)
let loadedWorldVersion = null;
let lastCmd = null; // {key, t} -- debounce an accidental double-fire of one command
let pendingDetail = null; // {verb, name, t} -- a targeted examine/read whose next narrate renders as a detail inset (the ledger reveal)
let lastInventory = []; // the latest snapshot's carried things, for the keepsakes backpack foldout
let lastJournal = []; // the controlled toon's journal entries from the snapshot (self only)
let journalBeatShown = false; // "previously in your dream" fires once per toon entry
let bgShownFor = null; // room id whose art the plate currently shows (stale-art veil)
let wonState = null; // the world's won-moment ({score, rank, text?}) from snapshot status / game_won

// Reconnect backoff: a dropped socket retries on a gentle, capped exponential
// delay behind a single calm "the dream is sleeping" overlay (not a growing
// pile of error lines), and recovers on its own when the server returns
// (SPEC 2026-06-30).
let reconnectDelay = 0;
const RECONNECT_MIN = 1000;
const RECONNECT_MAX = 20000;
const ASLEEP_RETRY = 30000; // a sleeping village is checked gently
// An UNPLANNED outage (the Worker's `unplanned`: a deploy restart, a tunnel
// blip) reads as a brief drop for this long before the asleep note shows.
const UNPLANNED_GRACE = 60000;
let outageSince = 0;
let dreamingElsewhere = false; // another window of this account has the toon
let pingTimer = null;

async function whyClosed() {
  // "signed-out", {asleep, note, since, operator}, or null (a transient drop).
  try {
    const r = await fetch("api/me", { credentials: "same-origin", cache: "no-store" });
    if (r.status === 401) return "signed-out";
    if (r.status === 503) {
      const j = await r.json();
      if (j && j.asleep) {
        return { asleep: true, unplanned: !!j.unplanned, note: j.note, since: j.since,
                 operator: j.operator };
      }
    }
  } catch (_) {}
  return null;
}

function asleepText(why) {
  const who = why.operator || "the person who invited you";
  const note = why.note ? " " + why.note : "";
  return `The village is asleep.${note} Send ${who} a note to light the lamps; this page will wake with it.`;
}

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
    outageSince = 0;
    hideDreamOverlay();
    // A quiet keepalive: idle sockets survive the edge's proxy hops, and each
    // ping rides the server's per-frame session check.
    clearInterval(pingTimer);
    pingTimer = setInterval(() => {
      if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ kind: "ping" }));
    }, 25000);
  };
  ws.onclose = async (ev) => {
    clearInterval(pingTimer);
    if (awaitingPick || dreamingElsewhere) return; // left, or another window has us
    if (ev.code === 4409) {
      dreamingElsewhere = true;
      showDreamOverlay("you're dreaming in another window");
      return;
    }
    // Why did it close? A refused handshake reads as 1006 in the browser, so
    // ask: a lapsed session goes to the front door; a sleeping village (the
    // edge answers 503 while the box is down) shows its note and waits.
    const why = await whyClosed();
    if (why === "signed-out") {
      location.replace(document.baseURI);
      return;
    }
    // One calm state, not a growing pile of disconnect lines. Keep retrying on
    // a gentle, capped backoff; onopen hides the overlay when the server is
    // back, so a tab left open across a restart recovers with no manual reload.
    // A planned sleep shows its note at once; an unplanned one (a deploy's
    // restart) gets UNPLANNED_GRACE of quick retries first.
    if (!outageSince) outageSince = Date.now();
    const brief = why && why.asleep && why.unplanned
      && Date.now() - outageSince < UNPLANNED_GRACE;
    const sleeping = why && why.asleep && !brief;
    showDreamOverlay(sleeping ? asleepText(why) : "the dream is sleeping...");
    reconnectDelay = sleeping ? ASLEEP_RETRY : Math.min(
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
    } else if (data.kind === "clarify") {
      renderClarify(data);
    } else if (data.kind === "elsewhere") {
      dreamingElsewhere = true;
      showDreamOverlay("you're dreaming in another window");
    } else if (data.kind === "notice") {
      systemLine(data.text); // a gentle limit note (too long, too fast)
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
  // Feature flags the server gates optional surfaces on. regen_ui governs
  // the dev plate tools; when the server says off, the click handlers
  // below never reveal them (and the endpoints 404 anyway).
  featureRegenUi = !!(snap.features && snap.features.regen_ui);
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
    if (triggerUpdateReload()) {
      // The server marked this snapshot's note seen: carry it across the reload.
      if (snap.while_you_slept) stashSleptNote(snap.while_you_slept);
      return; // reloading into fresh assets; stop here
    }
    // Guarded against a reload loop: adopt the new baseline and render
    // best-effort so the tab isn't frozen on the stale build.
    loadedBuild = snap.build || loadedBuild;
    loadedWorldVersion = snap.world_version || loadedWorldVersion;
  }
  document.body.classList.remove("awake"); // in the dream again
  document.getElementById("room-title").textContent =
    snap.room ? snap.room.title : "drifting...";
  document.getElementById("room-desc").textContent =
    snap.room && snap.room.description ? snap.room.description : "";
  renderStatusRibbon(snap.status);
  renderFolio(snap.time);
  // The ended-marker derives from snapshot status, so late joiners and
  // reconnects learn of a win they never saw live (the game_won event is
  // world-scoped but transient). The marker reopens The End page; the
  // overlay itself only auto-opens on the live event.
  wonState = (snap.status && snap.status.won) || null;
  renderEndMarker();
  // Darkness veils the room art (criterion 6/12): the authored darkness
  // line is already the description, the scene panels arrive empty from the
  // server, and the plate goes near-black while inventory stays usable.
  document
    .getElementById("room-header")
    .classList.toggle("plate-dark", !!(snap.room && snap.room.dark));
  setRoomBackground(snap.room);
  // In-scope object mentions become clickable in narration.
  entities = (snap.entities || []).slice().sort(
    (a, b) => (b.alias || "").length - (a.alias || "").length
  );
  clearStagedVerb();
  pendingDetail = null; // a fresh snapshot supersedes any in-flight examine/read
  // Map actor IDs to display names so 'say' events can name the speaker
  // (built from ALL co-located toons, including yourself).
  actorNames = {};
  for (const t of snap.toons || []) actorNames[t.id] = t.name;
  const selfId = snap.self ? snap.self.id : null;
  selfToonId = selfId;
  // WHO YOU ARE: the controlled toon, shown distinctly (not clickable —
  // it is identity, not a target).
  const selfEl = document.getElementById("self");
  selfEl.innerHTML = "";
  if (snap.self) {
    selfEl.appendChild(toonFace(snap.self.image_url)); // your own painted face
    const nm = document.createElement("span");
    nm.className = "you-name";
    nm.textContent = snap.self.name;
    selfEl.appendChild(nm);
    if (snap.self.mood) {
      const md = document.createElement("span");
      md.className = "mood";
      md.textContent = snap.self.mood;
      selfEl.appendChild(md);
    }
  } else {
    selfEl.appendChild(emptyLine("drifting..."));
  }
  // WHO ELSE IS HERE: co-located toons, excluding yourself.
  const others = (snap.toons || []).filter((t) => t.id !== selfId);
  renderObjects("toons", others, "no one else is here",
    (t) => (t.mood && /^[a-z][a-z -]*$/.test(t.mood) ? `${t.name} (${t.mood})` : t.name));
  renderTopics(others);
  // WHAT'S ON THE GROUND: room things (previously sent but never rendered).
  renderObjects("things", snap.items || [], "nothing around you");
  // WHAT YOU'RE CARRYING: inventory (things located on you). Cached so the
  // keepsakes backpack foldout can render the same list as specimen cards.
  lastInventory = snap.inventory || [];
  renderObjects("inventory", lastInventory, "your hands are empty");
  lastJournal = snap.journal || []; // your own story so far (self only)
  // Your Book of Stray Minutes (self only); the link shows once it exists.
  lastBook = snap.book || null;
  document.getElementById("book-toggle").classList.toggle("hidden", !lastBook);
  if (!document.getElementById("book-panel").classList.contains("hidden")) {
    renderBook(lastBook); // keep an open book live as minutes are found
  }
  // A dream turned over while you were away: its note rides exactly one
  // snapshot, so show it now as a dismissible leaf.
  const carriedNote = takeSleptNote(); // one carried across a redeploy reload
  if (snap.while_you_slept) showSleptPage(snap.while_you_slept);
  else if (carriedNote) showSleptPage(carriedNote);
  // Re-hydrate the chat from the snapshot's recent events. In the same room
  // the reader keeps their place through the re-render, and only lines the
  // log had not shown yet come into view (a take's own line can arrive
  // inside the snapshot rather than ahead of it).
  const chat = document.getElementById("chat");
  const sameRoom = !!snap.room && snap.room.id === lastArrivalRoomId;
  const scroller = logScroller();
  const keptTop = sameRoom ? scroller.scrollTop : null;
  const shownSeq = lastSeq;
  const answerSeq = answerFrom && answerFrom.isConnected ? answerFrom.dataset.seq : null;
  clearPending();
  chat.innerHTML = "";
  lastSeq = 0; // allow snapshot replays to render
  replaying = true; // one settle after the whole log, not a scroll per line
  try {
    for (const e of snap.events) renderEvent(e);
  } finally {
    replaying = false;
  }
  lastSeq = snap.last_seq;
  answerFrom = answerSeq ? chat.querySelector(`[data-seq="${answerSeq}"]`) : null;
  // "Previously, in your dream...": a returning toon's last journal entry,
  // shown once per toon entry when the log starts empty (a fresh connect,
  // not a reconnect with replayed history).
  const chatEmpty = !chat.children.length;
  if (chatEmpty && !journalBeatShown && lastJournal.length) {
    journalBeatShown = true;
    const beat = document.createElement("aside");
    beat.className = "evt detail-inset journal-beat";
    const tab = document.createElement("span");
    tab.className = "tab";
    tab.textContent = "previously, in your dream";
    beat.appendChild(tab);
    const p = document.createElement("p");
    p.textContent = lastJournal[lastJournal.length - 1].text || "";
    beat.appendChild(p);
    chat.appendChild(beat);
  }
  // First arrival into a room (fresh connect / claim / a room with no replayed
  // history): the event log would otherwise be empty, so synthesize a look-style
  // arrival line from the snapshot, mirroring the server `look` ("You are in X.
  // You see: ..."). No round-trip and no stored event (look is per-viewer).
  // lastArrivalRoomId guards against re-showing it on same-room re-snapshots.
  // Uses the pre-beat emptiness so the journal beat doesn't suppress it.
  const arrivalRoomId = snap.room ? snap.room.id : null;
  if (snap.room && arrivalRoomId !== lastArrivalRoomId && chatEmpty) {
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
    followLog(div);
  }
  if (keptTop !== null) {
    scroller.scrollTop = keptTop;
    const fresh = [...chat.children].filter((el) => Number(el.dataset.seq) > shownSeq);
    if (fresh.length) followLog(fresh[fresh.length - 1], fresh[0]);
    else trimSpacer(scroller);
  }
  if (arrivalRoomId !== lastArrivalRoomId) requestAnimationFrame(showRoomTop);
  lastArrivalRoomId = arrivalRoomId;
  // Verb bar: Examine / Take / Drop / Talk. Click a verb to stage it, then
  // click an object; clicking an object with no staged verb defaults to
  // Examine. There is deliberately no generic "go" control here — the
  // per-direction exit buttons are the only nav affordance.
  const verbBar = document.getElementById("verb-bar");
  verbBar.innerHTML = "";
  verbSpecs = {};
  for (const v of snap.verb_bar || []) {
    verbSpecs[v.name] = v; // {needs_iobj, valid_iobj_kinds} drives two-step staging
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

function renderFolio(time) {
  // The village's time of day under the chapter title: "day 3 · dusk" once
  // time runs, a still line before the clock is mended, and the old quiet
  // folio for worlds that keep no time.
  const el = document.getElementById("folio");
  if (!time) { el.textContent = "the dream"; return; }
  if (!time.running) { el.textContent = "time stands still"; return; }
  el.textContent = "day " + time.day + " \u00b7 " + (time.label || time.phase);
}

const TOPIC_SHOW = 6;
const topicsOpen = new Set();

function renderTopics(others) {
  // What you could ask each person here about: one row per person with
  // topics, each topic a chip that sends the ask verb (a click, no typing,
  // no LLM). Rows appear only for people with something to say.
  const box = document.getElementById("topics");
  box.innerHTML = "";
  for (const t of others || []) {
    if (!t.topics || !t.topics.length) continue;
    const row = document.createElement("div");
    row.className = "topic-row";
    const who = document.createElement("span");
    who.className = "topic-who";
    who.textContent = "ask " + t.name + " about";
    row.appendChild(who);
    // A long list collapses to its first few (a resident with a dozen
    // topics read as a wall of chips); "more" opens the rest for this visit.
    const open = topicsOpen.has(t.id) || t.topics.length <= TOPIC_SHOW + 1;
    const shown = open ? t.topics : t.topics.slice(0, TOPIC_SHOW);
    for (const label of shown) {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "topic-chip";
      chip.textContent = label;
      chip.onclick = () => {
        sendCommand("ask", t.id, label);
        showPending();
      };
      row.appendChild(chip);
    }
    if (!open) {
      const more = document.createElement("button");
      more.type = "button";
      more.className = "topic-chip topic-more";
      more.textContent = `+${t.topics.length - TOPIC_SHOW} more`;
      more.onclick = () => {
        topicsOpen.add(t.id);
        renderTopics(others);
      };
      row.appendChild(more);
    }
    box.appendChild(row);
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

function toonFace(imageUrl) {
  // A toon's painted watercolor face (portrait pipeline, SPEC 2026-07-07),
  // or a quiet placeholder circle until it is painted / when the toon has
  // no appearance seed. ComfyUI-down simply leaves the placeholder.
  const face = document.createElement("span");
  face.className = "toon-face" + (imageUrl ? "" : " toon-face-unpainted");
  if (imageUrl) {
    const img = document.createElement("img");
    img.src = assetUrl(imageUrl);
    img.alt = "";
    face.appendChild(img);
  }
  return face;
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
  if (o.kind === "toon") span.prepend(toonFace(o.image_url));
  span.onclick = () => onObjectClick(o.id, o.verbs || [], o.kind);
  // A see-through container nests its contents as indented child chips
  // (criterion 4/12); each child is itself clickable (and may nest again).
  if (o.contents && o.contents.length) {
    const wrap = document.createElement("span");
    wrap.className = "obj-wrap";
    wrap.appendChild(span);
    const nest = document.createElement("span");
    nest.className = "obj-nest";
    for (const c of o.contents) nest.appendChild(objectChip(c, c.name));
    wrap.appendChild(nest);
    return wrap;
  }
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
  // No single-verb text hint: the staged chip (filled ink tab + amber pip) and
  // the dimming of non-applicable targets already show what's staged. Only the
  // genuinely two-step give/use flow gets a hint (showStagedHint, after the
  // direct object is picked).
}

function clearStagedVerb() {
  stagedVerb = null;
  stagedDobjId = null;
  hideStagedHint();
  document
    .querySelectorAll("#verb-bar button.verb-staged")
    .forEach((b) => b.classList.remove("verb-staged"));
  document
    .querySelectorAll("#scene .obj.obj-ungated")
    .forEach((o) => o.classList.remove("obj-ungated"));
  document
    .querySelectorAll("#scene .obj.obj-staged-dobj")
    .forEach((o) => o.classList.remove("obj-staged-dobj"));
}

function showStagedHint(verb, dobjName) {
  // The two-step prompt after a needs_iobj dobj is chosen: "give <X> to..." /
  // "use <X> on...". Names the chosen direct object so the second click reads.
  const spec = verbSpecs[verb] || {};
  const kinds = spec.valid_iobj_kinds || [];
  const word = (spec.preps && spec.preps[0]) ||
    (kinds.indexOf("toon") !== -1 ? "to" : "on");
  const hint = document.getElementById("verb-hint");
  hint.textContent = `${verb} ${dobjName} ${word}... (click a target, or the verb again to cancel)`;
  hint.classList.remove("hidden");
}

function hideStagedHint() {
  const hint = document.getElementById("verb-hint");
  hint.textContent = "";
  hint.classList.add("hidden");
}

function clearSceneAndLog() {
  // Entering the picker (no controllable toon): wipe the previous session's
  // scene + log so stale text doesn't sit visible under the picker (before, it
  // only cleared once a toon was claimed). Mirrors renderSnapshot's empty states.
  clearPending();
  document.getElementById("chat").innerHTML = "";
  setSpacer(0);
  answerFrom = null;
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
  bgShownFor = null;
  wonState = null; // the next toon/world's snapshot re-derives the ended-marker
  renderEndMarker();
  closeEndingPage();
  journalBeatShown = false; // the next toon entry may show its own beat
  renderTopics([]);
  renderFolio(null);
  lastBook = null; // the book, like the note, belongs to the toon that left
  document.getElementById("book-toggle").classList.add("hidden");
  closeBook();
  document.getElementById("slept-panel").classList.add("hidden");
}

function applyVerbGating() {
  // Dim + disable scene objects the staged verb can't apply to. Single-object
  // verbs (and step 1 of a two-object verb) gate by the object's own verb list
  // (Talk -> toons; Take/Drop -> things). Step 2 of a two-object verb (a dobj
  // already chosen) gates by iobj KIND (give -> a toon; use -> a thing); the
  // chosen dobj stays lit and highlighted. Object chips carry their verbs +
  // kind, so a verb is offered only where it applies (SPEC 2026-06-30).
  const spec = stagedVerb ? verbSpecs[stagedVerb] : null;
  const step2 = spec && spec.needs_iobj && stagedDobjId;
  const validIobjKinds = (spec && spec.valid_iobj_kinds) || [];
  document.querySelectorAll("#scene .obj").forEach((el) => {
    const verbs = (el.dataset.verbs || "").split(",").filter(Boolean);
    const isStagedDobj = stagedDobjId && el.dataset.objectId === stagedDobjId;
    let applies;
    if (!stagedVerb) applies = true;
    else if (isStagedDobj) applies = true; // the chosen dobj stays selectable/lit
    else if (step2) applies = validIobjKinds.includes(el.dataset.kind);
    else applies = verbs.includes(stagedVerb);
    el.classList.toggle("obj-ungated", !applies);
    el.classList.toggle("obj-staged-dobj", !!isStagedDobj);
  });
}

function onObjectClick(objectId, objectVerbs, objectKind) {
  const spec = stagedVerb ? verbSpecs[stagedVerb] : null;
  if (stagedVerb && spec && spec.needs_iobj) {
    // Two-step (give/use). Step 1: record the direct object; step 2: the click
    // is the indirect object -> send both ids. Gate ONLY when kind/verbs known
    // (entity-link clicks pass neither; let the server validate those).
    if (!stagedDobjId) {
      if (objectVerbs && !objectVerbs.includes(stagedVerb)) return;
      stagedDobjId = objectId;
      const chip = document.querySelector(
        `#scene .obj[data-object-id="${objectId}"]`
      );
      showStagedHint(stagedVerb, chip ? chip.textContent : "it");
      applyVerbGating();
      return;
    }
    if (objectId === stagedDobjId) return; // can't target the dobj at itself
    const validKinds = spec.valid_iobj_kinds || [];
    if (objectKind && validKinds.length && !validKinds.includes(objectKind)) return;
    sendCommand(stagedVerb, stagedDobjId, "", objectId);
    clearStagedVerb();
    return;
  }
  // Single-object path: staged verb wins; a bare click defaults to Examine
  // (valid for every toon + thing). A staged verb the object doesn't support is
  // a no-op, so we never prompt for talk text on a non-toon.
  const verb = stagedVerb || "examine";
  if (stagedVerb && objectVerbs && !objectVerbs.includes(stagedVerb)) return;
  const stagedSpec = verbSpecs[verb] || {};
  if (stagedSpec.needs_text) {
    // Free-text prompting is verb DATA (criterion 12): the server's verb_bar
    // carries needs_text + text_prompt, so talk, plant, and any world verb
    // prompt through one generic flow — no verb names hardcoded here. An
    // empty answer still sends (the server may reply with its own authored
    // question); the action may be LLM-backed, so show the pending beat.
    const msg = (window.prompt(stagedSpec.text_prompt || "and what do you say?") || "").trim();
    sendCommand(verb, objectId, msg);
    showPending();
  } else {
    // A targeted examine/read renders its narrate as a storybook detail inset
    // (the ledger reveal); remember the target so renderEvent can style it.
    if (verb === "examine" || verb === "read") {
      pendingDetail = { verb, objectId, name: nameForObject(objectId), t: Date.now() };
    }
    sendCommand(verb, objectId);
  }
  clearStagedVerb();
}

function nameForObject(objectId) {
  // Display name for the detail-inset tab: the scene chip's text if present,
  // else the in-scope entity alias (an in-prose affordance click), else "it".
  // Never an id (no object ids in player-visible text).
  const chip = document.querySelector(`#scene .obj[data-object-id="${objectId}"]`);
  if (chip && chip.textContent) return chip.textContent.trim();
  const ent = (entities || []).find((e) => e.object_id === objectId);
  return ent && ent.alias ? ent.alias : "it";
}

function renderEvent(e) {
  if (e.seq <= lastSeq && lastSeq > 0) return; // dedupe on reconnect overlap
  lastSeq = Math.max(lastSeq, e.seq);

  // room_image_ready does not flow into the chat log; it just updates the bg.
  if (e.kind === "room_image_ready") {
    handleRoomImageReady(e);
    return;
  }

  // The world was won (a live, world-scoped moment — it reaches every player,
  // not just the winner's room): present The End storybook page. Dismissible;
  // the world keeps running, and the quiet end-marker can reopen it.
  if (e.kind === "game_won") {
    wonState = e.payload || {};
    renderEndMarker();
    showEndingPage(wonState);
    return;
  }

  // A targeted examine/read just fired: render its narrate as a storybook
  // detail inset (the ledger reveal) rather than a plain prose line.
  if (e.kind === "narrate" && pendingDetail && Date.now() - pendingDetail.t < 8000) {
    renderDetailInset(e, pendingDetail);
    pendingDetail = null;
    return;
  }

  const chat = document.getElementById("chat");
  const div = document.createElement("div");
  div.className = "evt evt-" + e.kind;
  div.dataset.seq = e.seq;
  if (e.kind === "say") {
    // Attribute by the server-provided display name, falling back to the
    // current room's actor map; NEVER the raw actor id (no object/toon ids in
    // player-visible text — SPEC 2026-06-30).
    const who =
      (e.payload && e.payload.name) || actorNames[e.actor_id] || "someone";
    const to = e.payload && e.payload.to ? ` <span class="to">to ${escape(e.payload.to)}</span>` : "";
    div.innerHTML = `<span class="speaker">${escape(who)}${to}:</span> &ldquo;${escape(
      e.payload.text || ""
    )}&rdquo;`;
  } else if (e.kind === "narrate") {
    const text = e.payload.text || "";
    // The line just shown repeating verbatim (an affordance clicked twice, a
    // temp-0 skill echoing itself) glows the existing line instead of
    // stacking a duplicate — the detail-inset de-dup's sibling for plain
    // prose (playtest 2026-07-02).
    const prior = chat.lastElementChild;
    if (prior && prior.classList.contains("evt-narrate") &&
        prior.dataset.text === text) {
      clearPending();
      glowElement(prior);
      followLog(prior);
      return;
    }
    div.dataset.text = text;
    div.innerHTML = linkifyEntities(text, entities);
    div.querySelectorAll(".entity-link").forEach((span) => {
      span.onclick = () => onObjectClick(span.dataset.objectId);
    });
  } else if (e.kind === "move") {
    // Whose move is this? Co-located departures arrive on the room
    // filter too (playtest 2026-07-02: another player's walk rendered as
    // "you go west"). Only the controlled toon's moves read as "you" —
    // and only YOUR death blacks out YOUR screen.
    const mine = e.actor_id === selfToonId;
    const mover = actorNames[e.actor_id] || "someone";
    if (e.payload && e.payload.died) {
      // Death interstitial: a brief black beat before the respawn snapshot
      // re-renders the world; the authored message arrives as its own
      // narrate. No "you go" line for dying.
      if (mine) {
        showDeathOverlay();
      } else {
        div.textContent = mover + " crumples, and is elsewhere.";
        clearPending();
        chat.appendChild(div);
        followLog(div);
      }
      return;
    }
    if (e.payload && e.payload.teleport) {
      div.textContent = mine
        ? "the world shifts around you."
        : mover + " is suddenly elsewhere.";
    } else {
      const dir = e.payload.direction || "somewhere";
      div.textContent = mine
        ? "you go " + dir + "."
        : mover + " heads " + dir + ".";
    }
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
  followLog(div);
}

function renderDetailInset(e, detail) {
  // The storybook expression of examine/read: a warm parchment card with a tab
  // label and the described text, revealed inline in the prose (DESIGN.md).
  const chat = document.getElementById("chat");
  const text = e.payload.text || "";
  // Examining the same thing again with the same result should not stack a
  // duplicate card: resurface the existing one at the bottom and glow it
  // ("don't repeat, glow the answer").
  if (detail.objectId) {
    const prior = chat.querySelector(
      `.detail-inset[data-object-id="${detail.objectId}"]`
    );
    if (prior && prior.dataset.text === text) {
      clearPending();
      chat.appendChild(prior); // move to the end, no duplicate
      glowElement(prior);
      followLog(prior);
      return;
    }
  }
  const aside = document.createElement("aside");
  aside.className = "evt detail-inset";
  aside.dataset.seq = e.seq;
  if (detail.objectId) aside.dataset.objectId = detail.objectId;
  aside.dataset.text = text; // for the repeat-examine glow check above
  const tab = document.createElement("span");
  tab.className = "tab";
  const nm = detail.name || "it";
  tab.textContent = detail.verb === "read" ? `${nm}, read` : `you examine ${nm}`;
  aside.appendChild(tab);
  const p = document.createElement("p");
  p.innerHTML = linkifyEntities(text, entities);
  p.querySelectorAll(".entity-link").forEach((span) => {
    span.onclick = () => onObjectClick(span.dataset.objectId);
  });
  aside.appendChild(p);
  const dogear = document.createElement("span");
  dogear.className = "dogear";
  aside.appendChild(dogear);
  clearPending();
  chat.appendChild(aside);
  followLog(aside);
}

function glowElement(el) {
  // Restart the glow animation even if the class is already present.
  el.classList.remove("detail-glow");
  void el.offsetWidth; // force reflow so re-adding the class replays it
  el.classList.add("detail-glow");
}

function setRoomBackground(room) {
  // On a ROOM CHANGE the old art is veiled immediately (bg-loading -> opacity
  // 0) and the plate reveals only once the next bitmap decodes (the img load
  // listener below), so the previous room's painting never lingers under the
  // new room's header (playtest 2026-07-02). Same-room re-snapshots and the
  // room_image_ready paint-in keep showing the current bitmap while the new
  // one loads — that cross-fade IS the painting reveal.
  const bg = document.getElementById("room-bg");
  const overlay = document.getElementById("painting-overlay");
  const target = room && room.image_url ? assetUrl(room.image_url) : PLACEHOLDER_BG;
  const changedRoom = !room || room.id !== bgShownFor;
  bgShownFor = room ? room.id : null;
  if (changedRoom) bg.classList.add("bg-loading");
  if (bg.src && bg.src.endsWith(target)) {
    bg.classList.remove("bg-loading"); // same bitmap: nothing to wait for
  } else {
    bg.src = target;
  }
  overlay.classList.toggle("hidden", !!(room && room.image_url));
}

// Reveal the plate when its bitmap has actually decoded (pairs with the
// bg-loading veil in setRoomBackground).
document.getElementById("room-bg").addEventListener("load", () => {
  document.getElementById("room-bg").classList.remove("bg-loading");
});

function handleRoomImageReady(event) {
  const bg = document.getElementById("room-bg");
  const overlay = document.getElementById("painting-overlay");
  overlay.classList.add("hidden");
  if (event.payload && event.payload.image_url) {
    bg.src = assetUrl(event.payload.image_url);
  }
  // image_url null means generation failed; leave the placeholder showing.
  // The error string is in event.payload.error if anything wants to surface it.
}

function renderStatusRibbon(status) {
  // Visible only for worlds that author a rank ladder (rank non-null);
  // clockmakers keeps its quiet header. Score / rank / moves / light.
  const el = document.getElementById("status-ribbon");
  if (!status || status.rank === null || status.rank === undefined) {
    el.classList.add("hidden");
    el.innerHTML = "";
    return;
  }
  el.classList.remove("hidden");
  el.innerHTML = "";
  const parts = [
    ["st-score", "score " + (status.score || 0)],
    ["st-rank", String(status.rank)],
    ["st-moves", "moves " + (status.moves || 0)],
  ];
  for (const [id, text] of parts) {
    const span = document.createElement("span");
    span.id = id;
    span.className = "st-part";
    span.textContent = text;
    el.appendChild(span);
  }
  const light = document.createElement("span");
  light.id = "st-light";
  light.className = "st-part st-light " + (status.lit ? "lit" : "unlit");
  light.title = status.lit ? "you can see" : "it is dark";
  light.textContent = status.lit ? "\u2600" : "\u263D";
  el.appendChild(light);
}

function renderEndMarker() {
  // The quiet "the end" fleuron under the title: present only once the world
  // has been won. Clicking it reopens The End page from the stored moment.
  document.getElementById("end-marker").classList.toggle("hidden", !wonState);
}

function showEndingPage(w) {
  // The End: a dismissible storybook page carrying the winning score + rank.
  // Wording is world-agnostic; the authored flavor arrives in w.text. No
  // ids are ever rendered (the payload's actor id is deliberately unused).
  if (!w) return;
  document.getElementById("ending-text").textContent =
    w.text || "The dream reaches its final page.";
  const scoreEl = document.getElementById("ending-score");
  scoreEl.innerHTML = "";
  if (typeof w.score === "number") {
    const s = document.createElement("span");
    s.className = "ending-stat";
    s.textContent = "score " + w.score;
    scoreEl.appendChild(s);
  }
  if (w.rank) {
    const rk = document.createElement("span");
    rk.className = "ending-stat ending-rank";
    rk.textContent = String(w.rank);
    scoreEl.appendChild(rk);
  }
  document.getElementById("ending-panel").classList.remove("hidden");
}

function closeEndingPage() {
  document.getElementById("ending-panel").classList.add("hidden");
}

document.getElementById("ending-close").addEventListener("click", closeEndingPage);
document.getElementById("ending-panel").addEventListener("click", (e) => {
  if (e.target.id === "ending-panel") closeEndingPage(); // click the backdrop to close
});
document.getElementById("end-marker").addEventListener("click", () => {
  showEndingPage(wonState);
});

function renderClarify(c) {
  // The ambiguity question's clickable options (the prompt text itself
  // arrives as a private narrate). Clicking one completes the pending
  // command via the normal command frame; any other action abandons it.
  const chat = document.getElementById("chat");
  const div = document.createElement("div");
  div.className = "evt evt-clarify";
  for (const opt of c.options || []) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "clarify-opt";
    btn.textContent = opt.name;
    btn.onclick = () => {
      if (c.slot === "iobj") {
        sendCommand(c.verb, c.dobj_id, c.args || "", opt.id);
      } else {
        sendCommand(c.verb, opt.id, c.args || "", c.iobj_id);
      }
      div.remove();
    };
    div.appendChild(btn);
  }
  clearPending();
  chat.appendChild(div);
  followLog(div);
}

function showDeathOverlay() {
  const o = document.getElementById("death-overlay");
  o.textContent = "everything goes black...";
  o.classList.remove("hidden");
  setTimeout(() => o.classList.add("hidden"), 2200);
}

function youActed() {
  // What you just did should show, even right after arriving, and its answer
  // opens from its first line (followLog).
  holdPinUntil = 0;
  actedAt = Date.now();
  answerFrom = null;
}

function sendInput(text) {
  youActed();
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  ws.send(JSON.stringify({ kind: "input", text: text }));
}

function sendCommand(verb, dobjId, args, iobjId) {
  youActed();
  // The structured command frame: the click path. Bypasses the parser, so a
  // deterministic verb makes no LLM call (the server's verb handler may). A
  // two-object verb (give/use) carries iobj_id; single-object verbs omit it.
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  // Some browsers fire a click handler twice on a single tap, which would echo
  // the resulting line twice (e.g. a doubled "You examine ..."). Drop an
  // identical command (verb+dobj+iobj+args) repeated within 400ms.
  const key = verb + "|" + (dobjId || "") + "|" + (iobjId || "") + "|" + (args || "");
  const now = Date.now();
  if (lastCmd && lastCmd.key === key && now - lastCmd.t < 400) return;
  lastCmd = { key, t: now };
  ws.send(
    JSON.stringify({
      kind: "command",
      verb: verb,
      dobj_id: dobjId || null,
      iobj_id: iobjId || null,
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
  followLog(div);
}

// ---- reading the log ------------------------------------------------------
// Entering a room shows its description first; the arrival lines that land
// right after (greetings, the replayed room log) must not yank the view away
// from it, so following holds briefly after a room change.
let holdPinUntil = 0;
const ARRIVAL_HOLD_MS = 2500;
// A new line comes into view without leaving the column starting mid-
// paragraph (playtest 2026-09-28: asking a resident about a topic left the
// tail of an older line at the top). When a line needs scrolling, the view
// comes to rest at the top of a paragraph, and an answer to what you just did
// opens at its own first line when it is taller than the column. A spacer
// under the log makes that resting place reachable. A reader scrolled back
// through the log keeps their place unless they just acted.
let actedAt = 0; // when you last did something (sendInput / sendCommand)
const ACT_FOLLOW_MS = 30000; // lines this soon after your action answer it
let answerFrom = null; // the first line of the answer to your last action
let replaying = false; // a snapshot is re-rendering the log: no scrolling per line

function logScroller() {
  // On desktop the whole reading column (the room description plus the log)
  // is the scroll container; on phones the log scrolls in its own box.
  const chat = document.getElementById("chat");
  const prose = chat.closest(".prose");
  return prose && getComputedStyle(prose).overflowY !== "visible" ? prose : chat;
}

function spacerPx() {
  return parseFloat(document.getElementById("chat").style.paddingBottom) || 0;
}

function setSpacer(px) {
  document.getElementById("chat").style.paddingBottom = px > 0 ? Math.ceil(px) + "px" : "";
}

function contentEnd(sc) {
  // Where the text ends inside the scroller, not counting the spacer.
  return sc.scrollHeight - (sc.contains(document.getElementById("chat")) ? spacerPx() : 0);
}

function trimSpacer(sc) {
  // Keep only as much spacer as the current resting place needs.
  const need = Math.max(0, sc.scrollTop + sc.clientHeight - (sc.scrollHeight - spacerPx()));
  if (need < spacerPx()) setSpacer(need);
}

function offsetIn(el, sc, edge) {
  // An element's top (margin box) or bottom, in the scroller's coordinates.
  const r = el.getBoundingClientRect();
  const origin = sc.getBoundingClientRect().top + sc.clientTop - sc.scrollTop;
  if (edge === "bottom") return r.bottom - origin;
  return r.top - (parseFloat(getComputedStyle(el).marginTop) || 0) - origin;
}

function paragraphsIn(sc) {
  const chat = document.getElementById("chat");
  const desc = document.getElementById("room-desc");
  const paras = [...chat.children];
  if (sc !== chat && desc.textContent) paras.unshift(desc);
  return paras;
}

function revealRange(first, last, sc) {
  // Bring first..last into view, resting on a paragraph's top.
  const viewH = sc.clientHeight;
  const top = offsetIn(first, sc, "top");
  const bottom = offsetIn(last, sc, "bottom");
  if (top >= sc.scrollTop - 1 && bottom <= sc.scrollTop + viewH + 1) {
    trimSpacer(sc);
    return;
  }
  let target = top;
  if (bottom - top <= viewH) {
    // The earliest paragraph top that still shows the whole range.
    for (const p of paragraphsIn(sc)) {
      const t = offsetIn(p, sc, "top");
      if (t >= bottom - viewH - 1) { target = Math.min(t, top); break; }
    }
  }
  target = Math.max(0, target);
  setSpacer(Math.max(0, target + viewH - contentEnd(sc)));
  sc.scrollTop = target;
}

function wasFollowing(el, sc) {
  // Was the line before this one in view? Then the reader was following.
  const prev = el.previousElementSibling ||
    (sc !== document.getElementById("chat") ? document.getElementById("room-desc") : null);
  if (!prev || !prev.getBoundingClientRect().height) return true;
  return offsetIn(prev, sc, "bottom") <= sc.scrollTop + sc.clientHeight + 4;
}

function followLog(el, first) {
  // Called with each line added to (or glowed in) the log; `first` is the
  // earliest of several lines that arrived together.
  if (replaying || !el || !el.isConnected) return;
  first = first || el;
  const sc = logScroller();
  const answering = Date.now() - actedAt < ACT_FOLLOW_MS;
  if (answering && !(answerFrom && answerFrom.isConnected)) answerFrom = first;
  if (sc !== document.getElementById("chat") && Date.now() < holdPinUntil) {
    trimSpacer(sc);
    return;
  }
  if (!answering && !wasFollowing(first, sc)) {
    trimSpacer(sc);
    return;
  }
  revealRange(answering ? answerFrom : first, el, sc);
  // On a phone the log is a box in a scrolling page, and the topic chips sit
  // below it: bring the box into view when it answers what you just did.
  if (answering && sc === document.getElementById("chat")) {
    const r = sc.getBoundingClientRect();
    if (r.bottom <= 0 || r.top >= window.innerHeight) sc.scrollIntoView({ block: "nearest" });
  }
}

function showRoomTop() {
  // Entering a room: show its description first, not the bottom of its log.
  holdPinUntil = Date.now() + ARRIVAL_HOLD_MS;
  answerFrom = null;
  setSpacer(0);
  const prose = document.querySelector(".prose");
  if (prose) prose.scrollTop = 0;
  // On a phone the page itself scrolls: bring the new room's plate and title
  // back into view after a move made from the compass at the foot.
  if (window.innerWidth <= 640) window.scrollTo(0, 0);
}

// Scroll cues: overlay scrollbars (macOS, phones) stay hidden until you
// scroll, so a column holding more than it shows fades at that edge instead
// (playtest 2026-09-28; the .more-above / .more-below styles).
function updateScrollCue(el) {
  const scrollable = getComputedStyle(el).overflowY !== "visible" &&
    el.scrollHeight - el.clientHeight > 2;
  el.classList.toggle("more-above", scrollable && el.scrollTop > 2);
  el.classList.toggle("more-below",
    scrollable && el.scrollTop + el.clientHeight < contentEnd(el) - 2);
}

function watchScroll(el) {
  if (!el) return;
  let queued = false;
  const update = () => {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => { queued = false; updateScrollCue(el); });
  };
  el.addEventListener("scroll", update, { passive: true });
  if (window.ResizeObserver) new ResizeObserver(update).observe(el);
  new MutationObserver(update).observe(el, { childList: true, subtree: true, characterData: true });
  window.addEventListener("resize", update);
  update();
}
["chat", "scene"].forEach((id) => watchScroll(document.getElementById(id)));
watchScroll(document.querySelector(".prose"));

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
  followLog(div);
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

// What you typed, for Up/Down recall (as in any text game), this tab only.
const inputHistory = [];
let historyPos = 0;
let historyDraft = ""; // the half-typed line, kept while you browse history

document.getElementById("input-form").addEventListener("submit", (ev) => {
  ev.preventDefault();
  const inp = document.getElementById("input-text");
  const text = inp.value.trim();
  if (!text) return;
  sendInput(text);
  showPending();
  if (inputHistory[inputHistory.length - 1] !== text) inputHistory.push(text);
  if (inputHistory.length > 50) inputHistory.shift();
  historyPos = inputHistory.length;
  inp.value = "";
});

document.getElementById("input-text").addEventListener("keydown", (ev) => {
  if (ev.key !== "ArrowUp" && ev.key !== "ArrowDown") return;
  if (!inputHistory.length) return;
  const browsing = historyPos < inputHistory.length;
  if (ev.key === "ArrowDown" && !browsing) return; // never erases a half-typed line
  ev.preventDefault();
  const inp = ev.target;
  if (!browsing) historyDraft = inp.value;
  historyPos += ev.key === "ArrowUp" ? -1 : 1;
  historyPos = Math.max(0, Math.min(inputHistory.length, historyPos));
  inp.value = historyPos < inputHistory.length ? inputHistory[historyPos] : historyDraft;
  inp.setSelectionRange(inp.value.length, inp.value.length);
});

// Backpack control: open the keepsakes foldout over the live inventory (a
// two-page specimen spread), replacing the old "print inventory to chat". No
// server round-trip: it renders the last snapshot's inventory client-side.
document.getElementById("backpack-toggle").addEventListener("click", openBackpack);
document.getElementById("backpack-close").addEventListener("click", closeBackpack);
document.getElementById("backpack-panel").addEventListener("click", (e) => {
  if (e.target.id === "backpack-panel") closeBackpack(); // click the backdrop to close
});

// ---- the Book of Stray Minutes ------------------------------------------
let lastBook = null;
let bookPageId = null;

document.getElementById("book-toggle").addEventListener("click", () => {
  renderBook(lastBook);
  document.getElementById("book-panel").classList.remove("hidden");
});
document.getElementById("book-close").addEventListener("click", closeBook);
document.getElementById("book-panel").addEventListener("click", (e) => {
  if (e.target.id === "book-panel") closeBook();
});

function closeBook() {
  document.getElementById("book-panel").classList.add("hidden");
}

function renderBook(book) {
  if (!book) return;
  document.getElementById("book-title").textContent = book.title || "The Book";
  document.getElementById("book-sub").textContent =
    book.found + " of " + book.total + " stray minutes found";
  const pagesBox = document.getElementById("book-pages");
  pagesBox.innerHTML = "";
  const pages = book.pages || [];
  if (!bookPageId || !pages.some((p) => p.id === bookPageId)) {
    const started = pages.find((p) => p.found > 0);
    bookPageId = (started || pages[0] || {}).id || null;
  }
  for (const pg of pages) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "book-page-link" + (pg.id === bookPageId ? " current" : "") +
      (pg.complete ? " complete" : "");
    btn.textContent = pg.title + "  " + pg.found + "/" + pg.total;
    btn.onclick = () => { bookPageId = pg.id; renderBook(lastBook); };
    pagesBox.appendChild(btn);
  }
  const page = pages.find((p) => p.id === bookPageId);
  const entries = document.getElementById("book-entries");
  entries.innerHTML = "";
  document.getElementById("book-page-title").textContent = page ? page.title : "minutes";
  const reward = document.getElementById("book-reward");
  reward.classList.toggle("hidden", !(page && page.reward_text));
  reward.textContent = page && page.reward_text ? page.reward_text : "";
  if (!page) return;
  for (const e of page.entries) {
    const row = document.createElement("div");
    row.className = "book-entry" + (e.found ? " found" : "");
    if (e.found) {
      const nm = document.createElement("div");
      nm.className = "book-entry-name";
      nm.textContent = e.name;
      const tx = document.createElement("div");
      tx.className = "book-entry-text";
      tx.textContent = e.text;
      row.appendChild(nm);
      row.appendChild(tx);
    } else {
      row.textContent = "\u00b7 \u00b7 \u00b7";
    }
    entries.appendChild(row);
  }
}

// ---- while you slept ------------------------------------------------------
const SLEPT_KEY = "dd-slept-note"; // a note that arrived on a reloading snapshot

function stashSleptNote(note) {
  try { sessionStorage.setItem(SLEPT_KEY, JSON.stringify(note)); } catch (e) { /* best effort */ }
}

function takeSleptNote() {
  try {
    const raw = sessionStorage.getItem(SLEPT_KEY);
    sessionStorage.removeItem(SLEPT_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (e) {
    return null;
  }
}

function showSleptPage(note) {
  document.getElementById("slept-title").textContent = note.title || "While you slept";
  document.getElementById("slept-text").textContent = note.text || "";
  document.getElementById("slept-panel").classList.remove("hidden");
}
document.getElementById("slept-close").addEventListener("click", () => {
  document.getElementById("slept-panel").classList.add("hidden");
});
document.getElementById("slept-panel").addEventListener("click", (e) => {
  if (e.target.id === "slept-panel") document.getElementById("slept-panel").classList.add("hidden");
});

function openBackpack() {
  renderKeepsakes(lastInventory);
  renderCollection(lastJournal);
  document.getElementById("backpack-panel").classList.remove("hidden");
}

function closeBackpack() {
  document.getElementById("backpack-panel").classList.add("hidden");
}

// ---- dev room-image repaint tools --------------------------------------
// Click the plate for a repaint arrow (same-prompt regen); double-click for
// the gear (open the prompt editor). Both reveal lower-right and auto-hide.
// Nothing typed is persisted; a repaint overwrites the cached image in place
// and the room_image_ready event swaps the art in for everyone in the room.
// A dev instrument, gated by the server's features.regen_ui flag
// (DAYDREAM_REGEN_UI; the endpoints 404 when it is off).
let featureRegenUi = false;
let plateClickTimer = null;
let plateToolsHideTimer = null;

function showPlateTool(which) {
  if (!featureRegenUi) return;
  const tools = document.getElementById("plate-tools");
  document.getElementById("plate-regen").classList.toggle("hidden", which !== "regen");
  document.getElementById("plate-gear").classList.toggle("hidden", which !== "gear");
  tools.classList.remove("hidden");
  if (plateToolsHideTimer) clearTimeout(plateToolsHideTimer);
  plateToolsHideTimer = setTimeout(hidePlateTools, 4000);
}

function hidePlateTools() {
  document.getElementById("plate-tools").classList.add("hidden");
  if (plateToolsHideTimer) { clearTimeout(plateToolsHideTimer); plateToolsHideTimer = null; }
}

async function postRepaint(prompt) {
  if (!bgShownFor) { systemLine("(no room to repaint yet)"); return; }
  // Show the painting overlay immediately; room_image_ready clears it.
  document.getElementById("painting-overlay").classList.remove("hidden");
  const body = prompt ? { prompt } : {};
  const r = await fetch(`api/rooms/${encodeURIComponent(bgShownFor)}/image`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    document.getElementById("painting-overlay").classList.add("hidden");
    let detail = `${r.status}`;
    try { const j = await r.json(); if (j.detail) detail = `${r.status} ${j.detail}`; } catch (_) {}
    systemLine(`(repaint failed: ${detail})`);
  }
}

async function openRepaintDialog() {
  if (!bgShownFor) { systemLine("(no room to repaint yet)"); return; }
  const current = document.getElementById("repaint-current");
  const input = document.getElementById("repaint-input");
  current.textContent = "loading...";
  input.value = "";
  document.getElementById("repaint-panel").classList.remove("hidden");
  try {
    const r = await fetch(`api/rooms/${encodeURIComponent(bgShownFor)}/image-prompt`,
      { credentials: "same-origin" });
    if (!r.ok) throw new Error(`${r.status}`);
    const j = await r.json();
    current.textContent = j.prompt;
    input.value = j.prompt; // prefill so a dev edits from the real prompt
  } catch (e) {
    current.textContent = `(could not load prompt: ${e.message})`;
  }
}

function closeRepaintDialog() {
  document.getElementById("repaint-panel").classList.add("hidden");
}

// Single vs double click on the plate: a 250 ms timer distinguishes them so
// a dblclick doesn't also fire the single-click branch.
document.querySelector(".plate-figure").addEventListener("click", () => {
  if (plateClickTimer) return; // second half of a dblclick; let dblclick win
  plateClickTimer = setTimeout(() => {
    plateClickTimer = null;
    showPlateTool("regen");
  }, 250);
});
document.querySelector(".plate-figure").addEventListener("dblclick", () => {
  if (plateClickTimer) { clearTimeout(plateClickTimer); plateClickTimer = null; }
  showPlateTool("gear");
});
document.getElementById("plate-regen").addEventListener("click", (e) => {
  e.stopPropagation();
  hidePlateTools();
  postRepaint(null);
});
document.getElementById("plate-gear").addEventListener("click", (e) => {
  e.stopPropagation();
  hidePlateTools();
  openRepaintDialog();
});
document.getElementById("repaint-go").addEventListener("click", () => {
  const prompt = document.getElementById("repaint-input").value.trim();
  closeRepaintDialog();
  postRepaint(prompt || null);
});
document.getElementById("repaint-close").addEventListener("click", closeRepaintDialog);
document.getElementById("repaint-panel").addEventListener("click", (e) => {
  if (e.target.id === "repaint-panel") closeRepaintDialog(); // backdrop closes
});

function renderKeepsakes(items) {
  const box = document.getElementById("keepsakes");
  box.innerHTML = "";
  if (!items || !items.length) {
    const p = document.createElement("p");
    p.className = "empty-note";
    p.textContent = "your satchel is empty just now — keepsakes gather as you wander.";
    box.appendChild(p);
    return;
  }
  for (const it of items) box.appendChild(keepsakeCard(it));
}

function keepsakeCard(it) {
  const card = document.createElement("div");
  card.className = "specimen";
  const mount = document.createElement("div");
  mount.className = "mount";
  mount.innerHTML = keepsakeGlyph(it.name || "");
  card.appendChild(mount);
  const body = document.createElement("div");
  body.className = "s-body";
  const name = document.createElement("div");
  name.className = "s-name";
  name.textContent = it.name || "a keepsake"; // real item name (never an id)
  body.appendChild(name);
  const desc = document.createElement("div");
  desc.className = "s-desc";
  // The item's own remembered description (examined/authored detail from
  // the snapshot card, SPEC 2026-07-07 criterion 4); the generic caption
  // pool remains only as the fallback for detail-less things.
  desc.textContent = it.detail || keepsakeCaption(it.name || "");
  body.appendChild(desc);
  const tag = document.createElement("span");
  tag.className = "s-tag";
  tag.textContent = "a keepsake";
  body.appendChild(tag);
  card.appendChild(body);
  return card;
}

function renderCollection(journal) {
  // The satchel's right page: your dream journal, oldest first (real
  // entries written when you leave the dream). A dashed not-yet slot when
  // the book is still blank.
  const box = document.getElementById("collection");
  box.innerHTML = "";
  if (!journal || !journal.length) {
    const slot = document.createElement("div");
    slot.className = "slot";
    slot.innerHTML =
      '<div class="slot-label">unwritten</div>' +
      '<div class="slot-note">the book waits for your first waking</div>';
    box.appendChild(slot);
    return;
  }
  for (const entry of journal) {
    const card = document.createElement("div");
    card.className = "journal-entry";
    const p = document.createElement("p");
    p.textContent = entry.text || "";
    card.appendChild(p);
    box.appendChild(card);
  }
}

// Deterministic per-item flourish when an item carries no detail text: the
// mount glyph + caption are a stable, generic keepsake presentation keyed
// by the name. They never fabricate item-specific facts.
function hashName(s) {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
  return h;
}

function keepsakeCaption(name) {
  const pool = [
    "carried with you, and kept.",
    "a small thing, and yours.",
    "kept for the comfort of it.",
    "worn smooth by the carrying.",
  ];
  return pool[hashName(name) % pool.length];
}

function keepsakeGlyph(name) {
  // One of a few gentle amber SVGs (generic, parameterized by the name), pressed
  // into the mount like a specimen. Name is used only to pick a shape, never
  // interpolated into markup.
  const glyphs = [
    '<svg width="88" height="88" viewBox="0 0 120 120" aria-hidden="true"><circle cx="60" cy="60" r="40" fill="none" stroke="#c8a06e" stroke-width="14" stroke-dasharray="11 9"/><circle cx="60" cy="60" r="32" fill="#e7c791" stroke="#a97b3e" stroke-width="2.5"/><circle cx="60" cy="60" r="10" fill="#efe8d6" stroke="#a97b3e" stroke-width="2.5"/></svg>',
    '<svg width="88" height="88" viewBox="0 0 120 120" aria-hidden="true"><path d="M60 20 C 32 42, 32 82, 60 100 C 88 82, 88 42, 60 20 Z" fill="#dfe7cf" stroke="#8aa07f" stroke-width="2.5"/><path d="M60 28 L60 96" stroke="#8aa07f" stroke-width="2"/></svg>',
    '<svg width="88" height="88" viewBox="0 0 120 120" aria-hidden="true"><circle cx="60" cy="60" r="30" fill="#fbe6b6" stroke="#c8a06e" stroke-width="2.5"/><circle cx="60" cy="60" r="12" fill="#fff4d8"/><path d="M60 12 L60 30 M60 90 L60 108 M12 60 L30 60 M90 60 L108 60" stroke="#c8a06e" stroke-width="2.5" stroke-linecap="round"/></svg>',
  ];
  return glyphs[hashName(name) % glyphs.length];
}

// ---- slot picker (toon-slot-management spec, 2026-05-07) -------------
//
// Toggles the slots panel; fetches /api/slots and renders one row per
// slot with the appropriate action button. Create / claim / kick all
// re-fetch and re-render. After a successful claim or create, the
// player reconnects the WS so the new connection's session→toon
// resolution picks up the new claim.

async function fetchDreamer() {
  const r = await fetch("api/dreamer", { credentials: "same-origin" });
  if (!r.ok) {
    systemLine(`(could not open your dreamer: ${r.status})`);
    return null;
  }
  return r.json();
}

async function postSlotAction(slot, action, body) {
  const r = await fetch(`api/slots/${slot}/${action}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    credentials: "same-origin",
    body: body ? JSON.stringify(body) : null,
  });
  if (!r.ok) {
    let detail = `${r.status}`;
    try {
      const j = await r.json();
      if (j.detail) detail = j.detail;
    } catch (_) {}
    systemLine(`(${detail})`);
    return null;
  }
  return r.json();
}

// "Your dreamer" (SPEC 2026-09-27 criterion 5): an account's own toon(s),
// with enter / rest / delete, and a create form when it may make one.
async function renderSlots() {
  const data = await fetchDreamer();
  const list = document.getElementById("slots-list");
  const form = document.getElementById("dreamer-form");
  list.innerHTML = "";
  if (!data) return null;
  for (const t of data.toons) {
    const li = document.createElement("li");
    li.className = "slot-row";
    li.appendChild(toonFace(t.portrait_url));
    const name = document.createElement("strong");
    name.textContent = t.name;
    li.appendChild(name);
    const state = document.createElement("em");
    state.textContent = t.claimed_by_me ? " (here now)" : t.kicked_at ? " (resting)" : "";
    li.appendChild(state);
    const main = document.createElement("button");
    main.type = "button";
    if (t.claimed_by_me) {
      main.textContent = "rest";
      main.onclick = () => kickSlot(t.slot);
    } else {
      main.textContent = "enter";
      main.onclick = () => claimSlot(t.slot);
    }
    li.appendChild(main);
    const del = document.createElement("button");
    del.type = "button";
    del.textContent = "delete";
    del.className = "slot-delete";
    del.onclick = () => askDelete(t);
    li.appendChild(del);
    list.appendChild(li);
  }
  form.classList.toggle("hidden", !data.can_create);
  document.getElementById("slots-title").textContent =
    data.toons.length > 1 ? "your dreamers" : "your dreamer";
  return data;
}

document.getElementById("dreamer-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const form = ev.target;
  const err = form.querySelector(".door-error");
  err.hidden = true;
  const f = new FormData(form);
  const r = await fetch("api/dreamer/create", {
    method: "POST",
    headers: { "content-type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify({ name: (f.get("name") || "").trim(),
                           appearance_seed: (f.get("appearance_seed") || "").trim() }),
  });
  if (!r.ok) {
    let detail = "that didn't work";
    try { detail = (await r.json()).detail || detail; } catch (_) {}
    err.textContent = detail;
    err.hidden = false;
    return;
  }
  form.reset();
  reconnectAfterSlotChange();
});

async function claimSlot(slot) {
  const result = await postSlotAction(slot, "claim", null);
  if (result) reconnectAfterSlotChange();
}

async function kickSlot(slot) {
  const result = await postSlotAction(slot, "kick", null);
  if (result) {
    // Resting the toon you play is leaving the dream (the server marks the
    // session left): stay on "your dreamer" rather than reconnecting.
    awaitingPick = true;
    if (ws) { try { ws.close(); } catch (_) {} }
    enterPicker();
  }
}

// Your account (criterion 2): change password, sign out.
document.getElementById("password-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const form = ev.target;
  const err = form.querySelector(".door-error");
  const f = new FormData(form);
  const r = await fetch("api/account/password", {
    method: "POST",
    headers: { "content-type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify({ old: f.get("old"), new: f.get("new") }),
  });
  let msg = "your password is changed";
  if (!r.ok) {
    msg = "that didn't work";
    try { msg = (await r.json()).error || msg; } catch (_) {}
  } else {
    form.reset();
  }
  err.textContent = msg;
  err.hidden = false;
});

async function signOut() {
  // Rest the toon first (so its journal is written), then end the session.
  awaitingPick = true; // no reconnect while we go
  try { await fetch("api/session/leave", { method: "POST", credentials: "same-origin" }); } catch (_) {}
  try { await fetch("api/logout", { method: "POST", credentials: "same-origin" }); } catch (_) {}
  location.replace(document.baseURI);
}
document.getElementById("sign-out").addEventListener("click", signOut);
document.getElementById("awake-signout").addEventListener("click", signOut);

let pendingDelete = null;
function askDelete(t) {
  // A storybook confirm, not a browser dialog (criterion 8).
  pendingDelete = t;
  document.getElementById("delete-confirm-text").textContent =
    `Let ${t.name} go for good? This cannot be undone.`;
  document.getElementById("delete-confirm").classList.remove("hidden");
}
document.getElementById("delete-no").addEventListener("click", () => {
  pendingDelete = null;
  document.getElementById("delete-confirm").classList.add("hidden");
});
document.getElementById("delete-yes").addEventListener("click", async () => {
  const t = pendingDelete;
  pendingDelete = null;
  document.getElementById("delete-confirm").classList.add("hidden");
  if (!t) return;
  const result = await postSlotAction(t.slot, "delete", null);
  if (result) await renderSlots();
});

function reconnectAfterSlotChange() {
  // Any slot change (claim / create / switch / wake) re-enters as the new toon
  // with a CLEAN log: close the current socket while suppressing its onclose
  // auto-reconnect, then connect fresh (no ?since, so no replayed history).
  // (A transient network drop still auto-resumes via onclose -> connect(true).)
  document.getElementById("slots-panel").classList.add("hidden");
  awaitingPick = false;
  dreamingElsewhere = false; // re-entering here takes the toon back
  journalBeatShown = false; // entering as a toon: its beat may show once
  if (ws) {
    const old = ws;
    ws = null;
    try { old.onclose = null; old.close(); } catch (_) {}
  }
  connect(false);
}

async function openDreamerPanel() {
  document.getElementById("slots-panel").classList.remove("hidden");
  await renderSlots();
}
document.getElementById("awake-dreamer").addEventListener("click", openDreamerPanel);

document.getElementById("slots-toggle").addEventListener("click", async () => {
  const panel = document.getElementById("slots-panel");
  const opening = panel.classList.contains("hidden");
  panel.classList.toggle("hidden");
  if (opening) await renderSlots();
});

document.getElementById("slots-close").addEventListener("click", () => {
  document.getElementById("slots-panel").classList.add("hidden");
});

// ---- how to dream: the first-visit help leaf ----------------------------
// A static authored book page (index.html) explaining speaking, verbs and
// objects, exits, the satchel, and leaving/picking a toon. Auto-shown ONCE
// per browser at the picker (the "you've just arrived" beat), reopenable
// anytime from the footer's ? affordance. One click dismisses it; it never
// gates input beyond being an overlay you close.

function openHelp() {
  document.getElementById("help-panel").classList.remove("hidden");
}

function closeHelp() {
  document.getElementById("help-panel").classList.add("hidden");
}

function maybeShowFirstVisitHelp() {
  // localStorage carries the once-per-browser memory; a sandboxed context
  // (storage denied) fails open to showing it each arrival, which is the
  // gentler failure for a help page.
  let seen = null;
  try { seen = localStorage.getItem("dd-help-seen"); } catch (_) {}
  if (seen) return;
  try { localStorage.setItem("dd-help-seen", "1"); } catch (_) {}
  openHelp();
}

document.getElementById("help-toggle").addEventListener("click", openHelp);
document.getElementById("help-close").addEventListener("click", closeHelp);
document.getElementById("help-panel").addEventListener("click", (e) => {
  if (e.target.id === "help-panel") closeHelp(); // click the backdrop to close
});

// "Leave the dream": a brief wake beat, release this session's toon, and
// wake on the page between dreams (rather than the old no-op logout POST).
function enterPicker() {
  awaitingPick = true;
  clearSceneAndLog();
  showAwake();
  maybeShowFirstVisitHelp();
}

async function showAwake() {
  // Awake (playtest 2026-09-28: leaving used to show the empty scene, with
  // a live input box): the village seen from outside, where your dreamer is,
  // and the way back in. With no dreamer yet, the panel opens on its form.
  document.body.classList.add("awake");
  document.getElementById("room-title").textContent = "awake";
  document.getElementById("folio").textContent = "outside the dream";
  document.getElementById("room-bg").src = assetUrl("assets/door-village.png");
  const text = document.getElementById("awake-text");
  const back = document.getElementById("awake-return");
  text.textContent = "";
  back.hidden = true;
  const data = await renderSlots();
  if (!document.body.classList.contains("awake")) return; // stepped back in meanwhile
  const dreamers = (data && data.toons) || [];
  back.hidden = false;
  if (dreamers.length === 1) {
    const t = dreamers[0];
    text.textContent = `You are awake. ${t.name} is resting in the village, ` +
      "which keeps its own hours while you are away.";
    back.textContent = "step back in";
    back.onclick = () => claimSlot(t.slot);
  } else if (dreamers.length) {
    text.textContent = "You are awake. Your dreamers are resting in the village, " +
      "which keeps its own hours while you are away.";
    back.textContent = "choose a dreamer";
    back.onclick = openDreamerPanel;
  } else {
    text.textContent = "The village is just past this page. " +
      "Make your dreamer, and step inside.";
    back.textContent = "make your dreamer";
    back.onclick = openDreamerPanel;
    document.getElementById("slots-panel").classList.remove("hidden");
  }
}

document.getElementById("leave-dream").addEventListener("click", async () => {
  awaitingPick = true;
  systemLine("you wake...");
  try {
    await fetch("api/session/leave", { method: "POST", credentials: "same-origin" });
  } catch (_) {}
  if (ws) { try { ws.close(); } catch (_) {} }
  enterPicker();
});

connect(false);
