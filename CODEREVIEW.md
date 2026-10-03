## Review — 2026-10-03 (commit: 968da2b)

**Summary:** Refresh review of `origin/main..968da2b` (every file in focus): the keepsakes sync carries the door's link preview (words, card, icons) to KV; while asleep the Worker puts the door's Open Graph tags on its page, serves the card and icons from KV, and answers a link-preview fetcher with a 200; `prod check` gains "link preview". Tests: short 2089 passed, medium 2796 passed, edge 48 passed, the same after the fix. One /codefix cycle fixed the WARN (uncommitted: edge/src/worker.js, edge/test/preview.test.js). Security (/security, paths, then post-fix): 0 BLOCK / 0 WARN / 10 NOTE (9 carried, 1 new in the uptime watch, older than this change).

**External reviewers:**
None configured.

**Built-in review:**
`/code-review high`: 9 findings, 9 kept after Step 6 (merged into 1 WARN and 6 NOTEs).

### Findings

[WARN, fixed] (also claude-code) edge/src/worker.js:345 — a link-preview fetcher gets a 200 even when the edge holds no door preview, so in that case the phone builds and keeps a preview titled "daydream is asleep" (the template's `<title>`), with no card, for that URL. Before this change it got a 503 and kept a bare link, which is less misleading. The windows are real: the door reaches KV only at the hourly sync or at `prod sleep`, and `prod sleep` flips the flag to asleep (daydream/prodctl.py:724) and then rests everyone and writes journals before it syncs (prodctl.py:742), so the first sleep after a deploy serves the page without a preview for tens of seconds; an unplanned outage in the first hour after a deploy; a rollback to a release whose export has no door (the sync then deletes the key); a failing sync. The test "nothing synced, or a malformed record: the page as before" says "as before" but does not check the status, which changed from 503 to 200. (medium)
  Evidence: `const unfurl = isLinkPreview(request) && request.method === "GET" && ...` is decided before `doorPreview(env)` is read; `status: unfurl ? 200 : 503`.
  Suggested fix: read the door preview first and treat the request as an unfurl only when a preview exists (`unfurl && door`), so with nothing synced the fetcher gets what it got before (the 503 page for text/html, the 503 JSON for `*/*`). Assert the 503 in the "nothing synced" test.

[NOTE] edge/src/worker.js:323 — after the fix, every asleep request reads the `door` key before deciding, including the 503 JSON answers that never use it: a tab left on the asleep page now costs three KV reads per 30 s retry instead of two (the security pass's arithmetic: about a dozen all-day tabs exhaust the free tier's daily reads, against about seventeen before). Reading `door` only when the page renders or a fetcher could unfurl keeps the JSON answers at one read. (low)

[NOTE] (security) edge/src/worker.js:45 — older than this change: when the uptime watch's read of `uptime` throws, it treats the record as empty and writes that back, erasing the outage history, and while reads keep failing no outage opens; `prod status`'s watch line then says "no unplanned outage recorded" through a real one (its live public status still tells the truth). Skip the run on a thrown read. (low)

[NOTE] (also claude-code) edge/src/worker.js:321 — only a GET unfurls; a fetcher that sends HEAD to the page first gets the 503 JSON and may give up. The card and icons do answer HEAD. (low)

[NOTE] (claude-code) edge/src/worker.js:409 — `previewHtml` builds its URLs from `env.PUBLIC_HOST` with no fallback, while `handle()` treats it as optional; a fork without it would publish `https://undefined/...` card and icon URLs. The request's own host would do. (low)

[NOTE] (also claude-code) daydream/edge.py:247 — `DOOR_ASSET` repeats `instance._SHAPES["card_image"]` and worker.js `ASSET_PATH`; widening the card's shape in instance.py would let an instance name a card the sync then silently leaves out (prod check would catch it while asleep). (low)

[NOTE] (claude-code) edge/src/worker.js:407 — `previewHtml` rewrites door.html's preview tag set by hand, and `instance.ICONS` mirrors door.html's icon links; a tag or icon rel added to door.html is not mirrored at the edge and no test fails (a renamed icon is caught by test_auth). (low)

[NOTE] (also claude-code) daydream/keepsakes.py:153 — the door rides in the same export and bulk put as the passes, so a failure in the door path (an `InstanceError` from `instance.preview()`, a malformed `door` shape, invalid base64 rejected by the bulk API) stops the whole sync, pass revocations included. Only a bad instance.json (which also breaks the server) or a hostile service user (which can already break the sync) gets there. (low)

[NOTE] edge/src/worker.js:393 — the Worker caps each word at 200 characters, but `invite_title` and `card_alt` add a prefix to words instance.json allows at 200, so a long title or place is cut mid-word on the asleep page only. (low)

[NOTE] (claude-code) edge/src/worker.js:341 — every asleep page now waits for the `door` read after the keepsakes reads; reading both at once (Promise.all) saves a KV round trip. (low)

[NOTE] (claude-code) daydream/prodcheck.py:363 — the probe sends the iMessage user agent from the box's own address; a Cloudflare fake-bot rule would fail it on a healthy village. Real iMessage fetches also come from the sender's device, not Facebook's addresses, so such a failure probably reflects what phones see. Unverified until the deploy. (low)

Carried from 2026-10-01f (files unchanged or the finding still present; the door.html NOTE about previews while asleep is resolved by this change):

[NOTE] daydream/server.py:240 and edge/src/worker.js:343 — markers are replaced one after another, so a value containing a later marker is expanded again; on the asleep page, keepsake text containing `{{PREVIEW}}` expands into the Worker's escaped tags (harmless; the security pass confirmed nothing a player writes becomes markup). (low)
[NOTE] daydream/prodcheck.py:168 — "not run since boot" also describes a just-installed timer; a job that failed before a reboot reads ok until its next run. (low)
[NOTE] daydream/prodctl.py:909 — `prod status` makes a 10 s-timeout HTTPS probe before the Cloudflare API calls. (low)
[NOTE] tools/make_link_card.py:101 — `icons()` does not check the painting is wide enough for its square crop. (low)
[NOTE] tools/make_link_card.py:60 — the shadow is blurred twice. (low)
[NOTE] web/index.html:8 — the game page's icons are absolute URLs where base-relative would do. (low)
[NOTE] daydream/server.py:267 — a password-reset link is also `/invite/<slug>`, so it previews as an invitation (now at the edge too). (low)
[NOTE] web/assets/card-village.jpg — nothing ties the committed card to the door painting; crawler access through Cloudflare is unverified until the deploy. (low)

### Fixes Applied

- [WARN] edge/src/worker.js — the door preview is read first and a link-preview fetcher gets the 200 only when one exists; with nothing synced it gets the 503 page (text/html) or the 503 JSON (`*/*`), as before this change. edge/test/preview.test.js asserts the 503 for no record, an unparseable one and one without a title.

### Accepted Risks

- The guard is a pattern check over command text, not a sandbox: what it does not model is covered by the permission prompts and the operator.
- **A thing with a `home` handed to a DOZING dreamer** waits in their satchel until they rest (BACKLOG `dozing-handover-of-village-things`; also in SECURITY.md).
- Carried from SECURITY.md: LLM-emitted effects take an unscoped, LLM-chosen target id within each verb's allowed subset; stored prompt-injection via captured NPC memory; bootstrap `$MODEL` heredoc; `cmd_logs` path component; qpeek clone; `world reset` rm -rf operator trust; CGNAT hardcoding in tailscale mode; an account deleted mid-reply leaves the reply and its `talk:`/`rel:` records.

---
*Prior review (2026-10-01f, refresh, `62d77ef`): prod status leads with what friends see, link-preview cards and icons; 0 BLOCK / 4 WARN (all fixed in 62d77ef) / 9 NOTE.*

<!-- REVIEW_META: {"date":"2026-10-03","commit":"968da2b","reviewed_up_to":"968da2b5ca90848daa4df44122fe93f73e265dc8","base":"origin/main","tier":"refresh","block":0,"warn":1,"note":18} -->
