## Security Review — 2026-07-01 (scope: paths)

**Summary:** Re-review of the three live frontend files at HEAD `94f419a`
(`web/assets/main.js`, `web/index.html`, `web/assets/style.css`) after the
playtest-fixes commit `41df573` — the only change to these files since the prior
run at `accfdb6`. The diff is almost entirely cosmetic (CSS spacing/sizing, the
new desktop app-shell layout, the removed decorative `.wordmark`/`.comptag`) and,
notably, REMOVES an `innerHTML` sink (`showSimpleHint`, which wrote an escaped
verb into `#verb-hint.innerHTML`), so the client's markup-writing surface shrank.
The one functional addition is a repeat-examine de-dup in `renderDetailInset`
(`main.js:472`) that interpolates `detail.objectId` into a `chat.querySelector`
attribute selector. Traced it: `detail.objectId` is only ever a server-generated
object id — runtime spawns are `<kindprefix>-<8 hex>` from `uuid4().hex[:8]`
(`objects.py:266`; both `spawn` callers in `skills/effects.py` use the default id,
never a caller-supplied one), and seeded ids are design-time author slugs. It is
not runtime attacker-controllable with selector-breaking characters, and
`querySelector` is a read-only DOM query that executes nothing (worst-conceivable
case is a thrown `SyntaxError` on the viewer's own screen, and that path isn't
even reachable), so it is not an injection vector. Re-verified the rest of the
XSS surface at HEAD: every `innerHTML` assignment still routes dynamic values
through `escape()` (`main.js:633`), the escape-then-wrap `linkifyEntities`
(`main.js:569`, escapes the full string before the alias regex so LLM narration
and player names cannot inject markup), a hash-selected static SVG
(`keepsakeGlyph`, name picks a shape only), `textContent`, or the DB-constrained
integer `entry.slot`. No `eval`/`new Function`/`document.write`/
`insertAdjacentHTML`/`outerHTML`; `setTimeout` takes only function callbacks;
`img.src` takes server cache paths (an `<img>` src runs no script). **No external
assets** (grep for external `url()`/`src`/`href`/`@import`/`http(s):` returns
nothing): self-hosted woff2 font, inline `data:` SVG textures, one same-origin
script tag — supply-chain surface nil, matching the local-only policy. **No
secrets** in the files or their full git history. Net, unchanged from the prior
run: **0 BLOCK / 0 WARN / 1 NOTE.**

### Findings

- **[NOTE] web/index.html:1-8 — no Content-Security-Policy (defense in depth).**
  The app shell ships no CSP (meta tag or response header) and no
  `X-Content-Type-Options: nosniff`.
  - Attack vector: none reachable today. The concrete XSS surface (LLM-generated
    narration, player-supplied toon names, keepsake item names rendered via
    `innerHTML`) is fully mitigated by `escape()` / `textContent` / the
    escape-then-wrap `linkifyEntities`, all re-verified this run. CSP is a second,
    orthogonal layer that would blunt any future escaping regression and forbid
    inline/remote script.
  - Evidence: `web/index.html:1-8` has no CSP; the sole script is same-origin
    (`web/index.html:122`) and every asset is same-origin or inline `data:`, so a
    strict policy would not break the app.
  - Remediation: add `Content-Security-Policy: default-src 'self'` plus
    `X-Content-Type-Options: nosniff`, ideally as FastAPI response headers so the
    policy also covers `/assets/*` (not just the shell). Carried unchanged from
    the prior two reviews.

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
*Prior review (2026-07-01, paths, commit `accfdb6`): reviewed the same three
frontend files after the Reading Room retheme, keepsakes backpack foldout,
responsive collapse, and self-hosted font. Traced every XSS sink and confirmed
all server/LLM/player data is escaped before render; no external assets, no
secrets. Found 0 BLOCK / 0 WARN / 1 NOTE (the same missing-CSP item).*

<!-- SECURITY_META: {"date":"2026-07-01","commit":"94f419a9ef805cf43c6ac2967c4a1dca91db3ad7","scope":"paths","block":0,"warn":0,"note":1,"scanned_files":["web/assets/main.js","web/assets/style.css","web/index.html"]} -->
