## Review — 2026-09-29b (commit: 69760f7)

**Summary:** Refresh review of one follow-up commit over this morning's reviewed state (`ab44e90`): the dreamer form's frame sentence, the door's note on what other dreamers see, docs/DATA-LIFECYCLE.md on post and on what other dreamers see, Fen's words for the two post refusals the review added, the loader's check that `config.post.keeper` names a toon, and a backlog entry. Focus set read in full (8 files); the already-reviewed set checked for interactions (the validator against the live world's synthesis: the keeper is `t-fen`). `/security` over the 22 files changed since its last scan: 0 BLOCK / 0 WARN / 4 NOTE (2 new). Tests stable: short 1375, medium 2036, `ruff check .` clean, `node --check` on both scripts.

**External reviewers:**
None configured.

### Findings

No BLOCK or WARN.

[NOTE] (security) daydream/skills/effects.py:347, daydream/trace.py:185-193, daydream/post.py:257 — `expand_placeholders` runs over every narrated text, player text included: a letter containing `{dreamers_today}` reads back as the clause, and a dreamer may be named `{dreamers_today}`. No confidentiality impact (the clause is public), but a template over untrusted text. Suggested: neutralise braces in player fields (`post._line`'s `{text}`, dreamer names) or expand authored strings only. BACKLOG `placeholders-over-player-text`.

[NOTE] (security) daydream/api/slots.py:311-337, daydream/toons.py:121 — a world-scoped `presence_changed` re-snapshots every connected player, and leave/claim are unthrottled: a signed-in friend looping leave and claim costs two snapshots per connected player per cycle (0.74 ms each in a small room). Transient, stoppable with `account disable`.

[NOTE] web/assets/style.css:289 — `.dreamer-note` colours with `var(--ink-soft, inherit)`; no `--ink-soft` token exists, so the fallback applies. Harmless; drop the colour or name a real token.

[NOTE] (security, carried) daydream/accounts_cli.py:129-136 — the delete-during-talk gap. tests/test_config_edge.py:61 — a real tailnet address in a test fixture.

### Fixes Applied

None.

### Accepted Risks

- **A thing with a `home` handed to a DOZING dreamer** (`verbs._hand_to_player`, the tuck-away branch) waits in their satchel until they rest; declined this morning because walkthrough players count as dozing (BACKLOG `dozing-handover-of-village-things`; also in SECURITY.md).

Carried forward (the standing register lives in SECURITY.md):

- **LLM-emitted effects take an unscoped, LLM-chosen target id** within each
  verb's allowed subset; rule-only kinds unreachable from LLM-facing dispatch.
- Stored prompt-injection via captured NPC memory; bootstrap `$MODEL` heredoc;
  `cmd_logs` path component; qpeek clone; `world reset` rm -rf operator trust;
  CGNAT hardcoding in tailscale mode.
- (security, carried) daydream/accounts_cli.py:129 — an account deleted while its player waits on a resident's reply leaves that reply and its `talk:`/`rel:` records behind. tests/test_config_edge.py:61 — a real tailnet address in a test fixture.

---
*Prior review (2026-09-29, refresh, `ab44e90`): the beta rehearsal's household layer, nineteen commits; 3 BLOCK / 6 WARN / 8 NOTE with /security 0/1/4; every BLOCK and five WARNs fixed in one /codefix cycle (the dusk tally on every telling path, the away note surviving the leaver's page, one turn per open, capped post, world-scoped presence, one transient line, ruff clean); the dozing hand-over of village things declined and recorded as an accepted risk.*

<!-- REVIEW_META: {"date":"2026-09-29","commit":"69760f7","reviewed_up_to":"69760f7baca60dce17002d0d843efd0b572f610a","base":"origin/main","tier":"refresh","block":0,"warn":0,"note":4} -->
