## Security Review — 2026-07-01 (scope: paths)

**Summary:** Path-scoped review of the playable-quest-loop turn at HEAD `e769ad6`:
the two-object verbs (`give`/`use`), object state, the `spawn_object` verbs
passthrough, the world-authoring loader, versioning, the frontend two-step
staging, and the new canonical world `worlds/clockmakers-loft.json`. Traced every
dimension across all 11 files. **No secrets** (current or historical): the scan
is clean and `bin/game`/`bootstrap.py` git history over the quest-loop commits
surfaces no hardcoded value — the only `ANTHROPIC_API_KEY` reference is a
docstring naming the env var for the DEPRECATED design-time LLM path, and
`version.py` reads the operator-set `DAYDREAM_BUILD_SHA` override. **No
injection.** `objects.py` and `bootstrap._write_db` are fully parameterized
(the derived slug and every authored field are `?`-bound; `by_slug` uses
`json_extract` with a bound param); `main.js` routes every dynamic value through
`escape()` or `textContent`, and `linkifyEntities` escapes before wrapping alias
matches, so even LLM-generated narration cannot inject markup. **No new
privilege path.** The new deterministic verbs scope-validate both dobj and iobj
through `_resolve_in_scope`, `_handle_use` hardcodes `key="state"`/authored
`value` (no client-chosen property write), and `_apply_spawn_object` limits a
spawn's properties to `{seed,is_unique,generated_by?,verbs?}` — so a granted
`verbs` list is inert (no authored rule to trigger) and does not widen the
pre-existing LLM-chosen-effect-target accepted risk. The `/ws` handshake gate
(`is_authed` → `origin_allows` → `controller_session`-only toon resolution) is
intact and client `command` frames reach only `execute_command`, never the raw
effect API. Net: **0 BLOCK / 0 WARN / 1 NOTE.**

### Findings

- **[NOTE] web/index.html:1-8 — no Content-Security-Policy (defense in depth).**
  The app shell ships no CSP (meta tag or header) and no `X-Content-Type-Options`.
  Attack vector: none reachable today — the concrete XSS surface (LLM-generated
  narration and player-supplied toon names rendered via `innerHTML`) is already
  fully mitigated by `escape()` / `textContent` / the escape-then-wrap
  `linkifyEntities`, which this review re-verified. A CSP (`default-src 'self'`)
  would be a second, orthogonal layer that blunts any future escaping regression
  and forbids inline/remote script. Informational only; raised now because this
  is the first review with `web/index.html` in scope. Remediation: add a
  `default-src 'self'` CSP (all assets are same-origin) plus
  `X-Content-Type-Options: nosniff`, ideally as response headers in the FastAPI
  layer so it also covers `/assets/*`.

### Accepted Risks

Carried forward from prior reviews; not re-flagged as findings. Items re-verified
against in-scope code this run are marked.

- **LLM-emitted effects take an unscoped, LLM-chosen target id (re-verified in
  scope).** `set_property` / `move_object` / `spawn_object` trust the effect's
  target id; the `talk` dialogue path (a data skill) is the one LLM producer and
  is bound to its per-verb `allowed` subset. The new `give`/`use`/`open`/`read`
  verbs are DETERMINISTIC and build their effects from scope-validated objects +
  authored strings, so they do not widen this gap. `_apply_spawn_object` cannot
  set arbitrary properties (only seed/verbs/aliases/provenance), so an
  LLM-spawned object carries no `use`/`gives`/`state` rule and its granted verbs
  are inert. v2 `skills-authoring-and-security`.
- **Shared-world mutation: any authed tailnet session may drive verbs on any
  in-scope shared object (re-verified in scope).** `use`/`give`/`open` on a
  room fixture/NPC mutate the one shared world for everyone in that room. This is
  the intended single-shared-world design; per-session ownership is v2
  `multi-user-shared-world`. State-changing POSTs are CSRF-gated by
  `CsrfOriginMiddleware` and the `/ws` handshake is Origin-gated
  (`csrf.origin_allows`, `ws.py:451`).
- **Tailscale-mode auth is tailnet membership.** `auth.is_authed()` returns True
  in `tailscale` mode; `AccessMiddleware` (CGNAT `100.64.0.0/10` + loopback) is
  the real gate. Verified the `/ws` path still gates `is_authed` → `origin_allows`
  → `controller_session`-only toon resolution before `accept()`.
- **NPC dialogue prompt-injection via player input / captured memory.** Templates
  in `clockmakers-loft.json` render `player_input` as a `SandboxedEnvironment`
  context variable (no SSTI — user text is a render var, never compiled as
  template source), role-separator wrapped, input+output banlist checked; output
  is structured effects, not trusted text. Carried, unchanged.
- **Operator-trust, not request-controlled (`bin/game`).** `world reset`'s
  `rm -rf` of `live.db*` + `images/cache/w-bunny` (now re-seeding
  `worlds/clockmakers-loft.json`); `.env` + `~/.config/daydream/secrets.env`
  sourcing; `cmd_logs` path component; FastAPI binding `0.0.0.0`. None take
  network input.
- Cookie `https_only=False`; `/status/*` + `/cache/...` session-unauthenticated
  (AccessMiddleware-gated); liveness-gated claim takeover; the deprecated
  `bootstrap_world` LLM path reading `ANTHROPIC_API_KEY` from env (design-time
  admin tool, never runtime). All carried; none aggravated by the in-scope files.

---
*Prior review (2026-07-01, paths, commit `5b181d1`): reviewed `bin/game`,
`daydream/api/ws.py`, `daydream/review.py`, `daydream/toons.py` (verification-infra
turn). Found 0 BLOCK / 0 WARN / 0 NOTE; confirmed the `/ws` Origin check closed the
prior CSRF-on-handshake NOTE, no secrets across the history, `toons.py` fully
parameterized, and `review.py` HTML-escapes every dynamic value.*

<!-- SECURITY_META: {"date":"2026-07-01","commit":"e769ad61b73b5f4d0a66898f4618b13b38856a74","scope":"paths","block":0,"warn":0,"note":1,"scanned_files":["bin/game","daydream/api/ws.py","daydream/llm/bootstrap.py","daydream/objects.py","daydream/parser.py","daydream/skills/effects.py","daydream/verbs.py","daydream/version.py","web/assets/main.js","web/index.html","worlds/clockmakers-loft.json"]} -->
