## Review — 2026-06-30 (commit: 9a5ad44)

**Summary:** Refresh review of the versioning / deploy / playtest-fixes turn
(`origin/main` b4d0401..`9a5ad44`, 22 files +1085/-74) since the prior pass at
f3da4f5. Covers: the build-SHA + `WORLD_VERSION` boot gate (migration 012,
`/status/build`, lifespan `check_world_compat`), the client redeploy auto-reload
+ `?v=<sha>` asset stamp, `bin/game` build-staleness line + `deploy` verb +
`world reset`, the forge id-leak fix (single-pass linkify), the double-examine
debounce + entity-link click fix, liveness-aware slot takeover, a first-entry
arrival line, the "around you" relabel, and the drift de-dup. Baseline stable:
644 medium / 407 short, both green. Security chain clean (0 BLOCK / 0 WARN /
1 NOTE); the linkify rewrite is itself a net XSS fix. 0 BLOCK / 0 WARN.

**External reviewers:** None configured.

### Findings

- [NOTE] daydream/api/ws.py (`_live_session_ids`) — session liveness is tracked
  in a plain `set` (add on WS connect, discard on disconnect), so a session with
  two concurrent connections (two tabs controlling the same toon) is marked
  not-live when EITHER closes while the other tab is still playing. A `Counter`
  (refcount: increment/decrement, live iff > 0) would be correct. Low impact: the
  only capability this gates is the direct claim-takeover, which a friend-scope
  caller can already achieve via kick-then-claim, so the protection is soft
  regardless. Fix-if-needed: swap the set for `collections.Counter`.
- [NOTE] daydream/server.py:140-145 — `root()` interpolates `version.build_sha()`
  into the served HTML asset URL (`?v={sha}`) without escaping. Not exploitable:
  `build_sha()` only yields git hex, a literal `-dirty`, the operator-set
  `DAYDREAM_BUILD_SHA`, or `"unknown"` — none request-reachable. Flagged
  defensively as an unescaped sink. Fix-if-needed: attribute-escape or restrict
  to `[0-9a-f-]`. (SECURITY.md NOTE.)

### Fixes Applied

None. Both findings are informational NOTEs (not auto-fixed); 0 BLOCK / 0 WARN.

### Accepted Risks

Carried forward from the prior entry, with the slot-endpoint note updated for the
liveness-gated takeover added this turn:

- **LLM-emitted effects take an unscoped, LLM-chosen target id.** `set_property`
  / `move_object` / `spawn_object` trust the effect's target id; a room-affordance
  data skill dispatches with the FULL effect vocabulary (advisory
  `effects_schema`), while `talk` enforces its narrower per-verb `allowed` subset.
  No privilege escalation (`set_property` writes `properties_json` only; auth
  columns unreachable). v2 `skills-authoring-and-security`. (SECURITY.md NOTE.)
- Friend-scope on slot/session endpoints (CSRF gated by `CsrfOriginMiddleware`).
  Claim now adopts a controlled toon only when its session has no live WS
  connection — strictly narrower than the prior refuse-all, and no new capability
  versus the already-permitted kick-then-claim. `/status/build` joins
  `/status/drift` as a session-unauthenticated but AccessMiddleware-gated
  observability endpoint (build SHA / world_version / migration number;
  low-sensitivity in friend-scope). Cookie `https_only=False`; `100.64.0.0/10`
  CGNAT hardcoding; tailscale `is_authed` bypass; `/cache/...` unauthenticated.
  Stored prompt-injection via captured memory; bootstrap `$MODEL` heredoc;
  `cmd_logs` path component; qpeek clone. Unbounded slot-create body + event
  queues.

### Carried-forward open NOTEs (pre-existing)

The prior register persists (parser raw-input not role-separated — low risk,
output strictly grounded; toon-view N+1 inventory query; dead `interpreter.py`;
admin.py + bootstrap.py `_write_db` non-transactional). None aggravated this turn.

---
*Prior review (2026-06-30, commit f3da4f5): full review of the playtest-polish turn (14/14); 0 BLOCK / 0 WARN / 2 NOTE.*

<!-- REVIEW_META: {"date":"2026-06-30","commit":"9a5ad44","reviewed_up_to":"9a5ad44968b44279b31f455761d6250ee83968fb","base":"origin/main","tier":"refresh","block":0,"warn":0,"note":2} -->
