// The daydream edge Worker (SPEC 2026-09-27 criteria 14-16; docs/GOING-LIVE.md
// section 3). It is the only always-up piece, so it owns the asleep state.
//
// Routes: www.eidolon.com/daydream* (and the apex, redirected).
// - /daydream              -> 301 /daydream/ (relative URLs need the slash)
// - apex host              -> 301 to PUBLIC_HOST
// - /daydream/_edge/*      -> this Worker's own assets (the asleep page's art)
// - /daydream/edge/status  -> {state, note, since, operator}
// - everything else        -> the origin through the Access-guarded tunnel,
//   with /daydream stripped, unless the village is asleep: the KV flag says
//   so (a planned sleep), or the origin cannot answer (a crash, the box off).
//   Asleep means the storybook page for a navigation, 503 JSON for the API,
//   and a refused WebSocket.
//
// A 503 from the app itself is the app's own answer, not sleep.

const ASLEEP_STATUSES = new Set([502, 520, 521, 522, 523, 524, 525, 526, 530]);
const ORIGIN_TIMEOUT_MS = 15000;

export default {
  async fetch(request, env) {
    return handle(request, env);
  },
  // The uptime watch (a cron trigger, wrangler.toml): a friend's "it's down"
  // should never be the first signal.
  async scheduled(event, env, ctx) {
    ctx.waitUntil(watch(env));
  },
};

// ---- the uptime watch ----------------------------------------------------------

const OUTAGES_KEPT = 20;

// While the flag says awake, probe the origin; record an unplanned outage in
// KV ("uptime": {down_since, outages: [{from, to}]}) when it starts and when it
// ends. KV is written only on a change, never on a quiet check.
export async function watch(env, now = new Date()) {
  const state = await readState(env);
  if (state.state !== "awake") return "asleep";
  let up = false;
  try {
    const r = await timedFetch(env.ORIGIN + "/healthz", { headers: accessHeaders(env) }, 8000);
    up = r.ok;
  } catch (e) {
    up = false;
  }
  let u;
  try {
    u = JSON.parse((await env.STATE.get("uptime")) || "null");
  } catch (e) {
    u = null;
  }
  if (!u || typeof u !== "object") u = { down_since: null, outages: [] };
  if (!Array.isArray(u.outages)) u.outages = [];
  const at = now.toISOString().replace(/\.\d{3}Z$/, "Z");
  if (!up && !u.down_since) {
    u.down_since = at;
    await env.STATE.put("uptime", JSON.stringify(u));
  } else if (up && u.down_since) {
    u.outages = [{ from: u.down_since, to: at }, ...u.outages].slice(0, OUTAGES_KEPT);
    u.down_since = null;
    await env.STATE.put("uptime", JSON.stringify(u));
  }
  return up ? "up" : "down";
}

export async function handle(request, env) {
  const url = new URL(request.url);
  const base = env.BASE || "/daydream/";
  const prefix = base.replace(/\/$/, "");

  if (env.PUBLIC_HOST && url.hostname !== env.PUBLIC_HOST) {
    url.hostname = env.PUBLIC_HOST;
    return Response.redirect(url.toString(), 301);
  }
  if (url.pathname === prefix) {
    url.pathname = base;
    return Response.redirect(url.toString(), 301);
  }
  if (!url.pathname.startsWith(base)) {
    // A route pattern like /daydream* also matches /daydreams: not ours.
    return fetch(request);
  }
  const rest = url.pathname.slice(prefix.length); // "/..." as the origin sees it

  if (rest === "/_edge/portrait") {
    return portrait(request, env);
  }
  if (rest.startsWith("/_edge/")) {
    return env.ASSETS.fetch(request);
  }
  const state = await readState(env);
  if (rest === "/edge/status") {
    return json(await statusBody(env, state), 200);
  }

  const isWS = (request.headers.get("upgrade") || "").toLowerCase() === "websocket";
  if (state.state === "asleep") {
    return asleep(request, env, state, rest, isWS);
  }
  let resp;
  try {
    resp = await proxy(request, env, rest + url.search, isWS);
  } catch (e) {
    return asleep(request, env, unplanned(state), rest, isWS);
  }
  if (ASLEEP_STATUSES.has(resp.status)) {
    return asleep(request, env, unplanned(state), rest, isWS);
  }
  if (isWS) return passWebSocket(resp, env, prefix);
  return rewriteResponse(resp, env, prefix);
}

// The 101 and its socket pass through minus Access's cookie; any other answer
// to an upgrade (a refusal) is an ordinary response. Node's Response rejects
// status 101, so the unit tests reach the cookie filter and the refusal path.
function passWebSocket(resp, env, prefix) {
  if (resp.status !== 101) return rewriteResponse(resp, env, prefix);
  const headers = stripAccessCookies(new Headers(resp.headers));
  return new Response(null, { status: 101, headers, webSocket: resp.webSocket });
}

// ---- state ------------------------------------------------------------------

export async function readState(env) {
  try {
    const raw = await env.STATE.get("state");
    const s = raw ? JSON.parse(raw) : null;
    if (s && (s.state === "awake" || s.state === "asleep")) return s;
  } catch (e) {
    // an unreadable flag must not keep friends out: treat as awake and let
    // the origin probe decide
  }
  return { state: "awake", note: "", since: null };
}

function unplanned(state) {
  return { state: "asleep", note: "", since: null, unplanned: true, flagged: state.state };
}

async function statusBody(env, state) {
  if (state.state === "asleep") return publicState(env, state);
  try {
    const r = await timedFetch(env.ORIGIN + "/healthz", { headers: accessHeaders(env) }, 4000);
    if (r.ok) return publicState(env, state);
  } catch (e) {
    // fall through
  }
  return publicState(env, unplanned(state));
}

// The attached instance's words ride on the flag (docs/INSTANCES.md); a flag
// without them reads as the village, as before.
export function placeOf(s) {
  const p = s && typeof s.place === "string" && s.place.trim() ? s.place.trim() : "the village";
  return p.slice(0, 80);
}

function capital(s) {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function publicState(env, s) {
  return {
    state: s.state,
    asleep: s.state === "asleep",
    note: s.note || "",
    since: s.since || null,
    unplanned: !!s.unplanned,
    operator: (typeof s.operator === "string" && s.operator) || env.OPERATOR || "",
    place: placeOf(s),
  };
}

// ---- proxy --------------------------------------------------------------------

function accessHeaders(env) {
  const h = {};
  if (env.ACCESS_CLIENT_ID) h["cf-access-client-id"] = env.ACCESS_CLIENT_ID;
  if (env.ACCESS_CLIENT_SECRET) h["cf-access-client-secret"] = env.ACCESS_CLIENT_SECRET;
  return h;
}

export function upstreamHeaders(request, env) {
  const headers = new Headers(request.headers);
  // Nothing a client sends may pose as ours.
  for (const name of [...headers.keys()]) {
    if (name.startsWith("x-daydream-") || name.startsWith("cf-access-")) headers.delete(name);
  }
  headers.set("x-daydream-client-ip", request.headers.get("cf-connecting-ip") || "unknown");
  for (const [k, v] of Object.entries(accessHeaders(env))) headers.set(k, v);
  headers.delete("host");
  return headers;
}

async function proxy(request, env, originPath, isWS) {
  const init = {
    method: request.method,
    headers: upstreamHeaders(request, env),
    redirect: "manual", // the app's redirects go to the browser, not followed here
  };
  if (!["GET", "HEAD"].includes(request.method)) init.body = request.body;
  const target = env.ORIGIN + originPath;
  if (isWS) return fetch(target, init);
  return timedFetch(target, init, ORIGIN_TIMEOUT_MS);
}

async function timedFetch(url, init, ms) {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), ms);
  try {
    return await fetch(url, { ...init, signal: ctl.signal });
  } finally {
    clearTimeout(t);
  }
}

export function rewriteResponse(resp, env, prefix) {
  const out = new Response(resp.body, resp);
  const loc = out.headers.get("location");
  if (loc) out.headers.set("location", rewriteLocation(loc, env, prefix));
  stripAccessCookies(out.headers);
  return out;
}

// Access may add its own cookie to an origin response; it is not the
// browser's business.
export function stripAccessCookies(headers) {
  const cookies = headers.getSetCookie ? headers.getSetCookie() : [];
  if (cookies.some((c) => c.startsWith("CF_"))) {
    headers.delete("set-cookie");
    for (const c of cookies) if (!c.startsWith("CF_")) headers.append("set-cookie", c);
  }
  return headers;
}

export function rewriteLocation(loc, env, prefix) {
  // The origin already answers with public-base paths (/daydream/...); this
  // is a safety net for anything that slipped through as an origin path or
  // an absolute origin URL.
  try {
    const originHost = new URL(env.ORIGIN).host;
    if (/^https?:\/\//i.test(loc)) {
      const u = new URL(loc);
      if (u.host !== originHost) return loc;
      u.protocol = "https:";
      u.host = env.PUBLIC_HOST;
      if (!u.pathname.startsWith(prefix + "/")) u.pathname = prefix + u.pathname;
      return u.toString();
    }
  } catch (e) {
    return loc;
  }
  if (loc.startsWith("/") && !loc.startsWith(prefix + "/") && loc !== prefix) {
    return prefix + loc;
  }
  return loc;
}

// ---- asleep ----------------------------------------------------------------------

function wantsHtml(request, rest) {
  if (rest.startsWith("/api/") || rest.startsWith("/cache/") || rest.startsWith("/status/")) {
    return false;
  }
  return request.method === "GET" && (request.headers.get("accept") || "").includes("text/html");
}

async function asleep(request, env, state, rest, isWS) {
  const body = publicState(env, state);
  if (isWS) {
    return new Response(`${body.place} is asleep`, { status: 503, headers: noStore() });
  }
  if (!wantsHtml(request, rest)) {
    return json(body, 503, { "retry-after": "300" });
  }
  const tpl = await env.ASSETS.fetch(new Request(new URL((env.BASE || "/daydream/") +
    "_edge/asleep.html", request.url)));
  let html = await tpl.text();
  // Function replacements: a string replacement would read `$&`, `` $` ``
  // and `$'` in player text as substitution patterns.
  const fill = {
    "{{NOTE}}": escapeHtml(body.note),
    "{{OPERATOR}}": escapeHtml(body.operator || "the person who invited you"),
    "{{SINCE}}": escapeHtml(body.since || ""),
    "{{KEEPSAKES}}": keepsakesHtml(await keepsakesFor(request, env, state),
                                   env.BASE || "/daydream/", body.place),
    "{{BASE}}": escapeHtml(env.BASE || "/daydream/"),
    "{{PLACE}}": escapeHtml(capital(body.place)),
    "{{place}}": escapeHtml(body.place),
  };
  for (const [k, v] of Object.entries(fill)) html = html.replaceAll(k, () => v);
  return new Response(html, {
    status: 503,
    headers: { ...noStore(), "content-type": "text/html; charset=utf-8", "retry-after": "300",
               ...pageHeaders() },
  });
}

// ---- keepsakes (criterion 16) ------------------------------------------------------
//
// The box pushes each account's keepsakes and a pass list (sha256 of every
// live session token -> {account, expires}) to KV when the village sleeps and
// hourly while awake (daydream/keepsakes.py, daydream/edge.py). A friend is
// recognized by hashing their session cookie: no signing key, no password
// hashes, and a revoked session simply drops out of the list at the next sync.

export function cookieValue(header, name) {
  for (const part of (header || "").split(";")) {
    const [k, ...v] = part.trim().split("=");
    if (k === name) return v.join("=");
  }
  return null;
}

export async function sha256hex(s) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

// The attached instance's session cookie (per instance since the flag names
// it: docs/INSTANCES.md), else the configured one.
export function cookieNameFor(env, state) {
  const c = state && typeof state.cookie === "string" ? state.cookie : "";
  return /^dd_session_[a-z0-9_-]{1,60}$/.test(c) ? c : (env.COOKIE_NAME || "dd_session_prod");
}

async function passFor(request, env, state) {
  const s = state || await readState(env);
  const token = cookieValue(request.headers.get("cookie"), cookieNameFor(env, s));
  if (!token || token.length > 200) return null;
  let passes = {};
  try {
    passes = JSON.parse((await env.STATE.get("passes")) || "{}");
  } catch (e) {
    return null;
  }
  const pass = passes[await sha256hex(token)];
  if (!pass || !pass.account) return null;
  if (pass.expires && Date.parse(pass.expires) <= Date.now()) return null;
  return pass;
}

export async function keepsakesFor(request, env, state) {
  const pass = await passFor(request, env, state);
  if (!pass) return null;
  try {
    const entry = JSON.parse((await env.STATE.get("keepsakes:" + pass.account)) || "null");
    if (!entry) return null;
    const chronicle = JSON.parse((await env.STATE.get("chronicle")) || "[]");
    return { entry, chronicle };
  } catch (e) {
    return null;
  }
}

async function portrait(request, env) {
  const pass = await passFor(request, env);
  const png = pass ? await env.STATE.get("portrait:" + pass.account, { type: "arrayBuffer" }) : null;
  if (!png) return new Response("", { status: 404, headers: noStore() });
  return new Response(png, { headers: { "content-type": "image/png",
                                        "cache-control": "private, no-store" } });
}

export function keepsakesHtml(k, base, place) {
  if (!k) {
    return '<p class="keepsakes-none">Signed in on this device lately? Your journal and your ' +
      "book would be waiting here.</p>";
  }
  const e = k.entry || {};
  const parts = [`<section class="keepsakes"><h2>While you wait, ${escapeHtml(e.display_name)}</h2>`];
  if (e.portrait) parts.push(`<img class="portrait" src="${escapeHtml(base)}_edge/portrait" alt="">`);
  for (const toon of e.toons || []) {
    const journal = (toon.journal || []).slice().reverse();
    if (journal.length) {
      parts.push(`<h3>${escapeHtml(toon.name)}'s journal</h3>`);
      for (const j of journal) parts.push(`<p class="entry">${escapeHtml(j.text)}</p>`);
    }
    const book = toon.book;
    if (book) {
      parts.push(`<h3>${escapeHtml(book.title)}</h3>` +
        `<p class="count">${escapeHtml(book.found)} of ${escapeHtml(book.total)} found</p>`);
      for (const page of book.pages || []) {
        if (!(page.entries || []).length) continue;
        parts.push(`<h4>${escapeHtml(page.title)}</h4>`);
        for (const it of page.entries) {
          parts.push(`<p class="entry"><b>${escapeHtml(it.name)}</b> ${escapeHtml(it.text)}</p>`);
        }
      }
    }
  }
  const chronicle = k.chronicle || [];
  if (chronicle.length) {
    parts.push(`<h3>The chronicle of ${escapeHtml(place || "the village")}</h3>`);
    for (const c of chronicle) {
      const day = Number.isInteger(c.day) && c.day > 0 ? `Day ${c.day}: ` : "";
      parts.push(`<p class="entry">${escapeHtml(day + (c.text || ""))}</p>`);
    }
  }
  parts.push("</section>");
  return parts.join("\n");
}

// ---- helpers ----------------------------------------------------------------------

function noStore() {
  return { "cache-control": "no-store" };
}

function pageHeaders() {
  return {
    "content-security-policy":
      "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; " +
      "font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; " +
      "form-action 'self'; frame-ancestors 'none'",
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "same-origin",
    "x-robots-tag": "noindex, nofollow",
  };
}

function json(obj, status, extra = {}) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { ...noStore(), "content-type": "application/json", ...extra },
  });
}

export function escapeHtml(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
