## Review — 2026-09-28c (commit: cca5c50) — full

**Summary:** Pre-push review of the first prod evening's turn against origin/main (`9b738f9`): 5 commits, 26 files. The SPA's notes (answers resting on a paragraph top, scroll cues, the awake page, the dreamer panel), the server's own log lines, the arrival replay window and ambient beats, the iPad Safari fit, and a screen and engine layout matrix. Three fresh reviewers read it (the SPA; the server and docs; the two later commits), each reproducing its findings in a browser or against the app; every finding below was re-checked against the code. Baseline: medium tier 1709 passed; after two /codefix passes 1725 passed, 2 skipped (WebKit needs system libraries on this box). /security of `d9a8ac6..7f9af5a` and then of `7f9af5a..0aa9792`: 0 BLOCK / 0 WARN / 1 NOTE each (the timer units awaiting the operator's installer run); the second scan also found the cycle-2 correctness gap below.

**External reviewers:**
None configured.

### Findings

No BLOCK findings.

**WARN**

[WARN] web/assets/main.js:1130-1140 (revealRange) with 1157-1167 (followLog) — a new line within ACT_FOLLOW_MS of your action pulls a reader who scrolled down inside a long answer back to the answer's first line.
  Evidence: answering and answerFrom connected, so revealRange(answerFrom, el); the reader is below answerFrom's top, so the range is "out of view"; bottom - top > viewH, so target = top. Reproduced at 1280x650: scrollTop 277 (answer top), reader scrolls to 527, one unrelated say line returns it to 277.
  Suggested fix: when the range is taller than the view, keep the reader's place when it is already inside the range: target = clamp(sc.scrollTop, top, bottom - viewH) instead of top. Test: in the browser test, scroll into a long answer, append a line, the view does not move backward.

[WARN] web/assets/main.js:1606 (fetchDreamer) and 1625 (postSlotAction) with style.css (body.awake #chat hidden) — on the awake page every failure goes to the hidden #chat, so "step back in" silently does nothing (401 revoked/expired session, 503 asleep village, 404 dreamer gone); and a failed api/dreamer in showAwake reads as "no dreamer" (the "make your dreamer" text for an account that has one).
  Evidence: clearing cookies then clicking #awake-return leaves the page awake with "(401)" in the invisible chat.
  Suggested fix: a notice helper: while body.awake, write the message into a visible role="alert" line on the awake leaf (e.g. a #awake-note p), else systemLine. On a 401 from fetchDreamer/postSlotAction go to the door (location.replace(document.baseURI)); on a 503 whose JSON says asleep, show asleepText. In showAwake, data === null means "the village could not be reached just now" with the button retrying showAwake, not the no-dreamer branch. Test in tests/test_browser_flow.py: awake, cookies cleared, "step back in" lands on the door.

[WARN] web/assets/main.js:1758-1765 (delete-yes) — deleting your only dreamer while awake leaves the leaf saying "<name> is resting" with "step back in", which then claims an empty slot (404, invisible per the finding above).
  Suggested fix: after a successful delete, call showAwake() when body.awake is set (it re-reads api/dreamer and rebuilds the leaf). Test: awake, delete the dreamer, the leaf offers "make your dreamer".

[WARN] tests/test_browser_flow.py:325 — the `#verb-bar` hidden assertion in test_leaving_the_dream_wakes_on_a_page_with_the_way_back passes vacuously (clearSceneAndLog empties it, and an empty flex nav has zero height). Reclassified from NOTE (a test that proves nothing).
  Suggested fix: assert `.ribbon-wrap` is hidden instead.

[WARN] daydream/api/ws.py (_state_snapshot / the broadcast loop's re-snapshot, around lines 245 and 1100) — the arrival's cut applies only to the move's own snapshot. Every later same-room re-snapshot (object_moved from any take or drop, a state change, and toon_image_ready, which the arrival itself sets off by painting an unpainted face) replays the room's last 50 events unbounded, and renderSnapshot re-renders #chat from them, so the hours-old and ambient lines come back seconds after walking in: the playtest symptom again.
  Evidence: a scratch test moves into r-forge (the arrival snapshot omits a 2-hour-old line), then appends toon_image_ready in r-forge; the next snapshot's events include the old line (scratchpad/review-server/test_arrival_regress.py).
  Suggested fix: on an arriving snapshot, record in `view` the room, the arrival's last_seq, and the set of pre-arrival seqs the arrival replay kept (`view["arrival"] = {"room": room_id, "seq": last_seq, "kept": {e.seq for e in recent}}`). On a later non-arriving replay-recent snapshot in the same room, drop events with seq <= arrival seq that are not in kept. Do not pass skip_ambient to every re-snapshot: ambient beats the player saw live after arriving must stay. Test in tests/test_ws_limits.py: after the move, append toon_image_ready (or a take) in the room; the next snapshot still omits the old line and the pre-arrival ambient beat, and keeps a post-arrival ambient beat.

[WARN] daydream/journal.py:129, daydream/growth.py:520, daydream/skills/data.py:401, daydream/drift.py:487 — a log line prints an LLMUnavailable's message, which for a non-JSON reply carries up to 200 characters of raw model output (daydream/llm/client.py:171); the journal and growth prompts quote the player's own words, so typed text can reach the prod journal, against the "never typed text" promise (logs.py, incident.md, CLAUDE.md, tests/test_logs.py).
  Suggested fix: log the exception type only (`type(e).__name__`) at those four sites, as usage_logger already does. Test: journal.write_entry with a client raising LLMUnavailable("LLM returned non-JSON: <typed words>") logs the skip without the words.

[WARN] web/assets/style.css:658-659 and 691-692 — the vh fallback is dead where it is needed: env() inside the dvh calc makes the declaration parse-valid, so a browser with env() but not dvh (Safari 11.2-15.3, Chrome 69-107, Firefox 65-100) drops the vh line, then finds the dvh one invalid at computed-value time and gives #app.page height: auto; the input and footer fall off an unscrollable page.
  Evidence: `height: calc(100vh - 24px); height: calc(100zzz - 24px - env(...))` computes to 19px in Chromium and Firefox (676px without env()); in the app at 1133x702 the footer landed at y=838-869 with the wheel unable to scroll.
  Suggested fix: keep the vh declarations (with the env() margin) unconditional and put the two dvh height declarations inside `@supports (height: 100dvh) { ... }`. Update the comment and tests/test_layout_screens.py's static test to pin the @supports form.

[WARN] tests/test_layout_screens.py:104-110 (_scrolls_sideways) — on the mobile-emulated screens (is_mobile) Chromium widens the layout viewport to fit the content, so scrollTo(400, ...) has nothing to scroll and the check cannot fail on the phone or either iPad.
  Evidence: with the phone block's overflow-x rule and the leaf/door fixes removed (the 11px bug), the phone and both iPad tests pass; innerWidth 400, scrollWidth 400, visualViewport.width 390.
  Suggested fix: compare against the configured width: assert m["vw"] == screen.width and m["sw"] <= screen.width + 1 (keep the scroll probe for non-mobile screens).

[WARN] tests/test_layout_screens.py:113-118 (_at_the_end) and 125-128 — the door's "whole form reachable" check scrolls by script, and window.scrollTo moves an overflow: hidden viewport, so it passes when a person cannot scroll.
  Evidence: with `html { height: 100%; overflow: hidden; }` back in the desktop media, all 7 runnable cases pass; at 1133x650 on /invite a mouse wheel leaves scrollY 0 with the form's foot at 723.
  Suggested fix: scroll the way a person does (page.mouse.wheel over the page, repeated, or keyboard End) before measuring, and/or assert the scrolling element's computed overflow-y is not hidden.

[WARN] tests/test_layout_screens.py:84-86 — the engine skip reason loses its cause: Playwright's error starts with a bare "BrowserType.launch: " line, so the skip reads "(BrowserType.launch: )", and the install-deps hint is appended whatever the cause. Reclassified from NOTE (the skip reason is the only guidance an operator gets).
  Suggested fix: collapse the message's whitespace, strip the "BrowserType.launch:" prefix, keep 160 characters; add the install-deps hint only when the text mentions missing libraries or dependencies.

[WARN] docs/runbooks/incident.md ("Reading the log") — "DAYDREAM_LOG_LEVEL=WARNING in prod.env quiets everything but trouble": it sets only the daydream logger; uvicorn's own INFO lines (WebSocket accepted, connection open/closed, startup) follow uvicorn's --log-level. Reclassified from NOTE (a playbook claim an agent would act on).
  Suggested fix: "quiets the app's own lines (uvicorn's WebSocket lines follow its --log-level)".

**Re-review of the first fix pass (cycle 2), from the /security scan of 7f9af5a..0aa9792**

[WARN] daydream/api/ws.py:245-258 (_state_snapshot) — the cut is recorded only on an arriving (move) snapshot. After a fresh page load (resume_since None: an empty log) or a reconnect (?since=), view has no cut, so the next same-room re-snapshot (a take or drop, a state change, toon_image_ready from the connect's own portrait enqueue) replays the room's last 50 events however old, ambient beats included, and renderSnapshot rebuilds #chat from them: the first-evening symptom through another door.
  Evidence: scratchpad/sec-fresh/test_fresh_connect_replay.py against the real WebSocket; by reading: the fresh branch sets recent = [] and no view["arrival"], and the later branch applies a cut only when one exists.
  Suggested fix: record the cut on EVERY first snapshot of a room, not just a move: for the fresh branch (kept = empty set) and the reconnect branch (kept = the seqs it replayed; the SPA rebuilds its log from exactly those on reconnect) as well as arriving, i.e. `view["arrival"] = {"room": room_id, "seq": last_seq, "kept": {e.seq for e in recent}}` whenever resume_since is not _REPLAY_RECENT or arriving; apply it on later same-room replay-recent snapshots as now. Tests in tests/test_ws_limits.py: a fresh connect then a same-room effect re-snapshot does not bring back an old line or an old ambient beat; a reconnect then a re-snapshot keeps the replayed lines and adds nothing older.

**NOTE**

[NOTE] daydream/api/ws.py (the broadcast loop) — a toon moved by something other than its own move event (an effect relocating a player) gets no arrival cut for the new room, so its later same-room re-snapshots there still replay the last 50 lines. No such effect targets players in The Village of Lost Hours today; walking, teleports, death respawns and vehicle rides all emit the toon's own move. (From the cycle-2 /codefix report.)

[NOTE] ops/systemd/daydream-keepsakes.service, daydream-offsite.service (installed copies) — carried from SECURITY.md: the installed units still set NoNewPrivileges, so the hourly keepsakes sync fails while prod is awake and the weekly offsite will too. Needs the operator's `sudo ops/install-prod.sh`.

### Fixes Applied

All 12 WARNs, over two /codefix passes, each re-reviewed here against the code and the tests (every new test fails on the code before its fix):
- `842a856`: a reader inside a long answer keeps their place; the awake page's visible note, 401 to the door, the asleep text, "could not be reached" with "try again", and the rebuild after letting your dreamer go; the `.ribbon-wrap` assertion; the arrival's cut kept by later same-room re-snapshots (cleared on a world swap); the four log lines printing only the error type; the dvh heights in `@supports`; the layout matrix's configured-width rule for mobile screens, wheel scrolling for the door, and the real skip reason; incident.md's log-level wording. The honest width rule then found the upright iPad's leaves 12px past the screen; they hide at 900px and below.
- `cca5c50` (cycle 2): every first snapshot of a room (a move, a fresh load, a reconnect) sets the cut, not only a move.

### Accepted Risks

Carried forward (the standing register lives in SECURITY.md):

- **LLM-emitted effects take an unscoped, LLM-chosen target id** within each
  verb's allowed subset; rule-only kinds unreachable from LLM-facing dispatch.
- Stored prompt-injection via captured NPC memory; bootstrap `$MODEL` heredoc;
  `cmd_logs` path component; qpeek clone; `world reset` rm -rf operator trust;
  CGNAT hardcoding in tailscale mode.
---
*Prior review (2026-09-28b, full, `f3f46dc`): the operating turn; 0 BLOCK / 18 WARN, all fixed in `f3f46dc` over two /codefix passes and pushed as `9b738f9`.*

<!-- REVIEW_META: {"date":"2026-09-28","commit":"cca5c50","reviewed_up_to":"cca5c50c5606345d69b646d7e8f9740134fabd86","base":"origin/main","tier":"full","block":0,"warn":12,"note":2,"fixed":12} -->
