// Unit tests for the edge Worker (SPEC 2026-09-27 criteria 14-15), run with
// `node --test edge/test/` (also from tier_short when node is present). The
// origin and KV are mocked; the Worker's own logic is real.

import { test, beforeEach } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { handle, rewriteLocation, upstreamHeaders, escapeHtml, stripAccessCookies }
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
