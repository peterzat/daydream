## Review — 2026-06-30 (commit: 14d624d)

**Review scope:** Refresh review. Focus: 2 files changed since prior review
(commit 777a289) — `worlds/bunny.json` and `tests/test_world_load.py`. 0
already-reviewed files re-modified.

**Summary:** Closeout of the objects+verbs turn's one open criterion (the live
world reset, SPEC 19/19). The destructive reset was performed and verified live
against the running server (WS E2E: snapshot + verb bar, examine, walk, Rook
spawning the papers via the real local LLM); two content bugs in the reset world
surfaced by running it and were fixed in `worlds/bunny.json` (Wren
`is_human_controlled` 1→0 so the seed toon is claimable; bare item names so verb
wording reads "the brass lantern" not "the a brass lantern"). `test_world_load`
adjusted to select the acting player by `slot=1` (Wren is now
`is_human_controlled=0`). Tests green: 377 short / 591 medium. 0 BLOCK / 0 WARN.

**External reviewers:** None configured.

**Security:** No new runtime security surface. The changed `worlds/bunny.json`
was in the prior path-scoped scan (commit 777a289, 0 BLOCK / 0 WARN / 1 NOTE,
carried forward); the only other changed file is `tests/test_world_load.py`, a
test with no runtime surface. No re-scan warranted.

### Findings

[NOTE] tests/test_world_load.py:~178 vs worlds/bunny.json (Rook dialogue) — the
integration test mocks the dialogue LLM to spawn a thing named "a sheaf of
papers", while the authored `dlg-rook` prompt now instructs the name "sheaf of
papers".
  Evidence: the test asserts `o.name == "a sheaf of papers"` against its own
  mock; the live prompt emits "sheaf of papers".
  Why only NOTE: both are internally consistent (the test controls its mock and
  exercises the dialogue→spawn plumbing — binding resolution, allowlist, dedup —
  not the exact noun). The live spawn name was verified separately by the WS
  E2E. Optional: align the mock's name to the prompt for fidelity.

### Fixes Applied

None. 0 BLOCK / 0 WARN; the NOTE is informational.

### Accepted Risks

Carried forward unchanged from the prior entry:

- **LLM-emitted effects take an unscoped, LLM-chosen target id.** `set_property`
  / `move_object` / `spawn_object` trust the effect's target id; a room-affordance
  data skill (`stoke` / `tend`) dispatches with the FULL effect vocabulary
  (advisory `effects_schema`), while the `talk` verb enforces its narrower per-verb
  `allowed` subset. No privilege escalation (`set_property` writes
  `properties_json` only; auth columns unreachable). v2 `skills-authoring-and-
  security`. (SECURITY.md NOTE.)
- Friend-scope on slot/session endpoints (CSRF gated by `CsrfOriginMiddleware`).
  Cookie `https_only=False`; `100.64.0.0/10` CGNAT hardcoding; tailscale `is_authed`
  bypass; `/cache/...` + `/status/drift` unauthenticated. Stored prompt-injection
  via captured memory; bootstrap `$MODEL` heredoc; `cmd_logs` path component;
  qpeek clone. Unbounded slot-create body + event-subscriber queues.

### Carried-forward open NOTEs (pre-existing)

The prior register persists (parser raw-input not role-separated — low risk,
output strictly grounded; toon-view N+1 inventory query; dead `interpreter.py`;
admin.py + bootstrap.py `_write_db` non-transactional). None aggravated this turn.

---
*Prior review (2026-06-30, commit 777a289): full review of the objects + local
LLMs turn (41 files); 0 BLOCK / 0 WARN / 3 NOTEs (parser raw-input wrap;
toon-view N+1 inventory; dead interpreter.py). Security 0 BLOCK / 0 WARN / 1 NOTE
(unscoped LLM-effect target ids, accepted). Pushed.*

<!-- REVIEW_META: {"date":"2026-06-30","commit":"14d624d","reviewed_up_to":"14d624dcf26b45ab5cdbab9a271cd3dd4ecff587","base":"origin/main","tier":"refresh","block":0,"warn":0,"note":1} -->
