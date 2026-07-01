## Review — 2026-07-01 (commit: e769ad6)

**Summary:** Refresh review of the playable-quest-loop turn
(`origin/playtest-fixes-and-versioning`..`e769ad6`; 20 code/config files + 4
docs). Scope: two-object verbs `give`/`use` + a `valid_iobj_kinds` iobj gate
symmetric to the dobj gate (`daydream/verbs.py`), state-gated `open` + `read` +
state-aware `examine` over free-form `properties.state` (no migration), the
`spawn_object` `verbs` passthrough (`daydream/skills/effects.py`), the loader/
validator extension for stateful authored objects + a `fixture` prototype
(`daydream/llm/bootstrap.py`, `daydream/objects.py`), the parser two-target
fast-path (`daydream/parser.py`), the `verb_bar` iobj payload + WS command
forwarding (`daydream/api/ws.py`), the two-step click-staging UI
(`web/assets/main.js`/`style.css`/`index.html`), the new canonical world
(`worlds/clockmakers-loft.json`) + `bin/game world reset` retarget + a
`WORLD_VERSION` 1.1 bump, and the paired tests (a deterministic golden
playthrough, world-integrity invariants, loader/verb/parser/effects units).
Baseline: 452 short / 700 medium, green. Security re-scan of the 11 changed
runtime/config files: 0 BLOCK / 0 WARN / 1 NOTE.

**External reviewers:** None configured.

### Findings

No BLOCK/WARN issues. The new verb surface was traced adversarially and is
sound:

- `execute_command` validates the iobj (scope + `valid_iobj_kinds`) BEFORE any
  give/use handler runs, so `_handle_give`/`_handle_use` safely assume a valid,
  in-scope iobj of the right kind; every authored field they read
  (`wants`/`gives`/`use` rule/`state`/`*_text`) is `isinstance`-guarded with a
  soft fallback, so a malformed world degrades rather than crashing.
- `give` reparents the gift (single row move, no duplication), refuses
  not-carried + give-to-self, and dedups its `gives` reward by `give:<npc>`
  provenance; `open` returns early on `locked`/`open` so the payoff spawns
  exactly once (belt-and-suspenders with the `open:<id>` spawn dedup).
- Loader merge order is correct: an authored `properties` block is overlaid by
  top-level `seed`/`is_unique`/`text`/`verbs`, so core fields always win;
  malformed new fields fail validation loudly (tested).
- Parser two-target fast-path grounds both ids only when the verb applies to the
  dobj, else defers to the LLM; wrong-kind iobjs still ground and are refused
  gracefully by the executor gate.
- No spaghetti: 8 single-concern commits (verbs → state → loader → world →
  parser → UI → docs/version). Aligns with SPEC.md 8/8.

**NOTE (informational, not auto-fixed):** `web/index.html` ships no
Content-Security-Policy / `X-Content-Type-Options`. Pre-existing (this turn only
added the `#verb-hint` element); the concrete XSS surface (LLM narration + toon
names) is fully mitigated by `escape()` / `textContent` / escape-then-wrap
`linkifyEntities`, re-verified this pass. CSP would be belt-and-suspenders and
is a deliberate cross-cutting change, out of scope here. Recorded in SECURITY.md.

### Fixes Applied

None (no BLOCK/WARN findings).

### Accepted Risks

Carried forward from the prior entry (unchanged and unaggravated this turn). The
two-object verbs deliberately do NOT widen the LLM-target risk below: both dobj
and iobj are scope-gated, and `_handle_use` hardcodes `key="state"` with the
authored `to_state`, so a client never reaches a general arbitrary-property
write; the `spawn_object` `verbs` passthrough only attaches closed-registry verb
names (a granted `open`/`use` finds no authored rule and no-ops).

- **LLM-emitted effects take an unscoped, LLM-chosen target id.** `set_property`
  / `move_object` / `spawn_object` trust the effect's target id; room-affordance
  data skills dispatch with the full effect vocabulary, while `talk` (and the new
  deterministic verbs) enforce a narrower per-verb `allowed` subset. No privilege
  escalation. v2 `skills-authoring-and-security`. (SECURITY.md NOTE.)
- Friend-scope on slot/session endpoints (CSRF-gated by `CsrfOriginMiddleware`;
  `/ws` Origin-checked too); liveness-gated claim takeover; `/status/build`
  + `/status/drift` + `/cache/...` session-unauthenticated but AccessMiddleware-
  gated. Cookie `https_only=False`; `100.64.0.0/10` CGNAT hardcoding; tailscale
  `is_authed` bypass. Stored prompt-injection via captured memory; bootstrap
  `$MODEL` heredoc; `cmd_logs` path component; qpeek clone; `world reset` `rm -rf`
  operator-trust. Unbounded slot-create body + event queues.

### Carried-forward open NOTEs (pre-existing)

Parser raw-input not role-separated (low risk, output grounded); toon-view N+1
inventory query; dead `interpreter.py`; admin.py + bootstrap.py `_write_db`
non-transactional; no CSP/`X-Content-Type-Options` on the SPA shell (this turn's
NOTE). None aggravated this turn.

---
*Prior review (2026-07-01, commit 5b181d1): refresh review of the verification-infrastructure turn (offline `bin/game review` contact sheet, `toons.delete_slot` item-drop, forge perceptual anchor, glob-derived voice baselines, the `/ws` cross-origin handshake fix); 0 BLOCK / 0 WARN / 0 NOTE.*

<!-- REVIEW_META: {"date":"2026-07-01","commit":"e769ad6","reviewed_up_to":"e769ad61b73b5f4d0a66898f4618b13b38856a74","base":"origin/playtest-fixes-and-versioning","tier":"refresh","block":0,"warn":0,"note":1} -->
