## Review — 2026-09-30 (commit: 4aeb1e9)

**Summary:** Refresh review of `087fc4a..4aeb1e9`, the "Reflexes and few dead ends" spec (14 criteria): triage in the parser's call, gestures, absent residents, meta questions, AND-chains, verb defaults, world verb opt-outs, the promise guard, scenery and exit names, the prose-noun ratchet, fragments and pronouns, the battery. Three fresh reviewers read the diff in partitions and probed it; every finding was reproduced before it was recorded (the BLOCK and the parser, gesture and absent WARNs also by a second probe on a fresh village). `/security` on the 36 changed code and data paths added one WARN (Umber's cup) and one NOTE. Three fix cycles, all findings resolved, 33 regression tests added. Tests: `ruff check .` clean; `assemble_world --check` matches; short + medium 2396 before, 2435 after.

**External reviewers:**
None configured.

### Findings

[BLOCK] daydream/api/ws.py:790-806 — The chain stop also stopped inside a noun list or ALL (`take the moon and the paper lantern` took nothing). Fixed: each Parse carries its segment; a refusal stops only before a later part.

[WARN] daydream/parser.py (exit names) — `use the key on the cellar door` moved the player. Fixed: take/use move only by an exit named whole, with no preposition split.
[WARN] daydream/parser.py `interpret`, daydream/api/ws.py — list-valued model JSON or click ids raised and dropped the socket. Fixed: string guards.
[WARN] daydream/parser.py `_THEN_SPLIT` — "X and then Y" left a dangling "and". Fixed.
[WARN] daydream/parser.py — IT in one line meant the previous line's thing. Fixed: referents per segment.
[WARN] daydream/parser.py `_typed_target` — "please take the stone" read "You don't see the take the stone here." Fixed: a line opening with a non-verb word names what follows the verb.
[WARN] daydream/parser.py gesture fast path — a gesture swallowed the rest of the line ("hug Bell and go west"), and read how-words and "for ..." as names. Fixed.
[WARN] daydream/gestures.py, verbs.py — a resting dreamer was treated as present. Fixed.
[WARN] daydream/meta.py — "who is this" answered with the dreamer's own card. Fixed.
[WARN] daydream/llm/format2.py — rooms with `exit_names` skipped glimpse validation. Fixed.
[WARN] daydream/verbs.py, absent.py — the absent answer preempted authored glimpses, named offstage guests, and placed Zork's wanderer. Fixed: glimpses first; only people somewhere with a voice, a schedule, or a player.
[WARN] worlds/lost-hours/world.json — defaults broke on plural names. Fixed.
[WARN] daydream/dialogue.py — a draft whose beat went stale in flight was shown unjudged. Fixed.
[WARN] daydream/dialogue.py `_COMMITS` — ordinary talk ("I will keep it in mind") was dropped as a promise. Fixed (narrowed).
[WARN] tests/ — the cycle-1 fixes had no regression tests. Fixed: 33 tests, 32 of which fail on the pre-fix code.
[WARN] daydream/dialogue.py `_COMMITS` — the narrowing dropped "I'll take you to the well". Fixed: a narrow lead-you-somewhere shape.
[WARN] (security) worlds/lost-hours/world.json, cast/others.json — Umber's chipped cup multiplied without limit (context overflow at ~175 cups, event-loop stalls at thousands). Fixed: `UMBER-CUP` player flag; later pours are drunk in the cellar.

[NOTE] daydream/verbs.py `_handle_gesture` — the target's kind is not checked (a room dobj reads "You bow to The Lantern Square."); args "high five" become "gesture".
[NOTE] daydream/parser.py — AND-splitting breaks a noun list when a noun is also a verb word (Zork `take sword and light`); no village collision; the Zork walkthrough passes.
[NOTE] daydream/prose_nouns.py — the ratchet is porous (any one global name word covers a phrase) and keeps two stale lectern entries.
[NOTE] daydream/dialogue.py `_places` — a room reachable only by a secret exit is still listed; latent.
[NOTE] (security) daydream/api/ws.py — a clicked id becomes IT before any scope check; nothing leaks today.
[NOTE] (security) neither the parser's scope list nor the scene caps repeated objects (BACKLOG `repeated-things-caps`).
[NOTE] Prod cups: any cups already poured in prod stay; a dreamer who got one before the gate can get one more.

### Fixes Applied

- 4aeb1e9 (/codefix, three cycles): every BLOCK and WARN above.

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

<!-- REVIEW_META: {"date":"2026-09-30","commit":"4aeb1e9","reviewed_up_to":"4aeb1e9ca1ad5dd6276d0519dc9887dfcb092519","base":"origin/main","tier":"refresh","block":0,"warn":0,"note":7} -->
