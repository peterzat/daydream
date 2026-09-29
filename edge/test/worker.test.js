// Unit tests for the edge Worker (SPEC 2026-09-27 criteria 14-15), run with
// `node --test edge/test/` (also from tier_short when node is present). The
// origin and KV are mocked; the Worker's own logic is real.

import { test, beforeEach } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { handle, rewriteLocation, upstreamHeaders, escapeHtml, stripAccessCookies,
  placeOf, cookieNameFor, watch }
  from "../src/worker.js";

const TEMPLATE = readFileSync(new URL("../public/daydream/_edge/asleep.html", import.meta.url), "utf8");

let calls;
let originReply;

function env(state = null) {
  return {
    ORIGIN: "https://daydream-origin.eidolon.com",
    PUBLIC_HOST: "www.eidolon.com",
    BASE: "/daydream/",
    OPERATOR: "the Night Warden",
    ACCESS_CLIENT_ID: "id.access",
    ACCESS_CLIENT_SECRET: "secret-value",
    STATE: { get: async (k) => (k === "state" && state ? JSON.stringify(state) : null) },
    ASSETS: {
      fetch: async (req) => {
        const u = new URL(req.url || req);
        if (u.pathname.endsWith("/_edge/asleep.html")) return new Response(TEMPLATE);
        return new Response("asset:" + u.pathname);
      },
    },
  };
}

beforeEach(() => {
  calls = [];
  originReply = () => new Response("from origin", { status: 200 });
  globalThis.fetch = async (url, init = {}) => {
    const u = typeof url === "string" ? url : url.url;
    calls.push({ url: u, init });
    const r = originReply(u, init);
    if (r instanceof Error) throw r;
    return r;
  };
});

const req = (path, opts = {}) =>
  new Request("https://www.eidolon.com" + path, {
    headers: { accept: "text/html", "cf-connecting-ip": "203.0.113.5", ...(opts.headers || {}) },
    method: opts.method || "GET",
    body: opts.body,
  });

test("the bare prefix and the apex redirect to the canonical base", async () => {
  let r = await handle(req("/daydream"), env());
  assert.equal(r.status, 301);
  assert.equal(r.headers.get("location"), "https://www.eidolon.com/daydream/");
  r = await handle(new Request("https://eidolon.com/daydream/x"), env());
  assert.equal(r.status, 301);
  assert.equal(r.headers.get("location"), "https://www.eidolon.com/daydream/x");
});

test("awake: the prefix is stripped and the request proxied with the service token", async () => {
  const r = await handle(req("/daydream/api/me?x=1"), env());
  assert.equal(await r.text(), "from origin");
  assert.equal(calls[0].url, "https://daydream-origin.eidolon.com/api/me?x=1");
  const h = calls[0].init.headers;
  assert.equal(h.get("cf-access-client-id"), "id.access");
  assert.equal(h.get("cf-access-client-secret"), "secret-value");
  assert.equal(h.get("x-daydream-client-ip"), "203.0.113.5");
  assert.equal(calls[0].init.redirect, "manual");
});

test("a client cannot pose as the Worker", async () => {
  const headers = upstreamHeaders(req("/daydream/", { headers: {
    "x-daydream-client-ip": "127.0.0.1", "x-daydream-anything": "1",
    "cf-access-client-id": "forged", "cf-access-client-secret": "forged" } }), env());
  assert.equal(headers.get("x-daydream-client-ip"), "203.0.113.5");
  assert.equal(headers.get("x-daydream-anything"), null);
  assert.equal(headers.get("cf-access-client-id"), "id.access");
  assert.equal(headers.get("cf-access-client-secret"), "secret-value");
});

test("the app's redirects reach the browser (not followed), inside the base", async () => {
  originReply = () => new Response(null, { status: 303, headers: { location: "/daydream/" } });
  let r = await handle(req("/daydream/api/login", { method: "POST", body: "{}" }), env());
  assert.equal(r.status, 303);
  assert.equal(r.headers.get("location"), "/daydream/");
  originReply = () => new Response(null, { status: 302, headers: { location: "/login" } });
  r = await handle(req("/daydream/x"), env());
  assert.equal(r.headers.get("location"), "/daydream/login");
});

test("Access's CF_ cookies are stripped; the app's own cookies stay", () => {
  const h = stripAccessCookies(new Headers([
    ["set-cookie", "CF_Authorization=jwt; Path=/; Secure"],
    ["set-cookie", "dd_session_prod=tok; Path=/daydream/; HttpOnly"],
    ["set-cookie", "CF_AppSession=x; Path=/"],
  ]));
  assert.deepEqual(h.getSetCookie(), ["dd_session_prod=tok; Path=/daydream/; HttpOnly"]);
});

test("a refused WebSocket upgrade reaches the client without Access's cookie", async () => {
  originReply = () => new Response("forbidden", { status: 403, headers: [
    ["set-cookie", "CF_Authorization=jwt; Path=/; Secure; SameSite=none"]] });
  const r = await handle(req("/daydream/ws", { headers: { upgrade: "websocket" } }), env());
  assert.equal(r.status, 403);
  assert.deepEqual(r.headers.getSetCookie(), []);
  assert.equal(r.headers.get("set-cookie"), null);
});

test("an HTTP response keeps the app's cookie and loses Access's", async () => {
  originReply = () => new Response("ok", { status: 200, headers: [
    ["set-cookie", "CF_Authorization=jwt; Path=/"], ["set-cookie", "dd_session_prod=t"]] });
  const r = await handle(req("/daydream/api/me"), env());
  assert.deepEqual(r.headers.getSetCookie(), ["dd_session_prod=t"]);
});

test("rewriteLocation fixes an absolute origin URL and leaves others alone", () => {
  const e = env();
  assert.equal(rewriteLocation("https://daydream-origin.eidolon.com/login", e, "/daydream"),
    "https://www.eidolon.com/daydream/login");
  assert.equal(rewriteLocation("https://example.com/x", e, "/daydream"), "https://example.com/x");
  assert.equal(rewriteLocation("/daydream/", e, "/daydream"), "/daydream/");
});

test("KV asleep: the storybook page with the note, escaped, and no origin call", async () => {
  const r = await handle(req("/daydream/"), env({ state: "asleep", note: "back <Sunday>",
    since: "2026-09-27T10:00:00Z" }));
  assert.equal(r.status, 503);
  const html = await r.text();
  assert.match(html, /The village is asleep/);
  assert.match(html, /back &lt;Sunday&gt;/);
  assert.match(html, /Send the Night Warden a note/);
  assert.match(html, /href="\/daydream\/_edge\/asleep\.css"/);
  assert.equal(calls.length, 0);
  assert.match(r.headers.get("content-security-policy"), /script-src 'self'/);
});

test("KV asleep with no operator name: the plain fallback, no title", async () => {
  const e = { ...env({ state: "asleep", note: "", since: "2026-09-27T10:00:00Z" }), OPERATOR: "" };
  const html = await (await handle(req("/daydream/"), e)).text();
  assert.match(html, /Send the person who invited you a note/);
  assert.doesNotMatch(html, /Night Warden/);
});

test("KV asleep: the API gets 503 JSON and a WebSocket is refused", async () => {
  const e = env({ state: "asleep", note: "n", since: null });
  let r = await handle(req("/daydream/api/me", { headers: { accept: "application/json" } }), e);
  assert.equal(r.status, 503);
  const body = await r.json();
  assert.equal(body.asleep, true);
  assert.equal(body.operator, "the Night Warden");
  r = await handle(req("/daydream/ws", { headers: { upgrade: "websocket" } }), e);
  assert.equal(r.status, 503);
  assert.equal(calls.length, 0);
});

for (const status of [502, 530, 522]) {
  test(`an origin ${status} (tunnel or service down) reads as asleep`, async () => {
    originReply = () => new Response("cloudflare error", { status });
    const r = await handle(req("/daydream/"), env());
    assert.equal(r.status, 503);
    assert.match(await r.text(), /The village is asleep/);
  });
}

test("an origin that cannot be reached at all reads as asleep", async () => {
  originReply = () => new Error("connect failed");
  const r = await handle(req("/daydream/api/me", { headers: { accept: "application/json" } }), env());
  assert.equal(r.status, 503);
  assert.equal((await r.json()).unplanned, true);
});

test("the app's own 503 is passed through, not mistaken for sleep", async () => {
  originReply = () => new Response("daydream: web/index.html is missing", { status: 503 });
  const r = await handle(req("/daydream/"), env());
  assert.equal(r.status, 503);
  assert.equal(await r.text(), "daydream: web/index.html is missing");
});

test("edge/status reports awake only when the origin answers", async () => {
  let r = await handle(req("/daydream/edge/status"), env());
  assert.equal((await r.json()).state, "awake");
  originReply = () => new Response("", { status: 530 });
  r = await handle(req("/daydream/edge/status"), env());
  const s = await r.json();
  assert.equal(s.state, "asleep");
  assert.equal(s.unplanned, true);
});

test("the Worker's own assets are served from ASSETS", async () => {
  const r = await handle(req("/daydream/_edge/asleep.css"), env({ state: "asleep" }));
  assert.equal(await r.text(), "asset:/daydream/_edge/asleep.css");
});

test("paths that only share the prefix are not ours", async () => {
  await handle(req("/daydreams"), env());
  assert.equal(calls[0].url, "https://www.eidolon.com/daydreams");
});

test("escapeHtml", () => {
  assert.equal(escapeHtml(`<a href="x">'&`), "&lt;a href=&quot;x&quot;&gt;&#39;&amp;");
});

test("player text with $-patterns renders literally on the asleep page", async () => {
  const r = await handle(req("/daydream/"), env({ state: "asleep", note: "back $& $` $' soon" }));
  const html = await r.text();
  assert.match(html, /back \$&amp; \$` \$&#39; soon/);
  assert.doesNotMatch(html, /\{\{NOTE\}\}/);
});

test("escapeHtml keeps a zero (the book's \"0 of 150 found\")", () => {
  assert.equal(escapeHtml(0), "0");
  assert.equal(escapeHtml(null), "");
  assert.equal(escapeHtml(undefined), "");
});

// ---- instances (docs/INSTANCES.md): the attached instance's words on the flag ----

test("the flag's words: another instance sleeps in its own words", async () => {
  const e = env({ state: "asleep", note: "", since: null, place: "the great underground empire",
                  operator: "the Dungeon Master", cookie: "dd_session_prod_zork" });
  let r = await handle(req("/daydream/"), e);
  const html = await r.text();
  assert.match(html, /The great underground empire is asleep/);
  assert.match(html, /when the great underground empire does/);
  assert.match(html, /Send the Dungeon Master a note/);
  assert.doesNotMatch(html, /The village is asleep|Night Warden/);
  r = await handle(req("/daydream/api/me", { headers: { accept: "application/json" } }), e);
  const body = await r.json();
  assert.equal(body.place, "the great underground empire");
  assert.equal(body.operator, "the Dungeon Master");
  r = await handle(req("/daydream/ws", { headers: { upgrade: "websocket" } }), e);
  assert.equal(await r.text(), "the great underground empire is asleep");
});

test("the flag's words are escaped, and a flag without them reads as the village", async () => {
  const e = env({ state: "asleep", note: "", since: null, place: "the <b>vault</b>" });
  const html = await (await handle(req("/daydream/"), e)).text();
  assert.match(html, /The &lt;b&gt;vault&lt;\/b&gt; is asleep/);
  assert.equal(placeOf({}), "the village");
  assert.equal(placeOf({ place: "  " }), "the village");
});

test("the pass cookie is the flag's when it is a session cookie name, else the configured one", () => {
  const e = env();
  assert.equal(cookieNameFor(e, { cookie: "dd_session_prod_zork" }), "dd_session_prod_zork");
  assert.equal(cookieNameFor(e, { cookie: "evil; path=/" }), "dd_session_prod");
  assert.equal(cookieNameFor(e, {}), "dd_session_prod");
  assert.equal(cookieNameFor({ ...e, COOKIE_NAME: "dd_session_x" }, null), "dd_session_x");
});

test("the app's security headers reach the browser through the proxy unchanged", async () => {
  const appHeaders = {
    "content-security-policy": "default-src 'self'; frame-ancestors 'none'",
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "same-origin",
    "permissions-policy": "camera=(), microphone=(), geolocation=()",
  };
  originReply = () => new Response("<html></html>", { status: 200, headers: appHeaders });
  const r = await handle(req("/daydream/"), env({ state: "awake", note: "", since: null }));
  assert.equal(r.status, 200);
  for (const [k, v] of Object.entries(appHeaders)) assert.equal(r.headers.get(k), v, k);
});

// ---- the uptime watch ----

function kvEnv(initial) {
  const store = new Map(Object.entries(initial));
  const puts = [];
  const e = env();
  e.STATE = {
    get: async (k) => (store.has(k) ? store.get(k) : null),
    put: async (k, v) => { store.set(k, v); puts.push(k); },
  };
  return { e, store, puts };
}

test("the watch records an outage's start and end, and writes nothing on a quiet check", async () => {
  const awake = JSON.stringify({ state: "awake", note: "", since: null });
  const { e, store, puts } = kvEnv({ state: awake });
  originReply = () => new Response("ok", { status: 200 });
  assert.equal(await watch(e, new Date("2026-09-28T10:00:00Z")), "up");
  assert.deepEqual(puts, []);
  originReply = () => new Error("tunnel down");
  assert.equal(await watch(e, new Date("2026-09-28T10:05:00Z")), "down");
  assert.equal(JSON.parse(store.get("uptime")).down_since, null);  // only suspected
  assert.equal(await watch(e, new Date("2026-09-28T10:10:00Z")), "down");  // two in a row: open
  assert.equal(await watch(e, new Date("2026-09-28T10:15:00Z")), "down");  // still open: quiet
  assert.equal(puts.length, 2);
  assert.equal(JSON.parse(store.get("uptime")).down_since, "2026-09-28T10:05:00Z");
  originReply = () => new Response("ok", { status: 200 });
  await watch(e, new Date("2026-09-28T10:20:00Z"));
  const u = JSON.parse(store.get("uptime"));
  assert.equal(u.down_since, null);
  assert.deepEqual(u.outages, [{ from: "2026-09-28T10:05:00Z", to: "2026-09-28T10:20:00Z" }]);
  assert.equal(puts.length, 3);
  await watch(e, new Date("2026-09-28T10:25:00Z"));
  assert.equal(puts.length, 3);
});

test("one failed probe and then an answer records no outage (a planned restart)", async () => {
  const { e, store } = kvEnv({ state: JSON.stringify({ state: "awake", note: "", since: null }) });
  originReply = () => new Error("restarting");
  await watch(e, new Date("2026-09-28T10:05:00Z"));
  originReply = () => new Response("ok", { status: 200 });
  assert.equal(await watch(e, new Date("2026-09-28T10:10:00Z")), "up");
  const u = JSON.parse(store.get("uptime"));
  assert.equal(u.down_since, null);
  assert.equal(u.suspect_since, null);
  assert.deepEqual(u.outages, []);
});

test("an open outage closes when the flag goes asleep, and a suspicion does not outlive a sleep", async () => {
  const awake = JSON.stringify({ state: "awake", note: "", since: null });
  const { e, store } = kvEnv({ state: awake });
  originReply = () => new Error("the box is off");
  await watch(e, new Date("2026-09-28T10:05:00Z"));
  await watch(e, new Date("2026-09-28T10:10:00Z"));
  store.set("state", JSON.stringify({ state: "asleep", note: "back Sunday", since: null }));
  assert.equal(await watch(e, new Date("2026-09-28T10:15:00Z")), "asleep");
  let u = JSON.parse(store.get("uptime"));
  assert.equal(u.down_since, null);
  assert.deepEqual(u.outages, [{ from: "2026-09-28T10:05:00Z", to: "2026-09-28T10:15:00Z",
    ended: "asleep" }]);
  // Awake again: a failure seen just before a sleep is not carried past it.
  store.set("state", awake);
  await watch(e, new Date("2026-09-29T09:00:00Z"));
  store.set("state", JSON.stringify({ state: "asleep", note: "", since: null }));
  await watch(e, new Date("2026-09-29T09:05:00Z"));
  store.set("state", awake);
  await watch(e, new Date("2026-09-29T09:10:00Z"));
  u = JSON.parse(store.get("uptime"));
  assert.equal(u.down_since, null);
  assert.equal(u.suspect_since, "2026-09-29T09:10:00Z");
  assert.equal(u.outages.length, 1);
});

test("the watch leaves a planned sleep alone", async () => {
  const { e, puts } = kvEnv({ state: JSON.stringify({ state: "asleep", note: "", since: null }) });
  originReply = () => new Error("down on purpose");
  assert.equal(await watch(e), "asleep");
  assert.deepEqual(puts, []);
  assert.equal(calls.length, 0);
});

test("plain http is sent to https before anything else (security review 2026-09-29)", async () => {
  const r = await handle(new Request("http://www.eidolon.com/daydream/login?x=1"), env());
  assert.equal(r.status, 301);
  assert.equal(r.headers.get("location"), "https://www.eidolon.com/daydream/login?x=1");
  assert.equal(calls.length, 0);
});

test("an encoded slash never reaches the origin (the rate rule reads the path as written)", async () => {
  for (const p of ["/daydream/api%2flogin", "/daydream/api%2Finvite%2Fredeem", "/daydream/assets%5cx"]) {
    const r = await handle(req(p, { method: "POST" }), env());
    assert.equal(r.status, 400, p);
  }
  assert.equal(calls.length, 0);
});

test("the status probe never follows a redirect with the token attached", async () => {
  await handle(req("/daydream/edge/status"), env());
  const probe = calls.find((c) => c.url.endsWith("/healthz"));
  assert.ok(probe);
  assert.equal(probe.init.redirect, "manual");
});
