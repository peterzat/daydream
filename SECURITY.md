## Security Review — 2026-06-30 (scope: paths)

**Summary:** Path-scoped review of `daydream/api/ws.py` and `daydream/server.py`
at HEAD `c6f7d70`, two commits past the prior pass (`9a5ad44`): the
codereview/security record commit and the NOTE-fix commit. Both prior NOTEs are
now remediated in scope. The session-liveness tracker moved from a plain `set`
to a refcounting `Counter` (`ws.py:405-427`), so a two-tab session stays "live"
until both tabs close; this only tightens the already-soft claim-takeover gate
and grants no capability. The build-SHA asset-URL sink is now `quote(..., safe="")`
escaped before interpolation into the served HTML (`server.py:144-149`), closing
the unescaped-sink NOTE: even a future request-derived build id could not break
out of the `?v=` query value or the surrounding `src` attribute (`"`, `<`, `>`,
`&`, space all percent-encode). Traced both producers into the WS path (the
`command` click frame and the `input` free-text frame) and every HTTP route
end to end against the middleware stack (AccessMiddleware IP gate +
CsrfOriginMiddleware + SessionMiddleware, all in `server.py:49-72`).

The spine held. **No secrets**, current or historical: a pattern scan of both
files and all 36 commits that touch them surfaced only `config.session_secret()`,
a comment, and the login form's `name="password"` field, none of them hardcoded
values. **No injection.** The `serve_cached_image` route (`server.py:168-180`)
splits to four `[^/]+` path segments, then explicitly rejects any segment
containing `/` or `..` and constrains the filename to a no-slash `.png`, which
also defeats the pathlib absolute-path footgun (an absolute segment needs a
leading `/`, which the `/`-reject catches) before the final `is_file()` gate;
no traversal. WS `command` frames are type-checked (`verb` non-empty str,
`dobj_id`/`iobj_id` str-or-None, `args` coerced) and handed to
`verbs.execute_command`, which validates in-scope + verb-applies, so the click
path stays strictly narrower than free text. Free-text `input` is grounded by
the parser to a closed verb + in-scope object id; the LLM never mutates state
directly, and the `"You think to yourself"` narrate fallback that echoes raw
player text is stored as a JSON string and rendered escaped by the SPA
(`linkifyEntities`), so there is no server-side sink. **No auth regression.**
The WS endpoint gates on `auth.is_authed` then resolves a toon only by explicit
`controller_session` match (no default fallback); `root()` redirects
unauthenticated callers to `/login`; `/status/build` + `/status/drift` +
`/cache/...` remain AccessMiddleware-gated observability/asset endpoints
(accepted, low-sensitivity, friend-scope). **No PII.** Net: 0 BLOCK / 0 WARN /
1 NOTE.

### Findings

- **[NOTE] daydream/api/ws.py:430-449 — WS command channel is not
  Origin-checked; cross-origin driving is blocked today only by the SameSite=Lax
  session cookie.** The `/ws` handshake is a GET, so `CsrfOriginMiddleware`
  (`csrf.py:73-76`, HTTP-only) does not gate it, and `ws_endpoint` itself never
  inspects `Origin`/`Referer`. The WS carries state-changing frames (take / drop
  / go / talk / free text), which is the same confused-deputy class that
  `CsrfOriginMiddleware` was added to close for the POST slot/session endpoints.
  **Not exploitable today.** The toon a connection drives is resolved from the
  `daydream_session` cookie's `id`, and that cookie is SameSite=Lax (Starlette
  1.0.0 default, not overridden at `server.py:49-54`), so a script-initiated
  cross-site `new WebSocket(...)` does not carry it: the attacker's socket
  resolves no toon and receives `needs_toon`. The protection is therefore
  implicit in the cookie default rather than explicit like the POST path's
  Origin check. **Attack vector (latent):** if the session cookie is ever
  loosened to SameSite=None (e.g. to embed the game cross-origin) without a
  parallel WS Origin check, a tailnet member who loads an attacker page would
  have their toon driven and their room state read cross-origin (bounded to
  friend-scope game-state, no privilege escalation). **Remediation (hardening):**
  validate the handshake `Origin` netloc against `Host` in `ws_endpoint` (reuse
  `csrf.origin_allows`) before `ws.accept()`, or document the SameSite=Lax
  dependency at the cookie config so a future loosening triggers the WS fix too.

### Accepted Risks

Carried forward from prior reviews; not re-flagged as findings. Items verified
against in-scope code this run are marked.

- **Tailscale-mode auth + friend-scope (verified in scope).** `auth.is_authed()`
  returns True unconditionally in `tailscale` mode; `AccessMiddleware`
  (CGNAT `100.64.0.0/10` + loopback) is the real gate. Any authed tailnet session
  may create / claim / kick / leave / delete any slot; the liveness-aware claim
  takeover is gated by `is_session_live` and grants nothing beyond the existing
  kick-then-claim. State-changing POSTs are CSRF-gated by `CsrfOriginMiddleware`.
  Per-session ownership is v2 `multi-user-shared-world`.
- **Session cookie `https_only=False` (verified in scope, `server.py:53`).**
  Friend-scope; box is LAN/Tailscale only.
- **`/status/build`, `/status/drift`, `/cache/...` are session-unauthenticated
  (verified in scope).** Tailnet/loopback-only via AccessMiddleware; expose build
  SHA / world_version / migration number / cache PNGs — low-sensitivity in
  friend-scope.
- **LLM-chosen effect targets are unscoped; per-skill `allowed_kinds` advisory
  (carried).** No privilege escalation (`set_property` writes `properties_json`
  only; auth columns unreachable); content renders escaped. v2 BACKLOG
  `skills-authoring-and-security`.
- **Stored prompt-injection via captured memory (carried).** Drift renders
  captured player text inside `<memory>` tags via a `SandboxedEnvironment`;
  output is banlist-checked and escaped. v0 impact bounded to mild voice
  deviation, no mutation capability.
- **Operator-trust / out-of-scope-this-run (carried).** `bin/game world reset`
  `rm -rf`; env-file sourcing; `world swap` loopback; admin restore tar
  extraction; engine bootstrap clones; unbounded slot-create body + event-queue
  growth. None take request-controlled input.

---
*Prior review (2026-06-30, paths, commit `9a5ad44`): the versioning / deploy /
liveness-takeover turn (build-SHA + WORLD_VERSION boot gate, `/status/build`,
asset-SHA stamping, liveness-aware slot takeover, drift de-dup, world-version
stamp at load). Found 0 BLOCK / 0 WARN / 1 NOTE; confirmed all SQL parameterized,
`build_sha()` shells a fixed git argv, the single-pass `linkify` rewrite is a net
XSS fix, and the redeploy-reload is attacker-inert. Its one NOTE (the unescaped
build-SHA HTML sink) is remediated at this run's HEAD by the `quote()` call.*

<!-- SECURITY_META: {"date":"2026-06-30","commit":"c6f7d704ebbf0fbd59da45b00a72d5a291bd7864","scope":"paths","block":0,"warn":0,"note":1,"scanned_files":["daydream/api/ws.py","daydream/server.py"]} -->
