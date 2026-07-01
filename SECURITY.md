## Security Review — 2026-07-01 (scope: paths)

**Summary:** Path-scoped review of `bin/game`, `daydream/api/ws.py`,
`daydream/review.py`, and `daydream/toons.py` at HEAD `5b181d1`. The prior pass's
one open NOTE (the `/ws` handshake was not Origin-checked, relying only on the
SameSite=Lax cookie for cross-site protection) is now REMEDIATED on this branch:
`ws_endpoint` calls `csrf.origin_allows(...)` before `ws.accept()` (`ws.py:441-443`),
closing the WS confused-deputy vector at the app layer. Traced every dimension
across the four files. **No secrets** (current or historical): the scan surfaced
only `bin/game`'s reference to the gitignored `~/.config/daydream/secrets.env`
path and the `DAYDREAM_PASSWORD` env-var name, never a hardcoded value; three
commits of `bin/game` history are clean. **No injection.** `toons.py` routes all
six `_query` call sites through literal `WHERE` strings with `?`-bound params, and
every INSERT/UPDATE/DELETE (`create_toon_in_slot`, `claim_slot`, `kick_slot`,
`delete_slot`) is fully parameterized; request-derived values (`name`,
`appearance_seed`, `session_id`) are always bindings, never interpolated.
`review.py` composes its `index.html` with `html.escape` on every dynamic value,
including the LLM-generated NPC narrate lines and image prompts, and has no
`shell=True`/`os.system`/`eval`/`exec` (its only external call is the in-process
`admin.main([...])`). `bin/game` takes no network input; its destructive paths
(`world reset` `rm -rf`, `.env`/secrets sourcing, `cmd_logs` path component) are
operator-trust and carried. **No auth regression.** `ws_endpoint` gates on
`is_authed` → `origin_allows` → a `controller_session`-only toon resolution (no
default fallback), all before `accept()`. Net: **0 BLOCK / 0 WARN / 0 NOTE.**

### Findings

No security issues identified in the reviewed scope.

The prior review's only open item is now closed:

- **[REMEDIATED] daydream/api/ws.py:441-443 — WS handshake now Origin-checked.**
  The prior NOTE (the `/ws` GET bypassed the HTTP-only `CsrfOriginMiddleware`, so
  cross-origin driving was blocked only by the SameSite=Lax cookie default) is
  fixed: `ws_endpoint` rejects a cross-origin handshake via `csrf.origin_allows`
  before `ws.accept()`. Verified sound: the check runs pre-accept; the no-Origin
  allow path is safe because a browser always sends `Origin` on a WS opening
  handshake (a cross-site attacker cannot omit it), and a non-browser client that
  omits it never carries the victim's SameSite=Lax session cookie, so it resolves
  no toon. Defense in depth now sits at the app layer, no longer implicit in the
  cookie default.

### Accepted Risks

Carried forward from prior reviews; not re-flagged as findings. Items verified
against in-scope code this run are marked.

- **Tailscale-mode auth + friend-scope (verified in scope).** `auth.is_authed()`
  returns True unconditionally in `tailscale` mode; `AccessMiddleware`
  (CGNAT `100.64.0.0/10` + loopback) is the real gate. Any authed tailnet session
  may create / claim / kick / leave / delete any slot (`toons.py` is the data
  layer; authz lives at the slot/session endpoints). State-changing POSTs are
  CSRF-gated by `CsrfOriginMiddleware`; the WS channel is now Origin-gated too.
  Per-session ownership is v2 `multi-user-shared-world`.
- **Liveness-aware claim takeover (verified in scope, `toons.py:218-245`).** The
  `can_take_over` callback lets a session adopt a toon whose controlling session
  has no live WS connection; grants nothing beyond the existing kick-then-claim.
- **Operator-trust, not request-controlled (verified in scope, `bin/game`).**
  `world reset` `rm -rf` of `live.db*` + the world image cache; `.env` +
  `~/.config/daydream/secrets.env` sourcing; the `cmd_logs` first-arg path
  component; FastAPI binding `0.0.0.0` (AccessMiddleware is the boundary). None
  take network input.
- **`bin/game review` is a design-time local tool (verified in scope).** Runs on
  trusted checked-in inputs (`worlds/bunny.json`, `tests/drift/aesthetics/*.json`),
  writes an escaped HTML sheet the operator opens; consistent with the keyless
  generation policy (no cloud key, no `litellm` vision call).
- **Session cookie `https_only=False`; `/status/*` + `/cache/...` session-
  unauthenticated (AccessMiddleware-gated); LLM-chosen effect targets unscoped
  (`set_property` writes `properties_json` only, no auth-column reach); stored
  prompt-injection via captured memory (escaped, banlist-checked, no mutation).**
  All carried from prior full/path reviews; none aggravated by the in-scope files.

---
*Prior review (2026-06-30, paths, commit `c6f7d70`): reviewed `daydream/api/ws.py`
and `daydream/server.py`. Found 0 BLOCK / 0 WARN / 1 NOTE — the WS-handshake
Origin gap (blocked then only by SameSite=Lax). Confirmed no secrets across 36
commits, the `serve_cached_image` route defeats path traversal, WS command frames
are type-checked, and the build-SHA HTML sink is `quote()`-escaped. That single
NOTE is remediated at this run's HEAD (commit `07395bd`).*

<!-- SECURITY_META: {"date":"2026-07-01","commit":"5b181d15071667a63f03b98c3ea7d6f36e581ad8","scope":"paths","block":0,"warn":0,"note":0,"scanned_files":["bin/game","daydream/api/ws.py","daydream/review.py","daydream/toons.py"]} -->
