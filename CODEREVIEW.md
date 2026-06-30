## Review — 2026-06-30 (commit: 777a289)

**Summary:** Full-depth review of the **objects + local LLMs** turn against
`origin/main` (12 commits, 41 files +3279/-558): the MOO-style object/verb core
(migration 011 unifying `rooms`/`toons`/`items` into one `objects` table +
`daydream/objects.py` access layer; thin views over it), the closed verb
registry + `execute_command` bus (`daydream/verbs.py`), the grounded local-LLM
parser (`daydream/parser.py`), the allowlisted world-mutation effect API
(`daydream/skills/effects.py`), the clickable-object UI (`web/`), keyless
object-schema authoring (`daydream/llm/bootstrap.py` + `worlds/bunny.json`), and
the docs roll-forward. Tests green: `bin/game test medium` 591 passed / 15
deselected (377 short). Security chain run on the 14-file code surface:
**0 BLOCK / 0 WARN / 1 NOTE** (SECURITY.md, commit `777a289`). **0 BLOCK /
0 WARN** from this review; 3 NOTEs below.

**External reviewers:** None configured. (`review-external.sh` on PATH; no
provider keys in `~/.config/claude-reviewers/.env`.)

### Findings

[NOTE] daydream/parser.py:_user_prompt (~232) — player free text is embedded raw
(`Player input: {text}`) without the `safety.wrap_player_input` role-separator
tags or the input banlist the data-skill pipeline applies before its LLM call.
  Evidence: `data.execute` wraps + banlist-checks player args; `parser.parse`
  sends raw text and runs no banlist at parse time.
  Why only NOTE: the parser's output is strictly validated — verb must be in the
  closed vocabulary and dobj/iobj must resolve to an enumerated in-scope id
  (`parser.parse` re-checks both, and `verbs.execute_command` re-validates
  independently). Prompt injection therefore cannot yield an out-of-vocab or
  out-of-scope command; at worst it produces a command the player could already
  issue by clicking. Parity with the old interpreter (which also did not
  role-separate routing input; the banlist lived in skill *execution*, which the
  `talk` path still enforces on its args). Defense-in-depth only: consider
  wrapping for symmetry.
  Suggested fix (optional): pass `safety.wrap_player_input(text)` into the
  parser's user prompt.

[NOTE] daydream/toons.py:_query / _toon — N+1 inventory query. Each toon row
materialized by `_query` calls `objects.content_ids(obj.id, "thing")` to fill
`Toon.inventory`, so `get_toons_in_room` / `get_human_slots` / `get_npcs` issue
one extra indexed query per toon.
  Evidence: `_toon` always fills inventory; the only consumer that reads
  `.inventory` is the slot-create assertion (`tests/test_slots.py:212`).
  Why only NOTE: negligible at single-user scale (≤5 toons), indexed on
  `(world_id, location_id)`; not a correctness issue. Could lazily fill
  inventory only in `get_toon`, or batch with a single `GROUP BY location_id`.

[NOTE] Dead code: the grounded parser replaced `daydream/skills/interpreter.py`
on the live WS path, but `interpreter.py`, `daydream/llm/prompts.py`
(`INTERPRETER_SYSTEM` / `interpreter_user`), and `tests/test_skill_interpret.py`
remain — now unused by production (verified: no production module imports
`skills.interpreter`).
  Why only NOTE: harmless (still valid + green); a cleanup candidate, not a
  defect. Left in deliberately to avoid churn at the tail of a large turn.

### Fixes Applied

None. 0 BLOCK / 0 WARN; the 3 NOTEs are informational and not auto-fixed.

### Accepted Risks

Carried forward from the prior entry (unchanged), with this turn's extension:

- **LLM-emitted effects take an unscoped, LLM-chosen target id (EXTENDED this
  turn).** `set_property` / `move_object` / `spawn_object` trust the effect's
  target id, and a room-affordance data skill (`stoke` / `tend`) dispatches with
  the FULL effect vocabulary regardless of its declared `effects_schema`
  (advisory in v1). Enforced boundary is the kind-allowlist; the `talk` verb DOES
  enforce its narrower per-verb `allowed` subset. No privilege escalation:
  `set_property` writes `properties_json` only, so the promoted auth columns
  (`controller_session` / `is_human_controlled` / `kicked_at` / `slot`) are
  unreachable. Blast radius is friend-scope game state; output renders escaped.
  Target-authorization + per-effect jsonschema are v2 (`skills-authoring-and-
  security`). This extends the prior accepted `set_mood`-unscoped-`toon_id` risk.
  (SECURITY.md NOTE, `777a289`.)
- **Friend-scope on the slot/session endpoints.** Any authed session may
  create/claim/kick/delete/leave any slot; per-session ownership is v2. CSRF on
  bodyless POSTs is gated by `daydream/api/csrf.py` `CsrfOriginMiddleware`.
- Cookie `https_only=False`; LAN/Tailscale only. `100.64.0.0/10` CGNAT hardcoding.
  `AccessMiddleware` reads `scope["client"][0]` directly. Tailscale-mode
  `is_authed` bypass + `_ensure_session_id` fresh-UUID stamping. `/cache/...` +
  `/status/drift` intentionally unauthenticated.
- Stored prompt-injection via captured memory text; `bin/{vllm,memory}-bootstrap`
  `$MODEL` heredoc; `bin/game cmd_logs` path component; `bin/qpeek-bootstrap`
  clone — operator-trust / v2-`skills-authoring-and-security` class.
- Unbounded request body on slot create; unbounded event-subscriber queues.

### Carried-forward open NOTEs (pre-existing, not aggravated this turn)

The prior register persists (admin.py cascade + bootstrap.py `_write_db`
non-transactional; bootstrap skill/dialogue `room_slug` / name uniqueness not
cross-checked — a duplicate toon name would collide on the `skill-dlg-<slug>`
PK and fail the load loudly; swap-to-the-live-DB-itself FileNotFoundError-then-
safe-restore; various stale comments / dead CSS). None are in code this turn
changed in a way that resolves or worsens them.

---
*Prior review (2026-06-30, commit 195e73b): full review of the session-and-
presence + world-hot-swap stack; 2 WARN found and both fixed (CSRF on bodyless
POSTs → CsrfOriginMiddleware; drift-handle staleness after swap), 1 NOTE left
benign. 0 BLOCK / 0 WARN outstanding.*

<!-- REVIEW_META: {"date":"2026-06-30","commit":"777a289","reviewed_up_to":"777a289e6616abb9142ad08f075f6fe522e7468e","base":"origin/main","tier":"full","block":0,"warn":0,"note":3} -->
