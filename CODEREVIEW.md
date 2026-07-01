## Review — 2026-07-01 (commit: 5b181d1)

**Summary:** Refresh review of the verification-infrastructure turn
(`origin/playtest-fixes-and-versioning`..`5b181d1`; 11 code files + docs). Scope:
the batched-eyeball test architecture — `daydream/review.py` (new offline
contact-sheet harness), `daydream/toons.py` (`delete_slot` now drops carried
items into the room instead of destroying them), `bin/game` (`review`
subcommand), the forge perceptual anchor + golden, the glob-derived
voice-baseline manifest, the overlay reconnect-contract test hardening, and the
`daydream/api/ws.py` cross-origin `/ws` handshake fix (`07395bd`, which
remediates the prior review's one open NOTE). Also reviewed: the mid-turn
removal of an API-key litellm "vision gate" (added then deleted within the
unpushed range, so it nets to nothing in the shipped diff) and the reframe of
the aesthetic critic to the in-TUI agent (no cloud key). Baseline: 411 short /
654 medium, green. Security re-scan of the four changed source files: 0 BLOCK /
0 WARN / 0 NOTE (prior WS NOTE confirmed fixed).

**External reviewers:** None configured.

### Findings

No issues found. The WS Origin check correctly reuses the tested
`csrf.origin_allows` (fails open only for non-browser clients, which carry no
session cookie); `review.py` HTML-escapes every dynamic value including
LLM-generated narrate, isolates per-NPC dispatch errors, saves/restores
`DAYDREAM_DATA_DIR`, and never touches `live.db`; `toons.delete_slot` reparents
carried things before deleting the toon (FK satisfied) with a no-room fallback;
`bin/game review` is a quoted `python -m` wrapper with no injection sink.

Known content deferral (not a code finding): the forge perceptual golden is
baselined on a render that does NOT read as a blacksmith's forge — the
watercolor LoRA can't render a legible anvil/bellows. Tracked as
`forge-render-legibility` in BACKLOG.md; the golden re-ratifies after any seed/
LoRA rework. This is a content limit, honestly recorded in SPEC.md and BACKLOG.md.

### Fixes Applied

None (no BLOCK/WARN findings).

### Accepted Risks

Carried forward from the prior entry (unchanged and unaggravated this turn):

- **LLM-emitted effects take an unscoped, LLM-chosen target id.** `set_property`
  / `move_object` / `spawn_object` trust the effect's target id; room-affordance
  data skills dispatch with the full effect vocabulary, while `talk` enforces its
  narrower per-verb `allowed` subset. No privilege escalation. v2
  `skills-authoring-and-security`. (SECURITY.md NOTE.)
- Friend-scope on slot/session endpoints (CSRF-gated by `CsrfOriginMiddleware`;
  `/ws` now Origin-checked too); liveness-gated claim takeover; `/status/build`
  + `/status/drift` + `/cache/...` session-unauthenticated but AccessMiddleware-
  gated. Cookie `https_only=False`; `100.64.0.0/10` CGNAT hardcoding; tailscale
  `is_authed` bypass. Stored prompt-injection via captured memory; bootstrap
  `$MODEL` heredoc; `cmd_logs` path component; qpeek clone; `world reset` `rm -rf`
  operator-trust. Unbounded slot-create body + event queues.

### Carried-forward open NOTEs (pre-existing)

Parser raw-input not role-separated (low risk, output grounded); toon-view N+1
inventory query; dead `interpreter.py`; admin.py + bootstrap.py `_write_db`
non-transactional. None aggravated this turn.

---
*Prior review (2026-06-30, commit c6f7d70): full review of the two-NOTE follow-up (liveness refcount, build-SHA escaping); 0 BLOCK / 0 WARN / 1 NOTE (the WS-CSRF NOTE, now fixed in 07395bd).*

<!-- REVIEW_META: {"date":"2026-07-01","commit":"5b181d1","reviewed_up_to":"5b181d15071667a63f03b98c3ea7d6f36e581ad8","base":"origin/playtest-fixes-and-versioning","tier":"refresh","block":0,"warn":0,"note":0} -->
