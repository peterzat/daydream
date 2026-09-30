## Review — 2026-09-30 (commit: a7cdb15) — PRELIMINARY (fix loop in progress)

**Summary:** Refresh review of `087fc4a..a7cdb15`, the "Reflexes and few dead ends" spec (14 criteria): triage in the parser's call, gestures, absent residents, meta questions, AND-chains, verb defaults, world verb opt-outs, the promise guard, scenery and exit names, the prose-noun ratchet, fragments and pronouns, the battery. Three fresh reviewers read the diff in partitions and probed it; every finding below was reproduced (by the reviewer's probe and, for the BLOCK and the parser/gesture/absent WARNs, by a second probe on a fresh village). Tests at a7cdb15: `ruff check .` clean, short + medium 2396 passed.

**External reviewers:**
None configured.

### Findings

[BLOCK] daydream/api/ws.py:790-806 — The chain stop (criterion 5) also stops inside a noun list or ALL: `_expand_multi` returns one Parse per item and the loop breaks at the first refusal.
  Evidence: in the square, `take the moon and the paper lantern` reads "You don't see the moon here." "(So you leave the next part for now.)" and nothing is taken; before this turn the lantern was taken. `take all` / `drop all` stop at the first item that refuses.
  Suggested fix: carry which segment each Parse came from (e.g. a `segment` index set in `parse_line`) and stop only before a later segment; items of one list all run.

[WARN] daydream/parser.py:507-515 — An exit name matches the whole rest of a take/use line, so a two-object line ending in a door or stair moves the player.
  Evidence: at the Clocktower, `use the key on the cellar door` moves to r-cellar; `take the moth from the low door` too (before: both went to the model).
  Suggested fix: for take/use, move by an exit name only when the line has no preposition split (`_split_prep(spec, rest)[1] is None`, no " from ") and the name matches exactly.

[WARN] daydream/parser.py:1129-1131 (`interpret`) and daydream/api/ws.py:1352 — Untrusted model JSON crashes the input path: `result.get("dobj_id") in scope_ids` and `result.get("kind") in QUESTIONS` hash raw values.
  Evidence: `{"verb":"take","dobj_id":["x"]}` and `{"verb":"none","kind":["time"]}` raise `TypeError: unhashable type: 'list'`, which leaves `_receive_loop` and drops the socket. A click frame with a list `dobj_id` reaches `parser.remember_referents` before `_handle_command` coerces it (sqlite InterfaceError, sender's own socket).
  Suggested fix: `isinstance(..., str)` guards before the membership tests; coerce or drop non-string ids before `remember_referents`.

[WARN] daydream/parser.py:151/308 (`_THEN_SPLIT` vs `_AND_JOIN`) — "X and then Y" splits on THEN first and leaves a dangling "and".
  Evidence: `take the paper lantern and then go west` reads "You don't see the paper lantern and here." and the stop note; `…lantern, and then go west` reads "You don't see the and here."
  Suggested fix: let `_THEN_SPLIT` take a leading `,?\s*and\s+`.

[WARN] daydream/parser.py:259-272 — IT inside one line means the previous line's referent: `_remember` runs only after every segment has parsed.
  Evidence: with an earlier referent set, `take the paper lantern and examine it` examines the earlier thing (or reads "You don't see the it here").
  Suggested fix: remember each segment's referents as it is parsed.

[WARN] daydream/parser.py:1176 (`_typed_target`) — When the model leaves out `target`, the name becomes the words after the line's first word even when that word is not the verb.
  Evidence (mocked `{"verb":"take","dobj_id":null}`): "please take the stone" reads "You don't see the take the stone here."; "I want to pick up the stone" reads "You don't see the want here."
  Suggested fix: use the fallback only when the first word is the chosen verb or one of its aliases (skip it otherwise).

[WARN] daydream/parser.py:694-722 (`_gesture_fast_path`) and :283 (`_starts_like_a_command`) — A gesture claims the whole line and turns what follows into a missing name.
  Evidence: `hug Bell and go west` reads "You don't see Bell and go west here."; `thanks for the tea` reads "You don't see for the tea here."; `smile warmly`, `wave goodbye`, `bow deeply` read "You don't see warmly/goodbye/deeply here."; `hug the cobbles` (authored scenery) reads "You don't see cobbles here."
  Suggested fix: gesture words start a command for chain splitting; cut `who` at " and " and sentence punctuation; drop a leading "for …"; treat a trailing adverb as no target; when `who` neither grounds nor names someone absent, try glimpse/scenery, else leave the line to the parser's model call.

[WARN] daydream/gestures.py:147-159 and daydream/verbs.py `_handle_gesture` — A resting dreamer is treated as present (criterion 2: "a resting one isn't here").
  Evidence: after `kick_slot(2)`, `hug Vesper` tells Wren "You hug Vesper.", Vesper "Wren hugs you.", the room "Wren hugs Vesper."; the auto-target of "thank you" counts resting toons.
  Suggested fix: a player target that is not human-controlled (resting) gets `absent.line` privately; skip resting toons in the auto-target.

[WARN] daydream/meta.py:24 — `WHO_RE` includes "who is this": typed at a stranger it answers with the player's own look and inventory.
  Evidence: `who is this` beside a resident reads the dreamer's own card.
  Suggested fix: drop that phrasing from `WHO_RE`.

[WARN] daydream/llm/format2.py:337 — `elif "glimpsed"` is chained after `elif "exit_names"`, so a room with exit names skips glimpse validation (r-clocktower, r-cellar, r-lamphouse, r-duskroad).
  Evidence: a malformed glimpse (unknown verb key, bad `if`, a non-dict entry) in r-cellar loads with no error; the same in r-square is refused with four errors.
  Suggested fix: make the `glimpsed` check an independent `if`.

[WARN] daydream/verbs.py:497-503 — The absent answer runs before authored glimpses and names offstage guests; it also changes Zork.
  Evidence: at the Dusk Road, `take the hour` / `touch the hour` read "Extra Hour isn't here." (the authored "hour" glimpse is preempted, and the guest has not arrived); in Zork, `examine thief` from West of House reads "thief isn't here; thief is in Round Room just now." (was "You don't see the thief here"), leaking the wanderer's position.
  Suggested fix: try the authored glimpse/scenery first; skip toons with no room; make the absent answer apply only to toons with a voice sheet or schedule (or a world opt-in) so Zork keeps its behaviour.

[WARN] worlds/lost-hours/world.json (verbs push, pull, climb, light, touch, look under; `config.gestures.thing`) — Defaults break on plural names.
  Evidence: "The resting clocks doesn't budge", "the trellises isn't one of Bell's", "The pigeonholes isn't made for climbing", "You give the jars of saved hours a gentle tug. It stays where it belongs.", "You touch the trellises. It is exactly as real…", gesture-at-thing "It takes the kindness quietly." 8f5d7e9 fixed only part.
  Suggested fix: rewrite these lines with no verb agreeing with `{the_thing}`/`{The_thing}` and no "it"/"its" for the thing.

[WARN] daydream/dialogue.py:714, 737-746 — A draft that advances an authored beat skips the guard, but if the beat has gone stale at commit (`advance_beat` returns None) the draft itself is shown, unjudged.
  Evidence: mocked dialogue advancing `moth/hob-notices` while another player finishes it in flight: calls `['dialogue']` (no judge) and the narration shows "Hob grins. 'Follow me, I'll carry your lamp to the well.'"
  Suggested fix: when the skipped draft ends up shown (`ev is None`), run the guard on it then (deterministic checks + judge), and deflect if it fails.

[WARN] daydream/dialogue.py:575-597 (`_COMMITS`) — Ordinary talk matches the commitment shapes and is dropped before the judge, so residents deflect instead of answering.
  Evidence: `commits()` is True for "I will keep it in mind.", "I'll take it as a compliment.", "I can give you a little advice, if you like.", "We walk the lane each evening when the lamps are lit.", "Together we keep the hours.", "Spring will come along soon enough."
  Suggested fix: narrow the shapes: `come along` only with "with me/you"; drop bare `we go/walk/leave` and `together we`; for keep/take/show/give require the player's thing or a "for you"/"safe" completion (not "you"/"it" idioms like "keep it in mind", "take it as"); add these lines as negative cases in `test_commitments_the_engine_wont_keep`.

[NOTE] daydream/verbs.py `_handle_gesture` — the target's kind is never checked (a room dobj from the model or a click frame reads "You bow to The Lantern Square."), and args "high five" become "gesture" (lookup uses `split()[0]` before `WORDS.get(name)`).
[NOTE] daydream/parser.py:314 — AND-splitting breaks a noun list when a noun or alias is also a verb word (Zork: `take sword and light`, "light" is the lamp's alias). No village collision today; the Zork walkthrough passes.
[NOTE] daydream/prose_nouns.py — the ratchet is porous (a phrase counts as covered by any one global name word: "old", "clock", "evening"), and the baseline keeps two stale lectern entries.
[NOTE] daydream/dialogue.py:124-149 (`_places`) — a room reachable only by a secret exit is still listed; latent (no world has both today).
[NOTE] Test gaps: the SQL `json_each` list-`except` path in `events.fetch_since` has no test (hand-checked correct); no test for a noun list with a missing item before a present one.

### Cycle 2 (re-review of the /codefix pass)

The cycle-1 fixes hold under re-probe: the noun list takes the lantern after "You don't see the moon here.", `use the key on the cellar door` no longer moves, `hug Bell and go west` hugs and goes west, `smile warmly` smiles, `take the hour` at the Dusk Road reads its glimpse, unhashable model JSON no longer raises. Two findings remain:

[WARN] tests/ — The cycle-1 fixes carry no regression tests (only the six negative `commits()` cases were added).
  Evidence: no test covers the BLOCK (a noun list with a missing item before a present one), take/use exit-name exactness (`use the key on the cellar door` stays put, `take the stairs` still moves), `interpret` with a list `dobj_id`/`kind` and a click frame with a list `dobj_id` reaching `remember_referents`, "X and then Y" / "X, and then Y", IT per segment with an earlier referent set, gesture chains (`hug <someone> and go <dir>`, `smile warmly`, `thanks for the tea`, a gesture at authored scenery), a resting dreamer as a gesture target and in the auto-target, a malformed glimpse in a room that has `exit_names` refused by the loader, glimpse-before-absent (`take the hour` at the Dusk Road) and an offstage guest not named as elsewhere, a world whose toons have no voice or schedule keeping "You don't see the X here", the stale-beat draft being judged (and deflected when it fails), `who is this` no longer answering with the dreamer's card, and the SQL `json_each` list-`except` path in `events.fetch_since`.
  Suggested fix: one focused test per item, in the existing test files for each module (test_chains_guesses, test_parser, test_fragments_pronouns, test_gestures, test_format2 or test_glimpse, test_absent, test_promise_guard, test_meta, test_events).

[WARN] daydream/dialogue.py `_COMMITS` — The narrowing dropped unambiguous promise shapes, so they now rely on the judge alone.
  Evidence: `commits()` is False for "I'll show you the way up." and "I'll take you to the well." (both were True before; the promise suite showed the judge alone lets some promises through).
  Suggested fix: add a narrow shape for leading the player somewhere: `(?:show|take|lead|walk|bring) you (?:the way|to|there|over|across|down|up|home|along)\b` (after i will/i'll/i shall/let me/i can), and add both lines as True cases in `test_commitments_the_engine_wont_keep` while keeping the six False cases.

### Cycle 3 (from /security, 2026-09-30)

[WARN] worlds/lost-hours/world.json:692 (the cellar `drink` rule) and worlds/lost-hours/cast/others.json:403-440 (Umber's `tea` topic) — Umber's chipped cup multiplies without limit: each pour spawns a cup whenever the player isn't holding one (the spawn dedup in `daydream/skills/effects.py:476-488` looks only at the satchel).
  Evidence (/security probe): `drop all. drink` in the cellar leaves one more cup per line with no model call, about 180 a minute at the socket's rate limit. At about 175 cups the parser's scope list overflows the model's 8,192-token context (300 cups measured 12,598 tokens) and every model-read line in the cellar reads "foggy"; at about 3,000 cups each drop or pour rebuilds the cellar scene for 194 ms on the single event loop. Nothing removes the cups. The `tea` topic route is already in prod.
  Suggested fix: pour the cup once per player, as Quill's seed is gated: declare a player flag (e.g. `UMBER-CUP` in `player_flags`), have the first pour (topic or drink rule) spawn the cup and `set_pflag`, and later pours narrate tea drunk there with no spawn (an authored line in Umber's label voice). Add a walkthrough or test that pouring twice after dropping the cup leaves one cup. Re-assemble `worlds/lost-hours.json`.

[NOTE] (security) daydream/api/ws.py:1352 — a clicked id becomes IT before any scope check; an out-of-scope id could later be named through "ask <someone> about it". Nothing leaks today (runtime ids are random, and an id a player learns arrives with its name). Remember a clicked id only when it is in scope.
[NOTE] (security) Neither the parser's scope list nor the scene caps repeated objects; any future way to multiply things reopens the context overflow. BACKLOG candidate.

### Fixes Applied

Cycle 1 (/codefix): all fourteen findings above (1 BLOCK, 13 WARN). Short 1713, medium 2402.

### Accepted Risks

- **A thing with a `home` handed to a DOZING dreamer** (`verbs._hand_to_player`, the tuck-away branch) waits in their satchel until they rest; declined because walkthrough players count as dozing (BACKLOG `dozing-handover-of-village-things`; also in SECURITY.md).

Carried forward (the standing register lives in SECURITY.md):

- **LLM-emitted effects take an unscoped, LLM-chosen target id** within each
  verb's allowed subset; rule-only kinds unreachable from LLM-facing dispatch.
- Stored prompt-injection via captured NPC memory; bootstrap `$MODEL` heredoc;
  `cmd_logs` path component; qpeek clone; `world reset` rm -rf operator trust;
  CGNAT hardcoding in tailscale mode.
- (security, carried) daydream/accounts_cli.py:129 — an account deleted while its player waits on a resident's reply leaves that reply and its `talk:`/`rel:` records behind.
- (security, carried, open WARN needing the operator) tools/agent_guard.py:36-38, :47, :264-267 — a recursive search one folder below home, and a combined short-flag spelling of gh's show-token option, get no opinion from the guard.

---
*Prior review (2026-09-29h, refresh, `087fc4a`): the lint fix for the glimpses push and the creative-break playtest note; no new issues, the agent-guard WARN carried open.*

<!-- REVIEW_META: {"date":"2026-09-30","commit":"a7cdb15","reviewed_up_to":"a7cdb15d9748","base":"origin/main","tier":"refresh","block":1,"warn":16,"note":7,"preliminary":true} -->
