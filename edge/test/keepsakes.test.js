// The keepsakes view on the asleep page (SPEC 2026-09-27 criterion 16).

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { handle, sha256hex, cookieValue, keepsakesHtml } from "../src/worker.js";

const TEMPLATE = readFileSync(new URL("../public/daydream/_edge/asleep.html", import.meta.url), "utf8");
const TOKEN = "tok-abc_123";

async function envWith({ expires = "2099-01-01T00:00:00Z", portrait = true } = {}) {
  const hash = await sha256hex(TOKEN);
  const kv = {
    state: JSON.stringify({ state: "asleep", note: "back soon", since: null }),
    passes: JSON.stringify({ [hash]: { account: "a-1", expires } }),
    "keepsakes:a-1": JSON.stringify({
      display_name: "Robin <A>", portrait,
      toons: [{ name: "Mira", journal: [{ text: "I mended a clock." }, { text: "Tace smiled." }],
                book: { title: "Book of Stray Minutes", found: 2, total: 150,
                        pages: [{ title: "Dawn", entries: [{ name: "a dewdrop", text: "caught at six" }] }] } }],
    }),
    chronicle: JSON.stringify([{ day: 3, text: "The clock was mended by Mira." }]),
    "portrait:a-1": new Uint8Array([137, 80, 78, 71]).buffer,
  };
  return {
    BASE: "/daydream/", PUBLIC_HOST: "www.eidolon.com", OPERATOR: "Peter",
    ORIGIN: "https://daydream-origin.eidolon.com",
    STATE: { get: async (k, opts) => kv[k] ?? null },
    ASSETS: { fetch: async () => new Response(TEMPLATE) },
  };
}

const page = (cookie) => new Request("https://www.eidolon.com/daydream/", {
  headers: { accept: "text/html", ...(cookie ? { cookie } : {}) },
});

test("a recognized friend sees their own keepsakes, escaped", async () => {
  const r = await handle(page(`other=1; dd_session_prod=${TOKEN}`), await envWith());
  const html = await r.text();
  assert.match(html, /While you wait, Robin &lt;A&gt;/);
  assert.match(html, /Mira's journal/);
  assert.ok(html.indexOf("Tace smiled.") < html.indexOf("I mended a clock."), "newest first");
  assert.match(html, /2 of 150 found/);
  assert.match(html, /Day 3: The clock was mended by Mira\./);
  assert.match(html, /src="\/daydream\/_edge\/portrait"/);
});

test("no cookie, an unknown token, or an expired pass: only the notice", async () => {
  for (const cookie of [null, "dd_session_prod=someone-else"]) {
    const html = await (await handle(page(cookie), await envWith())).text();
    assert.doesNotMatch(html, /While you wait/);
    assert.match(html, /Signed in on this device lately/);
  }
  const expired = await envWith({ expires: "2000-01-01T00:00:00Z" });
  const html = await (await handle(page(`dd_session_prod=${TOKEN}`), expired)).text();
  assert.doesNotMatch(html, /While you wait/);
});

test("the portrait is served only to its owner", async () => {
  const e = await envWith();
  const url = "https://www.eidolon.com/daydream/_edge/portrait";
  let r = await handle(new Request(url, { headers: { cookie: `dd_session_prod=${TOKEN}` } }), e);
  assert.equal(r.status, 200);
  assert.equal(r.headers.get("content-type"), "image/png");
  r = await handle(new Request(url), e);
  assert.equal(r.status, 404);
});

test("cookie parsing and hashing", async () => {
  assert.equal(cookieValue("a=1; dd_session_prod=x=y; b=2", "dd_session_prod"), "x=y");
  assert.equal(cookieValue("", "x"), null);
  assert.equal(await sha256hex("abc"),
    "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
});

test("keepsakesHtml escapes everything it is given", () => {
  const html = keepsakesHtml({ entry: { display_name: "<script>", toons: [{ name: "<b>",
    journal: [{ text: "<img onerror=x>" }] }] }, chronicle: [] }, "/daydream/");
  assert.doesNotMatch(html, /<script>|<img onerror/);
});
