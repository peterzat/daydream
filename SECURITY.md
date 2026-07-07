# SECURITY.md

## Security Review — 2026-07-07 (scope: paths)

**Summary:** Path-scoped audit of the v1.0 release turn at commit `3fc761a`,
42 files (~15K lines): the new journal (`journal.py`), seed propagation
(`growth.py`), portraits (`images/client.py`, `api/slots.py`, `api/ws.py`),
endings/onboarding SPA surfaces (`web/`), the repaint API (`api/rooms.py`),
the hardening trio shipped ahead of this cut (loopback-only swap, regen kill
switch, delete grace window), CI, release files, and the previously-audited
core modules' deltas. The turn's security posture holds: every new LLM
surface (journal, propagation-free growth, drift pools) validates output
against length windows and the WHIMSY banlist before any mutation, every new
SPA render sink uses `textContent` or the `escape()`-routed linkify path, all
SQL is parameterized, and the three hardening boundaries verify under trace
(the swap gate reads the real TCP peer because uvicorn runs without proxy
headers; the regen flag 404s before auth; delete honors the 120 s grace).
Git history of the credential-adjacent files (.env.example, conftest, CI,
bin/game) is clean of secret values. Net: **0 BLOCK / 1 WARN / 3 NOTE.**

### Findings

[WARN] daydream/api/slots.py:153 (with daydream/images/client.py:237,
daydream/api/ws.py:382) — `appearance_seed` is an unmoderated, unbounded,
player-supplied image-generation prompt rendered into shared-visible
portraits, with no kill switch. Slot create accepts any non-empty string
(no length cap, no `safety.first_banned` pass, unlike the growth phrase's
120-char cap + banlist); on room entry `_maybe_enqueue_toon_portraits`
renders it through SDXL and the result is displayed to every co-located
player (toon cards) and to every session (`GET /api/slots` thumbnails).
Unlike room repaint, which got the `DAYDREAM_REGEN_UI=0` kill switch so
"players cannot repaint each other's rooms" on a shared deployment, the
portrait surface cannot be switched off.
  Attack vector: an authenticated session (tailnet member in the default
  mode, or password holder in `public`) creates a toon whose appearance
  seed requests hostile or off-tone imagery; other players see the
  rendered portrait without opting in, and each such seed also spends an
  exclusive GPU render. Inside the friend-scope trust boundary, so no
  privilege gain; flagged because the just-hardened shared-deployment
  posture gates the parallel repaint surface but not this one.
  Evidence: `slots.py:153-156` validates only "non-empty string";
  `toons.create_toon_in_slot` stores it verbatim; `portrait_target`
  passes it as the prompt seed; no banlist or cap anywhere on the path.
  Remediation: at create, cap the seed length (the growth phrase uses
  120 chars) and reject on `safety.first_banned`; optionally add a
  portraits kill switch mirroring `DAYDREAM_REGEN_UI` for shared
  deployments. Existing portraits can be cleared from the image cache.

[NOTE] daydream/config.py:160-162 — the per-install session secret is
written with default permissions, then chmod'd to 0600, leaving a brief
first-boot window where the file is world-readable (umask-dependent), and
the parent `~/.config/daydream/` is created with default mode.
  Attack vector: a co-resident local user reads the cookie-signing secret
  during the sub-second window at first boot; single-user dev box, so
  practical exposure is near nil.
  Evidence: `secret_path.write_text(new_secret + "\n")` precedes
  `secret_path.chmod(0o600)`.
  Remediation: create the file with 0600 atomically
  (`os.open(..., O_CREAT | O_WRONLY | O_EXCL, 0o600)`), or
  `secret_path.touch(mode=0o600)` before writing.

[NOTE] .github/workflows/test.yml:23-26 — supply-chain hardening on the
new CI workflow: `actions/checkout@v4` and `actions/setup-python@v5` are
pinned to mutable major tags rather than commit SHAs, and the workflow
declares no `permissions:` block, so the job token gets the repo default.
  Attack vector: a compromised or retagged upstream action executes with
  the default GITHUB_TOKEN scope on push/PR builds. No secrets are used
  in the workflow, which bounds the impact.
  Remediation: add `permissions: contents: read` at the workflow root and
  pin both actions by full commit SHA.

[NOTE] daydream/parser.py:175,491 (with daydream/api/ws.py:560) — carried
forward from the 2026-07-02 review, unchanged: one WS `input` frame still
expands without a per-line cap (`_THEN_SPLIT` / `_AND_SPLIT` / ALL
expansion), so a crafted line amplifies into arbitrarily many synchronous
clock ticks and event-log rows. Authenticated-only, self-inflicted lag,
recoverable; defense in depth. Remediation unchanged: cap typed-input
length and the expanded command count per line.

Traced and cleared this run (not findings):

- **Journal is self-scoped and injection-contained.** The snapshot carries
  `journal.entries_for_snapshot(<controlled toon id>)` only (`ws.py:281`);
  entries never ride toon cards, so another player's journal is
  unreadable. The recap prompt ingests only the toon's own events
  (`fetch_for_toon`: actor or recipient match), so another player's `say`
  (room-broadcast, NULL recipient) never enters it; LLM output is
  refusal-parsed, length-windowed (60-500), banlist-checked, and rendered
  via `textContent`. The leave endpoint never blocks on the write.
- **Propagation adds zero LLM surface.** The child-seed roll is
  deterministic (`worldstate.rng`), shape-checked at load (fail-loud) and
  again at runtime (fail-closed), suppressed at the generation ceiling
  and the grown-room cap, and rides the existing allowlisted commit batch.
- **The three hardening boundaries hold.** Swap: 401 before the loopback
  check, 403 for any non-loopback peer, target confined to the data dir,
  read-only immutable probe, newer-schema refusal; `request.client.host`
  is the real TCP peer (bin/game starts uvicorn without `--proxy-headers`).
  Regen: both endpoints 404 before auth when `DAYDREAM_REGEN_UI=0`, the
  snapshot flag keeps the SPA tools unbound, prompt override is
  length-capped, never persisted, and cannot move the cache key. Delete:
  refuses while the controller was live within 120 s; kick keeps plain
  liveness. All three are pinned by tests/security/.
- **No new client-side XSS.** Every new sink (journal beat + collection,
  keepsake cards, The End page, status ribbon, clarify options, slot rows,
  repaint dialog, help leaf) uses `textContent`, `escape()`, or fixed SVG
  pools; `review.py` composes its contact sheet through `html.escape` on
  every interpolation. `image_url` values are server-derived cache paths
  assigned to `img.src`.
- **No SQL injection.** New queries (`fetch_for_toon`, world_state upserts,
  journal property writes) bind every value; the one interpolation is an
  int-cast LIMIT.
- **Path handling.** `/cache/{...}` rejects `/` and `..` per segment and
  serves only `*.png` (`.prev` unreachable); `workflow_path` rejects any
  separator; growth slugs are `[a-z0-9-]`; created toon ids are
  server-generated.
- **The accepted talk-path `set_property` risk gains new consumers, all
  contained.** An LLM-emitted `set_property` can in principle write
  `drift_pools` (drift emits pool lines without a banlist, but through
  escaped sinks), `journal` (self-scoped, escaped), or `growth` (the plant
  pipeline re-validates shape, caps rooms, and banlists output), so no
  privilege escalation; recorded under the standing accepted risk below.
- **Secrets and PII.** No keys or tokens in scope files or their history;
  conftest values are labeled test constants; the LICENSE copyright line
  carries the author's name by design (MIT convention, intentional).

### Accepted Risks

Durable register carried forward (trust model: single shared password,
tailnet membership as the outer gate, no per-user roles; loopback is the
admin boundary):

- **LLM-emitted effects take an unscoped, LLM-chosen target id and
  key/value** on the `talk` dialogue path (bound to talk's non-restricted
  allowlist: narrate/set_property/set_mood/spawn_object). Now includes the
  durable-property nuance traced this run (drift_pools/journal/growth
  writes, each contained by downstream gates). Rule/growth/clock paths do
  not share this shape. v2 `skills-authoring-and-security`.
- **Shared-world mutation: any authed session may drive verbs on any
  in-scope shared object** and repaint rooms while the regen UI is on
  (dev default). Intended single-shared-world co-op design; per-session
  ownership is v2. State-changing POSTs are CSRF-origin-gated; `/ws` is
  Origin-gated and auth-gated.
- **Parser raw player input is not role-separated** before the grounding
  LLM call; output is strictly re-grounded to a closed verb + in-scope id.
- **Tailscale-mode auth is tailnet membership** (`auth.is_authed` returns
  True unconditionally in `tailscale`; the AccessMiddleware CGNAT
  `100.64.0.0/10` + loopback check is the real gate). Cookie
  `https_only=False`; `/status/*` + `/cache/...` session-unauthenticated
  but AccessMiddleware-gated.
- **NPC dialogue / growth prompt-injection via player input**: role-
  separator wrapped, length-capped, input-banlist-checked; LLM output
  structured, validated, and output-banlist-scanned before mutation.
  (Refusal `reason` is narrated without an output-banlist pass in
  `data.py`/`growth.py`; renders through escaped sinks.)
- **Operator-trust world envelopes + `bin/game`**: `world load`/`reset`
  content (verbs/rules/fuses/daemons/growth/drift pools/dialogue),
  `reset`'s `rm -rf`, `.env`/`secrets.env` sourcing, the `0.0.0.0` bind,
  the deprecated `bootstrap_world` LLM path reading `ANTHROPIC_API_KEY`
  (design-time only). None take network input.
- Unbounded slot-create body (size; the prompt-content half is this
  review's WARN) + liveness-gated claim takeover; missing CSP /
  `X-Content-Type-Options` on the SPA shell (XSS sinks are escaped);
  event queues bounded (256, drop-oldest).

---
*Prior review (2026-07-02, paths, commit `3fdd91f`): audit of the Zork
platform turn (28 files, ~11K lines): rule/effect engine keeps a closed
condition vocabulary and allowlisted effects with restricted kinds
unreachable from any LLM-facing dispatch; parameterized SQL, validated and
escaped LLM output, tarfile traversal guards; 0 BLOCK / 0 WARN / 1 NOTE
(the WS input amplification cap, carried forward above).*

<!-- SECURITY_META: {"date":"2026-07-07","commit":"3fc761aafbb67fa5fcf2b1afa86a0b81a54abcfe","scope":"paths","scanned_files":[".env.example",".github/workflows/test.yml","LICENSE","bin/game","daydream/admin.py","daydream/api/rooms.py","daydream/api/slots.py","daydream/api/world.py","daydream/api/ws.py","daydream/config.py","daydream/drift.py","daydream/drift_samples.py","daydream/events.py","daydream/gpu/arbiter.py","daydream/growth.py","daydream/images/cache.py","daydream/images/cli.py","daydream/images/client.py","daydream/images/workflows/painterly_portrait.json","daydream/journal.py","daydream/llm/bootstrap.py","daydream/llm/client.py","daydream/llm/prompts.py","daydream/parser.py","daydream/retell.py","daydream/review.py","daydream/server.py","daydream/skills/data.py","daydream/skills/effects.py","daydream/skills/registry.py","daydream/testing/__main__.py","daydream/toons.py","daydream/verbs.py","daydream/version.py","daydream/worldstate.py","pyproject.toml","tests/conftest.py","tools/assemble_world.py","tools/zork_oracle.py","web/assets/main.js","web/assets/style.css","web/index.html","worlds/clockmakers-loft.json"],"block":0,"warn":1,"note":3} -->
