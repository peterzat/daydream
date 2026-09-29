## Review — 2026-09-29 (commit: ab44e90)

**Summary:** (META block count is what remains: 3 BLOCK were found and all fixed.) Refresh review of nineteen unpushed commits over `origin/main` (`5db3142`): the beta rehearsal's household layer (letters and parcels through the post keeper, handing things over, "also dreaming", "while you were away", the record of dreamers, rosters, the thinking frame, Quill's seed, honest ledger credit, signed growth, the second dream) plus the playtest records. Every changed file read at full depth (57 files; the focus set is the whole diff); an independent adversarial pass by a fresh reviewer agent with runtime probes; `ruff check .`; `/security` over the 47 code and data files (0 BLOCK / 1 WARN / 4 NOTE). 3 BLOCK / 6 WARN / 8 NOTE; every BLOCK and five WARNs fixed in one /codefix cycle with seven new tests; one WARN's second half declined (below). Tests stable: short 1370 before, 1375 after; medium 2030 before, 2036 after; `ruff check .` clean; `node --check web/assets/main.js` ok.

**External reviewers:**
None configured (`review-external.sh` produced no findings and no cost log).

### Findings

[BLOCK] daydream/story.py:234 — `{dreamers_today}` was expanded only on the `effects._apply_narrate` path; every authored line told through `story._tell` (topics, beats, endings, storylets, including the two shipped lines) reached the player with the literal placeholder.
  Evidence: a runtime probe on a fresh world, `ask t-bell "who came through today"`, narrated "'Let me see: {dreamers_today}. ...'"; tests/test_trace.py covered only the effects path.
  Suggested fix: one helper called on every telling path; a test through a topic.

[BLOCK] daydream/absence.py:104, daydream/api/slots.py:303-309 — the "while you were away" note was consumed by the leaving player's own still-open socket on the browser leave path (the leave's `presence_changed` re-snapshotted the leaver, and `take_note` cleared the stamp for a toon no longer human-controlled), so a browser player never saw it.
  Evidence: TestClient probe: frames on the leaver's socket were `presence_changed` then a snapshot, and `away_since` was None right after leave.
  Suggested fix: `take_note` returns None without clearing unless the toon is human-controlled; the leave's `presence_changed` carries `except: t.id`; a socket-open leave-and-return test.

[BLOCK] daydream/live.py:14, tests/test_absence.py:8, tests/test_post.py:151, tests/test_trace.py — `ruff check .` reported 5 errors (UP035, two I001, F841); CI runs lint on push.

[WARN] daydream/post.py:300 (file_parcel), daydream/verbs.py:895-905 (_hand_to_player) — a parcel widened the verb's effect allowlist at the call site, and both paths could hide a shared village thing (one with a `home`) from everyone indefinitely: filed for one player it is invisible to all others and never sent home; tucked into a dozing player's satchel it waits on a rest that may never come.
  Suggested fix: declare `set_property` on `give`; refuse to file a thing whose `home` is set; for the dozing hand-over either refuse `home` things or accept the risk (see below).

[WARN] daydream/verbs.py:1574,1629-1641 with daydream/story.py:565-582 — a line longer than `TALK_SELECT_MAX_WORDS` that named an OPEN BEAT no longer selected it; the model received the beat's payoff text as grounding and could narrate a hand-over that did not happen.
  Suggested fix: the word cap applies to plain topics only; `topic_text` returns None for beats.

[WARN] daydream/verbs.py:976-981 — `_handle_open` ran the carried key through `execute_command`: two full commands for one typed `open` (two clock ticks, two catch-ups; turn-keyed rolls shift).
  Suggested fix: `_execute_resolved(... VERBS["use"] ...)` inside the same command.

[WARN] (security) daydream/post.py:187-253, 329-342 — letters were uncapped, and `letters_waiting` read every thing at the post room on every player's every command (6 ms per 1,000 waiting letters per call).
  Suggested fix: caps per sender-to-recipient and per recipient with an authored refusal; query only the viewer's letters.

[WARN] daydream/api/slots.py:308, daydream/toons.py:119 — `presence_changed` was room-scoped, so "also dreaming" (a world-wide list) refreshed only for viewers in the same room.
  Suggested fix: world-scoped, like `game_won`.

[WARN] web/assets/main.js:1289,1625 — every typed talk showed two transient lines at once (the client's "the dream stirs..." and the server's "considers...").
  Suggested fix: the server's line replaces the client's guess; a snapshot clears both.

[NOTE] daydream/llm/story_format.py:414-426 — `config.post.keeper` is not validated against the toon ids; a typo silently disables the inbox and parcels.

[NOTE] daydream/post.py:108-115 — `_INBOX_RE`'s `\bpost for\b` and `\banything (in|come in) for\b` match asks about other people's post and answer with the asker's own inbox; the ask-path inbox emits no `echo`.

[NOTE] daydream/post.py:265-288 — `file_parcel`'s docstring says it returns False and files nothing on every refusal; it returns True on the self/unknown/private/belongs refusals (to consume the command).

[NOTE] daydream/post.py:152-159, daydream/trace.py:94-100 — `_players`/`players` materialise every toon as a `Toon` on each call; a SQL filter would remove the per-NPC work. Player names are not unique: `write to Sam` picks the lowest slot silently.

[NOTE] daydream/objects.py:266-277 with daydream/growth.py:666 — the last-words match makes "spent dreamseed" answer to "dreamseed" again when no fresh seed is in scope (exact wins when one is); the comment at growth.py:661-664 overstates the alias change.

[NOTE] (security) daydream/post.py:265-303, daydream/accounts_cli.py:155-157 — a filed parcel of an authored thing would have been destroyed by `account delete` of the recipient; refusing parcels of things with a `home` (fixed above) closes the authored-object case. docs/DATA-LIFECYCLE.md should say letters and parcels left for others survive a delete or are sent home.

[NOTE] (security) daydream/trace.py, daydream/absence.py — the input log, documented as private to the dream digest, now feeds other players its metadata (last-seen time and room, awake/dozing/resting, who came through today). A requested household feature, no text shown; the docs and the door's note should say so.

[NOTE] (security, carried) daydream/accounts_cli.py:129-136 — the delete-during-talk gap. tests/test_config_edge.py:61 — a real tailnet address in a test fixture.

### Fixes Applied

- [BLOCK] daydream/trace.py `expand_placeholders`, called from `story._tell`, `effects._apply_narrate` and `effects.tell_others`; tests/test_trace.py `test_an_authored_topic_fills_who_came_through_today`. Re-reviewed: resolved.
- [BLOCK] `absence.take_note` returns None without clearing unless the toon is human-controlled; `slots._departed`'s `presence_changed` carries `except: t.id`; tests/test_dozing.py `test_the_away_note_survives_the_leavers_own_open_page`. Re-reviewed: resolved.
- [BLOCK] `ruff check --fix` (UP035, I001, F401) and the unused assignment removed; `ruff check .` clean. Re-reviewed: resolved.
- [WARN] `set_property` declared on `VERBS["give"]`; `file_parcel` passes `allowed` unchanged and refuses a thing whose `toons.home_of` is set, in authored words (`config.post.belongs_text`, engine default); tests/test_post.py `test_a_thing_that_goes_home_cannot_be_left_for_anyone`. The dozing hand-over half is declined (below). Re-reviewed: resolved as scoped.
- [WARN] the word cap applies to `topic["kind"] == "topic"` only; `story.topic_text` returns None for beats; tests/test_story.py `test_a_long_line_naming_an_open_beat_still_selects_it`. Re-reviewed: resolved.
- [WARN] `_handle_open` uses the key through `_execute_resolved` inside the same command; tests/test_verbs.py `test_open_with_the_key_in_hand_is_one_turn`. Re-reviewed: resolved.
- [WARN] (security) `MAX_WAITING_FROM_ONE` 5, `MAX_WAITING_FOR_ONE` 20, refusal `config.post.too_many_text` (engine default); `letters_waiting` queries only the viewer's letters (`objects.things_where_property`); tests/test_post.py `test_post_waiting_from_one_hand_is_capped`. Re-reviewed: resolved.
- [WARN] `presence_changed` world-scoped in both emitters; tests/test_dozing.py extended with a viewer in another room. Re-reviewed: resolved.
- [WARN] web/assets/main.js: `showThinking` clears the pending line; `renderSnapshot` clears the thinking line. Re-reviewed: resolved.

### Accepted Risks

- **A thing with a `home` handed to a DOZING dreamer** (`verbs._hand_to_player`, the tuck-away branch) waits in their satchel until they rest; a page that never returns holds it until `world rest-toon` or `account delete` sends it home. Declined this round: refusing it broke the arc contract (walkthrough players never open a socket, so every walkthrough hand-over runs through the dozing branch; `prologue-together` hands the escapement gear that way). Revisit with walkthrough players marked live (BACKLOG `dozing-handover-of-village-things`).

Carried forward (the standing register lives in SECURITY.md):

- **LLM-emitted effects take an unscoped, LLM-chosen target id** within each
  verb's allowed subset; rule-only kinds unreachable from LLM-facing dispatch.
- Stored prompt-injection via captured NPC memory; bootstrap `$MODEL` heredoc;
  `cmd_logs` path component; qpeek clone; `world reset` rm -rf operator trust;
  CGNAT hardcoding in tailscale mode.
- (security, carried) daydream/accounts_cli.py:129 — an account deleted while its player waits on a resident's reply leaves that reply and its `talk:`/`rel:` records behind. tests/test_config_edge.py:61 — a real tailnet address in a test fixture.

---
*Prior review (2026-09-28i, refresh, `32a32c1`): the second playtest's fixes (four commits); 0 BLOCK / 1 WARN / 2 NOTE, the WARN (a Safari-incompatible regex lookbehind) fixed in one /codefix cycle.*

<!-- REVIEW_META: {"date":"2026-09-29","commit":"ab44e90","reviewed_up_to":"ab44e90575fbf6850d21112412b700993fb6696c","base":"origin/main","tier":"refresh","block":0,"warn":6,"note":8} -->
