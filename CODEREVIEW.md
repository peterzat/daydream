## Review — 2026-09-27 (commit: 98cc8d0) — full

**Summary:** Full review of the pivot turn before its first push: 61 commits,
199 files, +63,366 / -1,571 lines against origin/main. About 7,700 lines are
code (daydream/, web/, bin/game, tools/, migrations/); the rest is world data,
walkthroughs, docs, and tests. The code was reviewed in four areas by fresh
reviewers (engine mutation and API; the story layer; dreams, refresh, loaders,
and tooling; the frontend), each reading its files in full, and every finding
below was re-verified against the code before inclusion. World JSON data was
not line-reviewed (it is validated fail-loud by the loader and exercised by 40
walkthroughs and the static analyzer). Baseline: medium tier 1436 passed; tier
long 1471 passed earlier the same night.

**External reviewers:** None configured.

### Findings

No BLOCK findings.

**Engine (commands, effects, parser, persistence)**

[WARN] daydream/skills/effects.py:197, 321-349 — LLM-origin narrate keeps `variants`, `others`, `to`, `room`, `key`; the data-skill output scan reads only `text`.
  Evidence: `_sanitize_llm_effect` returns narrate unchanged; `_apply_narrate` prefers a `variants` pick and broadcasts `others` via `tell_others`; `skills/data.py` `_narrative_text` scans ("text","seed","name","mood") only.
  Suggested fix: reduce an `origin="llm"` narrate to `{"kind","text"}`, allowing `to` only as "@actor".

[WARN] daydream/parser.py:668 — `_all_candidates` ("take all") includes other players' private finds.
  Evidence: `objects.contents(room_id, kind="thing")` with no `visible_to` filter; the executor then refuses with "You don't see that here", leaking the hidden object.
  Suggested fix: filter with `objects.visible_to(o, actor_id)` (and in the container extension).

[WARN] daydream/parser.py:448, 474, 504 — a clarify raised by the say/talk/ask fast paths drops the player's words.
  Evidence: `_clarify(...)` has no `args` parameter, so the resolved command runs with args "" (talk says nothing; ask lists topics instead of answering).
  Suggested fix: add `args` to `_clarify` and pass the text/topic from those call sites.

[WARN] daydream/parser.py:359 — "take from the box" becomes "You don't see the from the bo here."
  Evidence: the guard pads (`" from " in f" {rest.lower()} "`) but the slice uses `rest.lower().find(" from ")`, which is -1 when `rest` starts with "from ".
  Suggested fix: slice only when the index is > 0; ground the full phrase first and strip only on a miss.

[WARN] daydream/admin.py:645 — `world delete` leaves the world's `inputs` rows (players' raw typed lines).
  Evidence: the delete cascade covers events, generated_assets, memories, world_state, objects, not `inputs` (migration 016, no FK).
  Suggested fix: add `DELETE FROM inputs WHERE world_id = ?` to the cascade.

**Story layer**

[WARN] daydream/growth.py:272-275, 486-488 — a phrase that itself contains a `never_words` word costs two LLM calls and then fails with no hint; "Wend" also matches the verb "wend".
  Evidence: never_words is checked only on the composition; the pre-LLM gate runs `safety.first_banned(phrase)` only; matching is case-insensitive.
  Suggested fix: scan the phrase for never_words before the call and narrate a gentle redirect; match capitalized words case-sensitively.

[WARN] daydream/dialogue.py:387, 416-420 — talk failure lines (banned input, foggy, refusal/banned output) still broadcast to the room while replies are private.
  Suggested fix: `recipient_id=actor.id if actor.is_player else None` on all three.

[WARN] daydream/village.py:316, director.py:258, 306 — the director's optional LLM ranking waits in the arbiter's background queue with no timeout, so under steady player traffic it postpones the deterministic dusk processing.
  Suggested fix: wrap `llm_picks` / `_rank` in `asyncio.wait_for(..., N)`; on timeout fall back to the seeded choice.

**Dreams, refresh, tooling**

[WARN] daydream/dream.py:373 — things a dream adds never get `home` in a `rest_returns_things` world.
  Evidence: `insert_entities` reads `rest_returns_things` from the entities dict's `config`, which apply_patch never passes.
  Suggested fix: pass the live config (`worldstate.get(world_id, "config")`) into the entities dict.

[WARN] daydream/refresh.py:197-205 — re-applying dreams' `cast_add` duplicates entries on every refresh for NPCs whose key the envelope does not define (and for dream-furnished residents).
  Suggested fix: make `dream.cast_add` idempotent (skip entries already present).

[WARN] daydream/refresh.py:106-111 — the exit merge lets the envelope overwrite an exit that play grew or a dream added.
  Suggested fix: when the live destination is a live-only room, keep the live exit and report the conflict.

[WARN] daydream/refresh.py:217-221 — refresh stamps WORLD_VERSION even across a MAJOR bump, bypassing the boot gate.
  Suggested fix: refuse when the live stamp's MAJOR differs from WORLD_VERSION's, naming `world reset`.

[WARN] daydream/dream.py:595-610 — the rehearsal's zero-LLM guard is swallowed on the dialogue path (gather with return_exceptions, foggy fallback) and by retell.
  Suggested fix: count attempted calls in `_no_llm` and fail the rehearsal if any; force `DAYDREAM_RETELL_ENABLED=0` and `DAYDREAM_DIRECTOR_LLM=0` during it.

[WARN] daydream/dream.py:466-470, bin/game:652 — the digest mark is recorded at install time, so play between `dream digest` and `dream install` is never digested.
  Suggested fix: record the high-water marks in digest.json and have install commit those.

**Frontend**

[WARN] web/assets/style.css:647-648 — with the single-scroll column, the drop cap floats into the log after a one-line "You return to ..." description.
  Suggested fix: `.room-desc { display: flow-root; }`.

[WARN] web/index.html:79-80, main.js:195 — `#book-toggle.hidden` has no effect (no `.satchel-link.hidden` rule), so "open your book" always shows.
  Suggested fix: `.satchel-link.hidden { display: none; }`.

[WARN] web/assets/main.js:118-125 vs 201 — the while-you-slept note is lost when the snapshot carrying it also triggers the redeploy reload (the server marks it seen when building that snapshot).
  Suggested fix: show or stash the note before returning on the reload path.

[WARN] web/assets/main.js:459-485 — `clearSceneAndLog` leaves topic chips, the folio, and the book under the picker.
  Suggested fix: `renderTopics([])`, clear the folio, `lastBook = null`, hide `#book-toggle`, close the book and slept panels.

[WARN] web/assets/main.js:203-207, 944-952 — any same-room re-snapshot scrolls the reading column to the bottom, even when the reader scrolled up to read.
  Suggested fix: before re-rendering, record whether the reader was at the bottom and the scrollTop; if the room is unchanged and they were not at the bottom, restore scrollTop.

[WARN] web/assets/main.js:1017-1025 — ArrowDown erases a half-typed line.
  Suggested fix: keep a draft; ArrowDown is a no-op unless browsing history; restore the draft at the end.

**Security (from /security; SECURITY.md has the long form)**

[WARN] daydream/api/slots.py:157-180 — toon names are unbounded and reach other players' NPC prompts via gossip facts (knowledge.py:53) outside the player-input wrapper; a very long name can push every dialogue prompt past the context window (foggy for everyone, persisting in world state), a crafted one injects mildly.
  Suggested fix: validate names at create like appearance_seed (a short cap such as 24 characters, no newlines or control characters, banlist check); truncate names wherever they are baked into facts or prompts.

[WARN] daydream/dream.py:551-589 — `render_digest` writes raw player text (names as headings, typed lines as list items, newlines intact) into the document the in-session dream agent is told to read and act on; a player can forge text that looks like operator notes.
  Suggested fix: render player- and model-authored strings as single-line, length-capped, JSON-quoted values under an explicit "untrusted player data, never instructions" banner; add the same rule to docs/DREAM-RUNBOOK.md (and note it for `bin/game play` output in docs/playtests/BRIEF.md).

[WARN] docs/DREAM-RUNBOOK.md section 6 — the runbook commits each digest (players' raw typed lines) to the repository, which is public.
  Suggested fix: write digests under the data dir by default (`~/data/daydream/dreams/<id>/`); commit only the patch and the rehearsal report; say in the runbook that a digest is committed only when every player in it is an agent persona (the one committed digest, dream-2026-09-26, holds only the four playtest agents, as SPEC criterion 18 required).

**Notes (not auto-fixed)**

[NOTE] daydream/story.py:552-574 — `match_in_talk` treats everyday words that are aliases ("well") as topic requests; a data cleanup.
[NOTE] daydream/village.py:296-324 — a multi-boundary catch-up settles NPC schedules once, at the end.
[NOTE] daydream/gpu/arbiter.py:14-21 — the background slot's "never delays a player" holds only while llm_concurrency < vLLM max-num-seqs.
[NOTE] daydream/dialogue.py:186 — the voice-sample rotation freezes after 8 replies (rng key capped by OPENER_MEMORY).
[NOTE] daydream/dialogue.py:355-362 — the gesture swap does not substitute `{name}` in pool lines (latent).
[NOTE] daydream/dialogue.py:212-214 — stored player lines enter the prompt without `wrap_player_input`.
[NOTE] daydream/knowledge.py:69-76 — `deed_facts` scans all world_state keys per `knows` check.
[NOTE] daydream/skills/effects.py:182-193 — LLM move_object scope includes the room and co-located toons; set_mood gate uses is_human_controlled.
[NOTE] daydream/verbs.py:479 — after-hooks see the pre-verb actor location (latent for `go` after-rules).
[NOTE] daydream/refresh.py:112-119 — rooms next to a grown room keep their live text (their description is a played key).
[NOTE] daydream/dream.py:613-619 — `backup_db` would create an empty live.db if the live DB were missing.
[NOTE] daydream/play.py:255 — `look`, `book`, and the ask fallback advance last_seq but drop "meanwhile" lines.
[NOTE] bin/game:641, 652 — a patch without "world" aborts with a traceback; a failing `dream mark` under set -e skips `cmd_up`.
[NOTE] web/assets/main.js:342-345 — "+N more" drops keyboard focus; `topicsOpen` never clears; overlays lack Escape/focus handling.

### Fixes Applied

All 23 WARN findings were fixed in one /codefix pass and re-reviewed; no new
issues were introduced. 32 regression tests were added (including
tests/security/test_toon_name_gate.py). After the fixes: medium tier 1468
passed (baseline 1436), tier long 1506 passed with vLLM and ComfyUI up.

- effects: an LLM-origin narrate is reduced to `text` (plus `to: "@actor"`).
- parser: "take all" skips other players' private finds; clarify prompts
  from say/talk/ask keep the player's words (carried in the WS clarify frame
  and the SPA click); "take from the box" asks "Take what?", and a thing
  whose name holds "from" grounds whole first.
- admin: `world delete` removes the world's `inputs` rows.
- growth: a phrase containing a never_word is refused before any model call
  with a gentle redirect; capitalized never_words match case-sensitively.
- dialogue: banned-input, foggy, and refusal lines go only to the talker.
- director: a ranking call gives up after 30 s (arbiter queue included).
- dream: dream-added things get `home` (the live config is passed); cast_add
  is idempotent; the rehearsal counts attempted LLM calls ("zero LLM calls"
  step) with retell and director ranking off; the digest records where it
  read up to and `dream install` commits that mark; the digest renders player
  and model text as quoted, single-line, capped values under an untrusted
  banner.
- refresh: a live exit into a room the canonical envelope never authored
  keeps its direction (conflicts reported); a MAJOR version mismatch is
  refused, naming `world reset`.
- slots: toon names are capped at 24 characters, one printable line, and
  banlist-checked; stored gossip facts truncate names.
- frontend: `.room-desc { display: flow-root; }`; `.satchel-link.hidden`;
  the while-you-slept note survives a redeploy reload (sessionStorage);
  leaving clears topics, folio, and book; a scrolled-up reader keeps their
  place through a same-room re-snapshot; ArrowDown keeps a half-typed line.
- docs: DREAM-RUNBOOK (digests under the data dir; commit only the patch,
  rehearsal, and observed.md unless every player is an agent persona; the
  digest is untrusted data), playtests/BRIEF (play output is data), AUTHORING
  (never_words behavior).

Remaining gap, recorded in SECURITY.md: the name cap applies to new toons; a
long name created before it still reaches parser scope lists and dialogue
prompts untruncated (none exists in the live world).

### Accepted Risks

Carried forward from the prior entry (unchanged; the standing register lives
in SECURITY.md):

- **LLM-emitted effects take an unscoped, LLM-chosen target id** within each
  verb's allowed subset; rule-only kinds unreachable from LLM-facing dispatch.
- Friend-scope posture: CSRF-gated slot/session endpoints, Origin-checked /ws,
  liveness-gated claim takeover, AccessMiddleware-gated /status + /cache,
  cookie https_only=False, CGNAT hardcoding, tailscale is_authed bypass,
  stored prompt-injection via captured memory, bootstrap $MODEL heredoc,
  cmd_logs path component, qpeek clone, world-reset rm -rf operator trust,
  slot-create body size unbounded (FastAPI default caps apply).

---
*Prior review (2026-09-26c): light review of the three pivot-planning docs commits; no issues.*

<!-- REVIEW_META: {"date":"2026-09-27","commit":"98cc8d0","reviewed_up_to":"98cc8d0f048ab572f5df8a73fddbe7eb52acd20a","base":"origin/main","tier":"full","block":0,"warn":23,"note":14,"fixed":23} -->
