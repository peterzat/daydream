## Review — 2026-09-29h (commit: 087fc4a)

**Summary:** Refresh review of `0d81745..087fc4a`: the two lint errors CI caught in the glimpses push (an import block ruff wanted wrapped, an unused mock handle; no behaviour change) and the playtest note `docs/playtests/2026-09-29-creative-break.md` (light: its examples match the battery's recorded replies, its ZIL citations match the research, no instance names). `/security` on the paths changed since `de5e11b` (the /codefix fixes and the lint fix): no new finding; privacy, hidden exits, slow input, an injected tail and the village's never-words were probed. Tests: `ruff check .` clean; test_glimpse and test_parser 117; short 1571.

**External reviewers:**
None configured.

### Findings

No new issues.

### Open WARN (needs the operator; not for /codefix)

[WARN] (security, carried) tools/agent_guard.py:36-38, :47, :264-267 — a recursive search one folder below home, and a combined short-flag spelling of gh's show-token option, get no opinion from the guard. The guard asks the operator before any change to itself (`PROTECTED`, :199-202); the fix waits for a session with the operator present. Not accepted; not downgraded.

### Notes (carried from 2026-09-29g, still present)

[NOTE] daydream/glimpse.py — function words count as nouns ("take the" spends a model call).
[NOTE] daydream/parser.py:222 — "x tin. north" does not chain; CLAUDE.md's "one-letter aliases act only alone" is stale.
[NOTE] daydream/glimpse.py — on equal-length names the first entry whose conditions hold wins, and `validate_glimpsed` accepts any `verbs` key.
[NOTE] worlds/lost-hours/regions/01-clocktower.json — a carried Wend's ladder in the cellar still reads "no ladder in the cellar is tall enough".
[NOTE] Zork's LIFT now resolves to take; Zork is frozen.
[NOTE] (security, carried) placeholders over letter bodies and appearances; `play` prints a grown place's description unmarked (and a glimpse look repeats it, glimpse.py:342-343); the server keeps control characters in typed lines; the delete-during-talk gap.

### Fixes Applied

- The two lint errors (15d8c85).

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
*Prior review (2026-09-29g, refresh, `de5e11b`): the glimpses push; a fresh reviewer's probes found nine WARNs (the "carry" alias stealing a give, alias idioms, look-at self and room words, dark rooms, validation holes, long names, plural matching, exits in prose, an untested outage), all fixed and re-reviewed in 0094b57; security found nothing new.*

<!-- REVIEW_META: {"date":"2026-09-29","commit":"087fc4a","reviewed_up_to":"087fc4a105db23a8d9c75a327f9f570c4f1705e8","base":"origin/main","tier":"refresh","block":0,"warn":1,"note":6} -->
