## Review — 2026-09-29g (commit: de5e11b)

**Summary:** Refresh review of `1387a25..de5e11b`: the satchel and book by their names alone; glimpses (a name the prose says that is no object answers from an authored `properties.glimpsed`, else the prose sentence for a look and one validated, cached local line for other verbs, else "not here"); "look at" an absent name reads like examine; wider take/examine aliases; and the authored glimpse batch for the village. Read by a fresh reviewer with behaviour probes (mocked model) and checked in-session; /codefix fixed all nine fixable WARNs and the fixes were re-reviewed. `/security` on the paths since `d2f7538`: no new finding (privacy probed: another dreamer's private note, a closed box, another satchel and another dreamer's looks all read "not here" with no model call). Tests: medium 2225 before, 2260 after.

**External reviewers:**
None configured.

### Findings

[WARN, fixed] daydream/verbs.py:108 — the "carry" alias steals the letters arc's own instruction.
  Evidence: the letters thread says "carry it to whoever it nearly means"; holding the crayon letter with Bell here, "carry the crayon letter to Bell" now parses as take (the trailing-phrase head grounds the letter) and answers "You're already carrying the crayon letter." Before, "carry" was no verb and the line reached the model parser, which has give in reach.
  Suggested fix: drop "carry" from take's aliases; add a parser test that "carry the X to <toon>" does not parse as take on the fast path.

[WARN, fixed] daydream/parser.py:452-465 (with verbs.py:99) — "check" treats a leading preposition or self word as the name.
  Evidence: "check on Mott" answers "You don't see the on Mott here"; "check it out" -> "it out"; "check inventory" / "check my pockets" (the model-eval parser corpus's own inventory case) read a sentence naming a pocket watch. All went to the model parser before.
  Suggested fix: in `_fast_path`, when the verb came from an alias of take or examine and `rest` opens with a preposition (on, for, with, up, in, at, about, over, under, into, out) or is a self or inventory word (me, myself, my ..., pockets, inventory, satchel, bag), return None (defer to the model as before). Parser tests for these phrasings.

[WARN, fixed] daydream/parser.py:348-353 — look-at answers "not here" for self, room and inventory words.
  Evidence: "look at me" / "look at myself" -> "You don't see the me here"; "look in my satchel" -> "You don't see the satchel here"; "look at the room" / "look at the view" -> "You don't see the room here".
  Suggested fix: before passing a `dobj_name`, map self words (me, myself, self, yourself) to examine of the actor, room words (room, here, around, surroundings, view, place) to `look`, and satchel / bag / inventory / pockets (with or without "my") to `inventory`; and "<name>'s X" where <name> is an in-scope toon to examine that toon. Parser tests.

[WARN, fixed] daydream/glimpse.py:102-105, 139-169 — a dark room's prose leaks.
  Evidence: `objects.in_scope` keeps the room in darkness; in Zork's unlit cellar "examine the ramp" reads the room's ramp sentence and "take the ramp" spends a model call, while `look` says it is pitch black.
  Suggested fix: when `not lighting.room_lit(room_id)`, leave the room out of `_hosts` (both `authored` and `seen_in`). A test on a dark room.

[WARN, fixed] daydream/glimpse.py:227-245 — `valid_line` misses quoted speech, the world's canon-breakers and capitalized names.
  Evidence: accepted "Mott covers it with his hand. 'Not that one,' he says, kindly." (source: the tin's seed), "The baker left the tin here...", "...the mayor of the village keeps it there.", and an all-caps name.
  Suggested fix: reject single-quoted speech (reuse the quoted-span pattern in daydream/skills/effects.py), reject any word in the world's `config.templates.dreamseed.growth.never_words` (as daydream/growth.py applies them: a capitalized entry matches as written, a lowercase one in any case), and reject an all-caps word of two or more letters not in the source. Tests for each.

[WARN, fixed] daydream/parser.py:348, 463 — names of four words or more never reach glimpses.
  Evidence: "take the lantern by the stair", "look at the hands of the clock", "take the stub of blue chalk" and "take the jar on the top shelf" defer to the model parser, which never sets `dobj_name`, and read "The dream isn't sure what you mean by that".
  Suggested fix: where the fast path defers a name of four or more words, if its trailing-phrase head (`_TRAILING_PHRASE`) differs and is under four words, pass the head as `dobj_name` instead of deferring; and have `glimpse.validate_glimpsed` reject authored names of four or more words (then shorten the five authored ones: drop "lantern by the stair", "hands of the clock", "jar on the low shelf", "jar on the lowest shelf", "stub of blue chalk").

[WARN, fixed] daydream/glimpse.py:53-66 — a typed plural falls back to a singular with another meaning.
  Evidence: after the clock's look ("Its hands stand still."), "look at the hands" reads the repair ledger's "older, looping hand" sentence; the same turned "pockets" into "pocket watch".
  Suggested fix: when the typed last word is plural, match only the plural in prose (a singular typed word may still match its plural); add "hands" to the three great-clock entries' names in worlds/lost-hours/regions/01-clocktower.json and re-assemble.

[WARN, fixed] daydream/glimpse.py:188-190, 296-303 — an exit the prose names reads as out of reach, and the plain line says "it" for plurals.
  Evidence: in the well-court "open the gate" (the south exit) answers "You can see the gate from where you stand, but it isn't within reach just now"; "take the stairs" gets "stairs ... it isn't".
  Suggested fix: when the sentence that names the noun also names exactly one direction that is an exit of the current room, answer deterministically "The {noun} is the way {direction} from here." (no model call); make `plain_line` say "they aren't" for a plural noun.

[WARN, fixed] tests/test_glimpse.py:95-97 — the outage test never reaches the outage branch.
  Evidence: after `LLMUnavailable`, "lift the shelves" grounds to the jars (alias "shelves"); `compose`'s outage path has no coverage.
  Suggested fix: use a prose-only name on a fresh cache key (not yet asked) and assert `plain_line`.

### Open WARN (needs the operator; not for /codefix)

[WARN] (security, carried) tools/agent_guard.py:36-38, :47, :264-267 — a recursive search one folder below home, and a combined short-flag spelling of gh's show-token option, get no opinion from the guard. The guard asks the operator before any change to itself (`PROTECTED`, :199-202), deliberately, since this session carries player text; the fix waits for a session with the operator present. Not accepted; not downgraded. SECURITY.md has the detail.

### Notes

[NOTE] daydream/glimpse.py:41, 156-158 — function words count as nouns ("take the" spends a model call); require a content word.
[NOTE] daydream/parser.py:222 — `_starts_like_a_command` still rejects a one-letter first word, so "x tin. north" does not chain; CLAUDE.md's "one-letter aliases act only alone" is now stale.
[NOTE] daydream/glimpse.py:122 — on equal-length names the first entry whose conditions hold wins (unconditional entries must come last; AUTHORING.md should say so), and `validate_glimpsed` accepts any `verbs` key, so a typo never fires.
[NOTE] worlds/lost-hours/regions/01-clocktower.json — while the player carries Wend's ladder in the cellar, "take the jar" says no ladder here is tall enough; an entry on `{"carried": "o-tace-hour-ladder"}` would fit.
[NOTE] Zork's LIFT (a RAISE synonym for the basket) now resolves to take; Zork is frozen.
[NOTE] (security, carried) placeholders over letter bodies and appearances; `play` prints a grown place's description unmarked (and "look at" in a grown room now repeats it); the server keeps control characters in typed lines; the delete-during-talk gap.

### Fixes Applied

- [WARN] take no longer answers to "carry": "carry the letter to a friend" is a give, read by the model (test).
- [WARN] after an alias of take or examine that grounds nothing, a leading preposition, "my ...", a split particle ("it out") or a self or satchel word goes to the model as before (tests).
- [WARN] look at me / myself examines the dreamer; the room / view / here runs look; satchel / bag / inventory / pockets runs inventory; "<toon>'s X" examines that toon (tests).
- [WARN] an unlit room is not a glimpse host (test on a dark cellar).
- [WARN] `valid_line` rejects single-quoted speech, all-caps words the source never said, and the world's dreamseed `never_words`; model-eval's glimpse suite passes the same never-words (tests).
- [WARN] a phrase of four words or more passes by its trailing-phrase head (one with "and" still goes to the model, keeping Zork's list case); the loader refuses authored names of four words or more, and the five such names were removed (tests; AUTHORING.md says so).
- [WARN] a typed plural matches only a plural in prose; the great clock answers to "hands" (tests).
- [WARN] a compass exit the naming clause points to answers "The gate is the way south from here." with no model call; `plain_line` says "they aren't" for plurals (tests).
- [WARN] the outage test now reaches the outage branch (a prose-only name on a fresh key; confirmed failing with the branch broken).

### Accepted Risks

- **A thing with a `home` handed to a DOZING dreamer** (`verbs._hand_to_player`, the tuck-away branch) waits in their satchel until they rest; declined because walkthrough players count as dozing (BACKLOG `dozing-handover-of-village-things`; also in SECURITY.md).

Carried forward (the standing register lives in SECURITY.md):

- **LLM-emitted effects take an unscoped, LLM-chosen target id** within each
  verb's allowed subset; rule-only kinds unreachable from LLM-facing dispatch.
- Stored prompt-injection via captured NPC memory; bootstrap `$MODEL` heredoc;
  `cmd_logs` path component; qpeek clone; `world reset` rm -rf operator trust;
  CGNAT hardcoding in tailscale mode.
- (security, carried) daydream/accounts_cli.py:129 — an account deleted while its player waits on a resident's reply leaves that reply and its `talk:`/`rel:` records behind.

---
*Prior review (2026-09-29f, refresh, `d2f7538`): the socket and margin fixes after an ungated push; 0 BLOCK, the Talk drop test race fixed, the agent guard WARN left open for the operator.*

<!-- REVIEW_META: {"date":"2026-09-29","commit":"de5e11b","reviewed_up_to":"0094b57ed6b25d952071615de757d516f678bd53","base":"origin/main","tier":"refresh","block":0,"warn":1,"note":6} -->
