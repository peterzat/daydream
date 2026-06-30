## Security Review — 2026-06-30 (scope: paths)

**Summary:** Path-scoped review of the versioning / deploy / liveness-claim turn
(HEAD `9a5ad44`, the 13-commit run `b4d0401`..`9a5ad44`), which lands after the
prior security pass at `f3da4f5`. Scope: the build-SHA + WORLD_VERSION axes
(`daydream/version.py` + `migrations/012_world_version.sql`, both new to scope),
the server boot gate + `/status/build` + asset-SHA stamping (`daydream/server.py`),
the liveness-aware slot takeover (`daydream/api/slots.py`, `daydream/toons.py`,
`daydream/api/ws.py`), the drift laconic-prompt + near-duplicate suppressor
(`daydream/drift.py`), the world-version stamp at load (`daydream/llm/bootstrap.py`),
the `deploy` / `world reset` verbs + build-staleness probe (`bin/game`), and the
SPA's redeploy-reload + single-pass linkify + slot-claim UI (`web/assets/main.js`,
`web/index.html`). Trust model is unchanged friend-scope: `AccessMiddleware`
(tailnet CGNAT `100.64.0.0/10` + loopback) + `CsrfOriginMiddleware` are the outer
gates; in default `tailscale` mode `auth.is_authed()` is True unconditionally, so
tailnet membership is the authorization.

The security spine held under tracing across every changed file. **No new
injection.** All SQL is parameterized: the `claim_slot` takeover UPDATE
(`toons.py:240-244`), the world-version INSERT (`bootstrap.py:452-459`), and
migration 012 are static or bound; `version.check_world_compat`
(`version.py:106`) reads a fixed `SELECT`. `build_sha()` shells `git` as a fixed
argv list (no shell), times out at 2 s, and falls to `"unknown"`
(`version.py:52-70`). **The linkify change is a net XSS fix, not a regression.**
`linkifyEntities` (`main.js:424-449`) now escapes the full text once, escapes
every alias and object-id, builds one longest-alias-first regex over the escaped
text, and re-inserts only matched (already-escaped) substrings plus an
`escape()`d id, retiring the per-alias iterative replace that nested spans and
leaked ids into rendered text (the forge id-garbage). Player-created toon names
reach it only after `escape` + `escapeRegex`. **The redeploy-reload is
attacker-inert:** `snap.build` is compared, never written to the DOM; the reload
is same-origin `location.reload()` behind a 15 s sessionStorage anti-thrash guard
(`main.js:42-57,103-115`). **The slot takeover is a tightening, not an
escalation:** `claim_slot` adopts a toon held by ANOTHER session only when
`is_session_live(controller)` is False (`slots.py:112-113`, `toons.py:232-235`,
`ws.py:406-409`) — strictly narrower than the prior "refuse all controlled" and
well inside the already-accepted friend-scope where any authed session may
kick-then-claim any slot; the POST is CSRF-gated. **Drift gained no mutation
capability:** the laconic prompt + `_is_near_duplicate` suppressor
(`drift.py:479-493`) are pure string work; the memory-influenced LLM path stays
`<memory>`-wrapped, banlist-checked, escaped on render, and emits only a narrate
plus a fixed-bucket mood nudge. **No secrets / no PII:** the pattern scan over all
eleven scoped files returned only a doc reference to reading `ANTHROPIC_API_KEY`
from env (`bootstrap.py:17`), the `config.session_secret()` call site, the login
form's `password` field, and `{name}` drift tokens. Net: 0 BLOCK / 0 WARN / 1 NOTE.

### Findings

- **[NOTE] daydream/server.py:140-145 — build SHA interpolated into served HTML
  without escaping.** `root()` stamps the asset refs via
  `index.read_text().replace("/assets/main.js", f"/assets/main.js?v={sha}")`
  where `sha = version.build_sha()`. Not currently exploitable: `build_sha()`
  returns only `git rev-parse --short=12 HEAD` output (hex), an optional literal
  `-dirty` suffix, the operator-set `DAYDREAM_BUILD_SHA` env var, or `"unknown"`
  — none of which an HTTP/WS client can influence, so there is no reachable
  injection today. Recorded as a defense-in-depth observation: this is an
  unescaped sink, so if a future change ever derives the build id from
  request-controlled input (a header, query param, or DB field), it becomes a
  live reflected-XSS vector. Remediation if that day comes: HTML-attribute-escape
  `sha` before interpolation, or restrict it to `[0-9a-f-]`.

### Accepted Risks

Carried forward from prior reviews; none re-flagged as findings. Items verified
against in-scope code this run are marked; the rest live in modules outside this
path-scoped scan and are carried unexamined.

- **Friend-scope slot/session endpoints, now including liveness-aware takeover
  (verified in scope).** Any authed session may create / claim / kick / leave /
  delete any slot. New this turn: `claim` can take over a toon held by another
  session when that session has no live WS connection
  (`slots.py:112-113`, `toons.py:218-245`). This grants no capability beyond the
  existing kick-then-claim path and is gated by `is_session_live`; a TOCTOU
  window (victim reconnects between the liveness check and the UPDATE) yields at
  most an effect equivalent to a kick, which is already permitted. CSRF on these
  POSTs is closed by `CsrfOriginMiddleware`. Per-session ownership is v2
  `multi-user-shared-world`.
- **`/status/build` and `/status/drift` are session-unauthenticated, gated only by
  AccessMiddleware (verified in scope).** `/status/build` (`server.py:101-116`)
  joins `/status/drift` as a tailnet/loopback-only observability endpoint with no
  session check. It exposes the running build SHA (with a `-dirty` marker),
  `world_version`, and the max migration number — low-sensitivity in friend-scope.
  Same posture as the already-accepted `/status/drift`.
- **LLM-chosen effect targets are unscoped; per-skill `allowed_kinds` is advisory
  (carried).** The standalone room-affordance data-skill path dispatches with the
  full `ALLOWED_KINDS`; an effect's target id is trusted without a scope/ownership
  check. Bounded to friend-scope game-state: `set_property` writes
  `properties_json` only and cannot reach the auth columns (`slot`,
  `controller_session`, `is_human_controlled`, `kicked_at`), so no privilege
  escalation; `talk` keeps its narrower per-verb allowlist; content renders
  escaped. Deeper fix is v2 BACKLOG `skills-authoring-and-security`.
- **Stored prompt-injection via captured memory (verified in scope).** Drift's
  `_DRIFT_USER_TEMPLATE` renders `{{ m.text }}` (captured player text) inside
  `<memory>` tags via a `SandboxedEnvironment`; output is banlist-checked and
  escaped. v0 impact bounded to mild voice/tone deviation, now witnessed by a
  present player, with no new mutation capability. Deeper fix is v2.
- **Tailscale-mode auth (carried).** `auth.is_authed()` returns True
  unconditionally; `AccessMiddleware` (CGNAT `100.64.0.0/10` + loopback) is the
  real gate; cookie `https_only=False` (LAN/Tailscale only). `access.py` not in
  this scan's scope.
- **Operator-trust / out-of-scope-this-run (carried).** `bin/game world reset`
  `rm -f`/`rm -rf` over env-derived `$LIVE_DB` / `$DAYDREAM_DATA_DIR` and the
  hardcoded `w-bunny` cache dir; `bin/game` env-file sourcing; `world swap`
  loopback; admin restore tar extraction; engine bootstrap clones; unbounded
  slot-create body + event-subscriber queues. None take request-controlled input;
  all live behind the operator-trust boundary.

---
*Prior review (2026-06-30, paths, commit `f3da4f5`): the playtest-polish turn
(picker-first WS entry, two-producer command bus, witnessed drift, grounded-parser
fast-paths, closed verb registry, the SPA scene/inventory/overlay rendering, the
bunny.json envelope). Found 0 BLOCK / 0 WARN / 0 new NOTE; confirmed the LLM never
mutates state directly, the click path is strictly narrower than free text,
per-verb effect allowlists are enforced, and picker-first retired the legacy
`t-wren` shared-toon fallback (a net security improvement).*

<!-- SECURITY_META: {"date":"2026-06-30","commit":"9a5ad44968b44279b31f455761d6250ee83968fb","scope":"paths","block":0,"warn":0,"note":1,"scanned_files":["bin/game","daydream/api/slots.py","daydream/api/ws.py","daydream/drift.py","daydream/llm/bootstrap.py","daydream/server.py","daydream/toons.py","daydream/version.py","migrations/012_world_version.sql","web/assets/main.js","web/index.html"]} -->
