// A shared link while the village sleeps: the asleep page unfurls like the
// door (its preview tags, a 200 to a link-preview fetcher), and the card and
// icons come from KV, where the keepsakes sync left them.

import { test, beforeEach } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { handle, doorPreview, previewHtml, isLinkPreview } from "../src/worker.js";

const TEMPLATE = readFileSync(new URL("../public/daydream/_edge/asleep.html", import.meta.url), "utf8");
const CARD = new Uint8Array([0xff, 0xd8, 0xff, 0xe0]).buffer;
const ICON = new Uint8Array([137, 80, 78, 71]).buffer;
const IMESSAGE = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 " +
  "(KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1 facebookexternalhit/1.1 " +
  "Facebot Twitterbot/1.0";
const SAFARI = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 " +
  "(KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1";

const DOOR = {
  title: "The Village of Lost Hours", invite_title: "An invitation to The Village of Lost Hours",
  lede: "A small storybook village, kept for friends.", card: "assets/card-village.jpg",
  card_alt: "A watercolour of the village",
  icons: { icon: "assets/icon-32.png", "apple-touch-icon": "assets/icon-180.png" },
  assets: ["assets/card-village.jpg", "assets/icon-180.png", "assets/icon-32.png"],
};

let originCalls;

beforeEach(() => {
  originCalls = 0;
  globalThis.fetch = async () => {
    originCalls += 1;
    throw new Error("the box is off");
  };
});

function env({ state = "asleep", door = DOOR, assets = true } = {}) {
  const kv = {
    state: JSON.stringify({ state, note: "back soon", since: null }),
    ...(door ? { door: typeof door === "string" ? door : JSON.stringify(door) } : {}),
    ...(assets ? { "asset:assets/card-village.jpg": CARD, "asset:assets/icon-180.png": ICON,
                   "asset:assets/icon-32.png": ICON } : {}),
  };
  return {
    ORIGIN: "https://daydream-origin.example.com", PUBLIC_HOST: "www.example.com",
    BASE: "/daydream/", OPERATOR: "the Night Warden",
    STATE: { get: async (k) => kv[k] ?? null },
    ASSETS: { fetch: async () => new Response(TEMPLATE) },
  };
}

const get = (path, { ua = SAFARI, accept = "text/html", method = "GET" } = {}) =>
  new Request("https://www.example.com/daydream" + path,
    { method, headers: { "user-agent": ua, accept } });

function meta(html, key) {
  const m = html.match(new RegExp(`<meta (?:property|name)="${key}" content="([^"]*)">`));
  return m && m[1];
}

test("iMessage's fetcher is a link preview; Safari is a person", () => {
  assert.equal(isLinkPreview(get("/", { ua: IMESSAGE })), true);
  assert.equal(isLinkPreview(get("/", { ua: "Slackbot-LinkExpanding 1.0" })), true);
  assert.equal(isLinkPreview(get("/")), false);
});

test("asleep, a shared link unfurls like the door, with a 200 for the fetcher", async () => {
  const r = await handle(get("/", { ua: IMESSAGE, accept: "*/*" }), env());
  assert.equal(r.status, 200);
  const html = await r.text();
  assert.equal(meta(html, "og:title"), "The Village of Lost Hours");
  assert.equal(meta(html, "og:description"), "A small storybook village, kept for friends.");
  assert.equal(meta(html, "og:image"), "https://www.example.com/daydream/assets/card-village.jpg");
  assert.equal(meta(html, "twitter:image"), meta(html, "og:image"));
  assert.equal(meta(html, "twitter:card"), "summary_large_image");
  assert.match(html, /<link rel="apple-touch-icon" href="https:\/\/www\.example\.com\/daydream\/assets\/icon-180\.png">/);
  assert.match(html, /is asleep/);
  assert.doesNotMatch(html, /\{\{/);
});

test("an invite link shared while asleep previews as an invitation", async () => {
  const html = await (await handle(get("/invite/amber-thimble", { ua: IMESSAGE }), env())).text();
  assert.equal(meta(html, "og:title"), "An invitation to The Village of Lost Hours");
  assert.doesNotMatch(html, /amber-thimble/);
});

test("a person still gets the 503 asleep page, with the same tags", async () => {
  const r = await handle(get("/"), env());
  assert.equal(r.status, 503);
  assert.equal(meta(await r.text(), "og:title"), "The Village of Lost Hours");
});

test("the card and icons are served from KV while the origin cannot answer", async () => {
  for (const state of ["asleep", "awake"]) {  // a planned sleep, and an outage
    const r = await handle(get("/assets/card-village.jpg", { ua: IMESSAGE, accept: "*/*" }),
      env({ state }));
    assert.equal(r.status, 200, state);
    assert.equal(r.headers.get("content-type"), "image/jpeg");
    assert.deepEqual(new Uint8Array(await r.arrayBuffer()), new Uint8Array(CARD));
  }
  const icon = await handle(get("/assets/icon-180.png", { method: "HEAD" }), env());
  assert.equal(icon.status, 200);
  assert.equal(icon.headers.get("content-type"), "image/png");
});

test("an image the edge does not hold, or any other asset, is still asleep", async () => {
  for (const path of ["/assets/door-village.png", "/assets/main.js"]) {
    const r = await handle(get(path, { ua: IMESSAGE, accept: "*/*" }), env());
    assert.equal(r.status, 503, path);
    assert.equal((await r.json()).asleep, true);
  }
});

test("the API stays 503 JSON for a link-preview fetcher", async () => {
  const r = await handle(get("/api/me", { ua: IMESSAGE, accept: "*/*" }), env());
  assert.equal(r.status, 503);
  assert.equal((await r.json()).asleep, true);
});

test("nothing synced, or a malformed record: the page as before, no preview tags", async () => {
  for (const door of [null, "not json", JSON.stringify({ lede: "no title" })]) {
    const html = await (await handle(get("/", { ua: IMESSAGE }), env({ door }))).text();
    assert.equal(meta(html, "og:title"), null, String(door));
    assert.match(html, /is asleep/);
    assert.doesNotMatch(html, /\{\{/);
  }
});

test("only images the edge holds are named; the words are escaped", async () => {
  const d = await doorPreview(env({ door: { ...DOOR, title: `Lost "Hours" <&>`,
    card: "../secret.jpg", assets: ["assets/icon-32.png", "/etc/passwd"] } }));
  assert.equal(d.card, "");
  assert.deepEqual(d.icons, { icon: "assets/icon-32.png" });
  const html = previewHtml(d, env(), "/");
  assert.equal(meta(html, "og:title"), "Lost &quot;Hours&quot; &lt;&amp;&gt;");
  assert.equal(meta(html, "og:image"), null);
  assert.doesNotMatch(html, /apple-touch-icon/);
});

test("awake, the preview fetcher reaches the origin like anyone", async () => {
  globalThis.fetch = async () => {
    originCalls += 1;
    return new Response("from origin", { status: 200 });
  };
  const r = await handle(get("/", { ua: IMESSAGE }), env({ state: "awake" }));
  assert.equal(r.status, 200);
  assert.equal(await r.text(), "from origin");
  assert.equal(originCalls, 1);
});
