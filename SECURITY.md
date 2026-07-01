## Security Review — 2026-07-01 (scope: paths)

**Summary:** Path-scoped review of the three live frontend files at HEAD
`accfdb6` (`web/assets/main.js`, `web/index.html`, `web/assets/style.css`) after
the "Reading Room" retheme, the keepsakes backpack foldout, the responsive
single-column collapse, and the self-hosted display font — substantial new
client code layered on since these files were last reviewed (at `e769ad6`, which
covered only main.js + index.html at the pre-retheme two-step-staging state, and
did not scan style.css). Traced every XSS sink and confirmed the client treats
all server/LLM/player data as untrusted: every `innerHTML` assignment routes
dynamic values through `escape()` (`main.js:617`), the escape-then-wrap
`linkifyEntities` (`main.js:553` — escapes the full string before the
alias-matching regex, so LLM-generated narration and player toon names cannot
inject markup), a static hash-selected SVG (`keepsakeGlyph`, name used only to
pick a shape — `main.js:711`), or a server-side integer (`entry.slot`, a DB
column constrained to `HUMAN_SLOT_RANGE` 1-5 by `slots.py:_validate_slot` and the
`slot: int` path type, so the un-`escape()`d interpolations at `main.js:769-802`
are numeric, not an injection vector). No `eval` / `new Function` /
`document.write` / `insertAdjacentHTML` / `outerHTML`; `setTimeout` takes only
function callbacks; `img.src` is fed server-controlled cache paths (an `<img>`
src runs no script). **No external assets** (grep for external `url()`/`src`/
`href`/`@import`/`http(s):` in the CSS+HTML returns nothing): the font is
self-hosted (`@font-face` → `/assets/fonts/…woff2`), all textures are inline
`data:` SVG, and the only script tag is same-origin `/assets/main.js` — no CDN /
third-party runtime dependency (supply-chain surface is nil, and it matches the
local-only policy). **No secrets** in the files or their git history (UI-only
commits). Net, unchanged from the prior run: **0 BLOCK / 0 WARN / 1 NOTE.**

### Findings

- **[NOTE] web/index.html:1-8 — no Content-Security-Policy (defense in depth).**
  The app shell ships no CSP (meta tag or response header) and no
  `X-Content-Type-Options: nosniff`.
  - Attack vector: none reachable today. The concrete XSS surface (LLM-generated
    narration, player-supplied toon names, and keepsake item names rendered via
    `innerHTML`) is fully mitigated by `escape()` / `textContent` / the
    escape-then-wrap `linkifyEntities`, all re-verified this run. CSP is a second,
    orthogonal layer that would blunt any future escaping regression and forbid
    inline/remote script.
  - Evidence: `web/index.html:1-8` has no CSP; the sole script is same-origin
    (`web/index.html:125`) and every asset is same-origin or inline `data:`, so a
    strict policy would not break the app.
  - Remediation: add `Content-Security-Policy: default-src 'self'` plus
    `X-Content-Type-Options: nosniff`, ideally as FastAPI response headers so the
    policy also covers `/assets/*` (not just the shell). Carried unchanged from
    the prior review.

### Accepted Risks

Durable register carried forward from prior reviews; not re-flagged as findings.
This run is frontend-scoped, so the backend items below were not re-verified
against source this pass (their controls live outside the three reviewed files);
they remain accepted.

- **LLM-emitted effects take an unscoped, LLM-chosen target id.** `set_property` /
  `move_object` / `spawn_object` trust the effect's target id; the `talk` dialogue
  path is the one LLM producer, bound to its per-verb `allowed` subset. v2
  `skills-authoring-and-security`.
- **Shared-world mutation: any authed tailnet session may drive verbs on any
  in-scope shared object.** Intended single-shared-world design; per-session
  ownership is v2. State-changing POSTs are CSRF-gated; `/ws` is Origin-gated.
- **Tailscale-mode auth is tailnet membership.** `auth.is_authed()` returns True
  in `tailscale` mode; `AccessMiddleware` (CGNAT `100.64.0.0/10` + loopback) is
  the real network gate.
- **NPC dialogue prompt-injection via player input / captured memory.** Player
  text is a `SandboxedEnvironment` render var (no SSTI), role-separator wrapped,
  banlist-checked; output is structured effects, not trusted text.
- **Operator-trust, not request-controlled (`bin/game`).** `world reset`'s
  `rm -rf`, `.env`/`secrets.env` sourcing, `0.0.0.0` bind. None take network input.
- Cookie `https_only=False`; `/status/*` + `/cache/...` session-unauthenticated
  (AccessMiddleware-gated); liveness-gated claim takeover; the deprecated
  `bootstrap_world` LLM path reading `ANTHROPIC_API_KEY` (design-time admin tool,
  never runtime). All carried; none touched by the in-scope frontend files.

---
*Prior review (2026-07-01, paths, commit `e769ad6`): reviewed the playable-quest-loop
turn (two-object verbs, object state, the loader, versioning, main.js + index.html
two-step staging, `worlds/clockmakers-loft.json`). Found 0 BLOCK / 0 WARN / 1 NOTE
(the same missing-CSP item); confirmed no secrets, full SQL parameterization, and
that the client escapes every dynamic value.*

<!-- SECURITY_META: {"date":"2026-07-01","commit":"accfdb6488e377ff6cdc5368823cff6f26f6faf2","scope":"paths","block":0,"warn":0,"note":1,"scanned_files":["web/assets/main.js","web/assets/style.css","web/index.html"]} -->
