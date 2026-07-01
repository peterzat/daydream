## Review — 2026-07-01 (commit: accfdb6)

**Summary:** Full-depth review of the Reading Room UI retheme
(`origin/playtest-fixes-and-versioning`..`accfdb6`; 6 UI/docs commits plus 2
pre-session mockup-exploration commits). Scope: `DESIGN.md` (new durable UI
design bible), the reconciled CSS design tokens + a self-hosted Caveat woff2 +
its tier_short drift guard (`tests/drift/test_design_tokens.py`), the near-total
restructure of `web/index.html` + `web/assets/style.css` + targeted
`web/assets/main.js` into the storybook page (chapter plate, drop-cap prose,
marginalia, ink-tab verb ribbon, compass, an examine/read detail inset), the
keepsakes backpack foldout over live inventory, a phone-width single-column
collapse, README showcase images, and the paired frontend source-scan tests. All
changed code files read in full. Client-only: no `daydream/`/`worlds/`/DB change,
no `WORLD_VERSION` bump. Baseline: 454 short / 704 medium, green. Security
re-scan of the 3 changed runtime files: 0 BLOCK / 0 WARN / 1 NOTE.

**External reviewers:** None configured.

### Findings

No BLOCK/WARN issues. The retheme was traced adversarially and is sound:

- **XSS surface unchanged and safe.** Every new `innerHTML` sink routes dynamic
  data through a mitigation: `showSimpleHint` escapes the (closed-set) verb;
  `renderDetailInset` reuses the vetted escape-then-wrap `linkifyEntities` on the
  narrate text (the untrusted-LLM path); `keepsakeGlyph` returns a static
  hash-selected SVG with the item name used only to pick an index, never
  interpolated; item/toon names render via `textContent`. Confirmed by the
  chained `/security` pass.
- **No external runtime assets** (C7): the display font is a bundled `@font-face`
  woff2, textures are inline `data:` SVG, the only script is same-origin. Grep
  for `googleapis`/CDN/external `url()` is clean. The `Caveat-OFL.txt` license and
  a code comment are the only "external" strings.
- **No interaction regressed.** The scene-object gating selectors (`#scene .obj`)
  still resolve because the marginalia `aside` carries `id="scene"`; verb staging,
  two-step give/use, entity-link clicks, WS reconnect/`?since`, slots picker,
  overlays, `painting…`→`room_image_ready` swap, and redeploy-reload are untouched.
  The backpack rewiring drops `sendCommand("inventory")` for a client-side foldout;
  the `inventory` verb stays reachable via text input. Verified by 43 green
  frontend source-scan tests + a rendered visual review (desktop + 390px).
- **No ids leak.** `nameForObject` returns a chip's display text or an entity
  alias (never an id); the compass renders exit directions only (exit values are
  room ids, deliberately not shown).
- **No spaghetti:** single-concern commits (foundation → structure → backpack →
  responsive → docs → spec). Aligns with SPEC.md 8/8.

**NOTEs (informational, not auto-fixed):**

- **`web/index.html` ships no Content-Security-Policy / `X-Content-Type-Options`.**
  Carried unchanged; no reachable attack (the XSS surface is fully escaped), a
  `default-src 'self'` CSP (all assets same-origin) would be belt-and-suspenders.
  A deliberate cross-cutting change, out of scope here. Recorded in SECURITY.md.
- **`web/assets/main.js` detail-inset timing.** A drift `narrate` arriving within
  8 s of a targeted examine/read renders as a detail inset, since `pendingDetail`
  matches the next narrate regardless of source. Cosmetic only (a drift line
  shows as a ledger card); bounded by the 8 s window and reset on every snapshot.
- **Keepsake specimen captions/tags are generic client-side flourish.**
  `_object_card` carries no description/provenance, so the cards show the real
  item name plus a name-hashed caption/tag; they never fabricate item-specific
  facts. A server snapshot field would let them carry real lore (proposed backlog
  `snapshot-item-lore`).

### Fixes Applied

None (no BLOCK/WARN findings).

### Accepted Risks

Carried forward from the prior entry, none aggravated by this client-only UI turn
(it touches no server/LLM/auth/data surface):

- **LLM-emitted effects take an unscoped, LLM-chosen target id.** `set_property`
  / `move_object` / `spawn_object` trust the effect's target id; room-affordance
  data skills dispatch with the full effect vocabulary, while `talk` + the
  deterministic verbs enforce a narrower per-verb `allowed` subset. No privilege
  escalation. v2 `skills-authoring-and-security`. (SECURITY.md NOTE.)
- Friend-scope on slot/session endpoints (CSRF-gated by `CsrfOriginMiddleware`;
  `/ws` Origin-checked); liveness-gated claim takeover; `/status/*` + `/cache/...`
  session-unauthenticated but AccessMiddleware-gated. Cookie `https_only=False`;
  `100.64.0.0/10` CGNAT hardcoding; tailscale `is_authed` bypass. Stored
  prompt-injection via captured memory; bootstrap `$MODEL` heredoc; `cmd_logs`
  path component; qpeek clone; `world reset` `rm -rf` operator-trust. Unbounded
  slot-create body + event queues.

### Carried-forward open NOTEs (pre-existing)

Parser raw-input not role-separated (low risk, output grounded); toon-view N+1
inventory query; dead `interpreter.py`; admin.py + bootstrap.py `_write_db`
non-transactional; no CSP/`X-Content-Type-Options` on the SPA shell. None
aggravated this turn.

---
*Prior review (2026-07-01, commit e769ad6): refresh review of the playable-quest-loop turn (two-object give/use verbs + iobj gate, state-gated open/read, stateful world loader, The Clockmaker's Loft, WORLD_VERSION 1.1); 0 BLOCK / 0 WARN / 1 NOTE (CSP).*

<!-- REVIEW_META: {"date":"2026-07-01","commit":"accfdb6","reviewed_up_to":"accfdb6488e377ff6cdc5368823cff6f26f6faf2","base":"origin/playtest-fixes-and-versioning","tier":"full","block":0,"warn":0,"note":3} -->
