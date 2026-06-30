## Review — 2026-06-30 (commit: c6f7d70)

**Summary:** Full review of the two-NOTE follow-up (`origin/playtest-fixes-and-
versioning`..`c6f7d70`, 4 files +71/-13): `daydream/api/ws.py` and
`daydream/server.py` plus their tests. Both prior NOTEs are remediated here —
session liveness moved from a plain `set` to a refcounting `Counter` (a two-tab
session stays live until both close), and the build-SHA HTML sink is now
`quote(version.build_sha(), safe="")`-escaped. Baseline stable: 407 short / 82
targeted (ws + frontend + slots), green. Security re-scan of the two changed
source files: 0 BLOCK / 0 WARN / 1 NOTE (a pre-existing latent item below).
0 BLOCK / 0 WARN.

**External reviewers:** None configured.

### Findings

- [NOTE] daydream/api/ws.py:430-449 (pre-existing; surfaced because the file was
  touched, NOT introduced this turn) — the `/ws` handshake is a GET, so
  `CsrfOriginMiddleware` (HTTP-only) doesn't gate it and `ws_endpoint` never
  inspects `Origin`/`Referer`, yet the socket carries state-changing frames
  (take/drop/go/talk/free-text). Not exploitable today: the toon is resolved from
  the `daydream_session` cookie, which is SameSite=Lax (Starlette default, not
  overridden), so a script-initiated cross-site `new WebSocket()` carries no
  cookie and resolves no toon (`needs_toon`). Latent: loosening the cookie to
  SameSite=None without a parallel WS check would open cross-site WebSocket
  hijacking (bounded to friend-scope game state, no privilege escalation).
  Fix-if-needed: validate the handshake `Origin` against `Host` in `ws_endpoint`
  (reuse `csrf.origin_allows`), or document the SameSite dependency at the cookie
  config. (SECURITY.md NOTE.)

### Fixes Applied

None in this review run (no `/codefix`). The two changes under review are
themselves the fixes for the prior review's two NOTEs (liveness refcount,
build-SHA escaping), made before the review and verified by new tests.

### Accepted Risks

Carried forward from the prior entry:

- **LLM-emitted effects take an unscoped, LLM-chosen target id.** `set_property`
  / `move_object` / `spawn_object` trust the effect's target id; a room-affordance
  data skill dispatches with the FULL effect vocabulary, while `talk` enforces its
  narrower per-verb `allowed` subset. No privilege escalation. v2
  `skills-authoring-and-security`. (SECURITY.md NOTE.)
- Friend-scope on slot/session endpoints (CSRF gated by `CsrfOriginMiddleware`);
  liveness-gated claim takeover (no new capability vs kick-then-claim).
  `/status/build` + `/status/drift` session-unauthenticated but AccessMiddleware-
  gated observability. The `/ws` channel relies on the SameSite=Lax cookie default
  for cross-site protection (the NOTE above). Cookie `https_only=False`;
  `100.64.0.0/10` CGNAT hardcoding; tailscale `is_authed` bypass; `/cache/...`
  unauthenticated. Stored prompt-injection via captured memory; bootstrap `$MODEL`
  heredoc; `cmd_logs` path component; qpeek clone. Unbounded slot-create body +
  event queues.

### Carried-forward open NOTEs (pre-existing)

Parser raw-input not role-separated (low risk, output grounded); toon-view N+1
inventory query; dead `interpreter.py`; admin.py + bootstrap.py `_write_db`
non-transactional. None aggravated this turn.

---
*Prior review (2026-06-30, commit 9a5ad44): full review of the versioning/deploy/playtest-fixes turn; 0 BLOCK / 0 WARN / 2 NOTE (both resolved here).*

<!-- REVIEW_META: {"date":"2026-06-30","commit":"c6f7d70","reviewed_up_to":"c6f7d704ebbf0fbd59da45b00a72d5a291bd7864","base":"origin/playtest-fixes-and-versioning","tier":"full","block":0,"warn":0,"note":1} -->
