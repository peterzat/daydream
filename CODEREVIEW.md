## Review — 2026-06-30 (commit: f3da4f5)

**Summary:** Full review of the playtest-polish turn (SPEC 2026-06-30, 14/14):
the diff `ebc43bd`..`f3da4f5` (29 files, +1140/-297) covering picker-first entry
(removing the `t-wren` phantom-toon fallback), labelled scene + `inventory` verb
+ backpack control + client-side verb-applicability gating, no-id say-attribution,
navigate-by-place + look-at parser fast-paths, second-person narration + clean
verb lines (single terminal stop; named-absent "you don't see the X here"), the
calm sleeping/shifts connection overlay with capped-backoff reconnect, witnessed
drift (occupancy suppression removed, busy cadence 1800 → 240 s), tightened NPC
voices + forge-as-forge seed, and an end-to-end gameplay-scenario test. Baseline
stable: 396 short / 622 medium, both green. Security chain clean (0/0/0, a net
improvement — the legacy `t-wren` shared-toon fallback is retired). 0 BLOCK / 0 WARN.

**External reviewers:** None configured.

### Findings

- [NOTE] daydream/api/slots.py + daydream/api/ws.py — the `left` session flag is
  still set on leave (and cleared on create/claim) but ws.py no longer reads it
  after picker-first: `_resolve_controlled_toon_id` returning None (toon presence)
  now gates the picker, subsuming the old `left`-flag branch. Vestigial but
  harmless; a future cleanup could drop the flag writes. No behavior impact.
- [NOTE] daydream/parser.py (the "verb \<name>" fast-path) — an unresolved
  "verb \<name>" now resolves to a deterministic "you don't see the \<name> here"
  (via `Parse.dobj_name`) instead of an LLM grounding attempt, slightly reducing
  fuzzy-matching for descriptive phrases after a known verb (e.g. "take the glowing
  thing"). This is the spec-mandated C9 named-absent behavior; the LLM still grounds
  non-verb-leading phrasings ("grab that shiny thing"). Deliberate trade-off.

### Fixes Applied

None. The two findings are informational NOTEs (not auto-fixed); no BLOCK/WARN.

### Accepted Risks

Carried forward unchanged from the prior entry:

- **LLM-emitted effects take an unscoped, LLM-chosen target id.** `set_property`
  / `move_object` / `spawn_object` trust the effect's target id; a room-affordance
  data skill (`stoke` / `tend`) dispatches with the FULL effect vocabulary
  (advisory `effects_schema`), while the `talk` verb enforces its narrower per-verb
  `allowed` subset. No privilege escalation (`set_property` writes
  `properties_json` only; auth columns unreachable). v2 `skills-authoring-and-
  security`. (SECURITY.md NOTE.)
- Friend-scope on slot/session endpoints (CSRF gated by `CsrfOriginMiddleware`).
  Cookie `https_only=False`; `100.64.0.0/10` CGNAT hardcoding; tailscale `is_authed`
  bypass; `/cache/...` + `/status/drift` unauthenticated. Stored prompt-injection
  via captured memory; bootstrap `$MODEL` heredoc; `cmd_logs` path component;
  qpeek clone. Unbounded slot-create body + event-subscriber queues.

### Carried-forward open NOTEs (pre-existing)

The prior register persists (parser raw-input not role-separated — low risk,
output strictly grounded; toon-view N+1 inventory query; dead `interpreter.py`;
admin.py + bootstrap.py `_write_db` non-transactional). None aggravated this turn.
The picker-first change RETIRED one prior accepted risk: the legacy `t-wren`
shared-toon fallback is gone (an unresolved session now controls no toon).

---
*Prior review (2026-06-30, commit 14d624d): refresh review of the live-world-reset closeout (objects+verbs 19/19); 0 BLOCK / 0 WARN / 1 NOTE.*

<!-- REVIEW_META: {"date":"2026-06-30","commit":"f3da4f5","reviewed_up_to":"f3da4f54dcd8999cdb2bf658de4314bf682e1e86","base":"origin/main","tier":"full","block":0,"warn":0,"note":2} -->
