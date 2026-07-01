## Review — 2026-07-01 (commit: 94f419a)

**Summary:** Refresh review of the Reading Room playtest-fixes + README turn
(`origin/playtest-fixes-and-versioning`..`94f419a`; 1 code commit + 2 docs
commits). Focus set: `web/assets/main.js`, `web/assets/style.css`,
`web/index.html`, `tests/test_frontend.py` (all read in full), plus `README.md`
(docs) and the regenerated `docs/pretty/reading-room-ui.png`. Client-only: no
`daydream/`/`worlds/`/DB change, no `WORLD_VERSION` bump. Baseline: 454 short /
707 medium, green. Security re-scan of the 3 changed runtime files: 0/0/1.

**External reviewers:** None configured.

### Findings

No BLOCK/WARN. The playtest fixes were traced adversarially:

- **Removed a markup sink.** `showSimpleHint` (an `innerHTML` write) is gone; the
  staged-verb feedback is now purely the chip pip + target dimming. The security
  surface shrank, confirmed by the chained `/security` pass.
- **Repeat-examine de-dup is sound in the common case.** `renderDetailInset`
  tags each inset with `data-object-id` + `data-text`; a repeat examine/read of
  the same object with the same result resurfaces the existing card (moved to the
  end) and glows it (`glowElement` reflow trick) instead of duplicating. The
  `chat.querySelector` selector interpolates a server-generated object id (a safe
  `<prefix>-<hex>` slug, never client-controlled), so it is not an injection
  vector; `dataset.text` uses the DOM API, and the inset body still routes
  through the vetted escape-then-wrap `linkifyEntities`.
- **Layout changes are presentation-only.** The desktop app-shell
  (`@media (min-width: 641px)`, `body { overflow:hidden }`, a viewport-height
  flex leaf with the chat/marginalia scrolling inside) keeps the ribbon + compass
  in view; fixed overlays (dream/slots/backpack) are `position:fixed` and
  unaffected. Rendered-verified at 1366x768 (nav visible) and 390px (mobile
  document scroll intact).
- **No spaghetti / spec-aligned:** one coherent UI-polish commit from a single
  playtest round, plus two docs commits. SPEC.md is closed 8/8; this is post-spec
  polish + documentation.

**NOTEs (informational, not auto-fixed):**

- **`web/assets/main.js:472` de-dup keys on object id first.**
  `renderDetailInset` finds the prior inset with `querySelector('.detail-inset
  [data-object-id="X"]')` (first match) and only glows-instead-of-appends when
  its stored text also matches. If an object's examine text *changes* between
  looks (e.g. a stateful object examined in a new state), a later re-examine of
  the new-state text can match the older inset by id but not by text and append a
  duplicate. Cosmetic, narrow (static examine text is the norm); the common
  re-examine case de-dups correctly.
- **`web/index.html` ships no CSP / `X-Content-Type-Options`.** Carried; no
  reachable attack (XSS sinks are fully escaped), a `default-src 'self'` CSP would
  be belt-and-suspenders. Recorded in SECURITY.md.
- **Detail-inset timing.** A drift `narrate` within 8 s of a targeted
  examine/read still renders as a detail inset (cosmetic; bounded by the window +
  snapshot reset). Carried.
- **Keepsake captions/tags are generic client-side flourish** (no server item
  lore yet); the real content is the item name. Backlog `snapshot-item-lore`.

### Fixes Applied

None (no BLOCK/WARN findings).

### Accepted Risks

Carried forward, none aggravated by this client-only UI/docs turn:

- **LLM-emitted effects take an unscoped, LLM-chosen target id.** `set_property`
  / `move_object` / `spawn_object` trust the effect's target id; `talk` + the
  deterministic verbs enforce a narrower per-verb `allowed` subset. No privilege
  escalation. v2 `skills-authoring-and-security`. (SECURITY.md NOTE.)
- Friend-scope on slot/session endpoints (CSRF-gated; `/ws` Origin-checked);
  liveness-gated claim takeover; `/status/*` + `/cache/...` session-unauthenticated
  but AccessMiddleware-gated. Cookie `https_only=False`; `100.64.0.0/10` CGNAT
  hardcoding; tailscale `is_authed` bypass. Stored prompt-injection via captured
  memory; bootstrap `$MODEL` heredoc; `cmd_logs` path component; qpeek clone;
  `world reset` `rm -rf` operator-trust. Unbounded slot-create body + event queues.

### Carried-forward open NOTEs (pre-existing)

Parser raw-input not role-separated (low risk, output grounded); toon-view N+1
inventory query; dead `interpreter.py`; admin.py + bootstrap.py `_write_db`
non-transactional; no CSP/`X-Content-Type-Options` on the SPA shell. None
aggravated this turn.

---
*Prior review (2026-07-01, commit accfdb6): full-depth review of the Reading Room UI retheme (storybook SPA, keepsakes foldout, responsive collapse, DESIGN.md + token drift guard, self-hosted font); 0 BLOCK / 0 WARN / 3 NOTE.*

<!-- REVIEW_META: {"date":"2026-07-01","commit":"94f419a","reviewed_up_to":"94f419a9ef805cf43c6ac2967c4a1dca91db3ad7","base":"origin/playtest-fixes-and-versioning","tier":"refresh","block":0,"warn":0,"note":4} -->
