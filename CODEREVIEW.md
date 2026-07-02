## Review — 2026-07-02 (commit: 8b4e865)

**Summary:** Refresh review of the Dreamseeds turn
(`origin/playtest-fixes-and-versioning`..HEAD; 10 implementation commits plus
the prior session's 4 doc/spec commits, all after the last reviewed commit
`94f419a`, so the focus set was the full 35-file diff — reviewed at full
depth). Scope: the two world-shaping effects (`spawn_room`/`link_exit` +
the `DEFAULT_KINDS` opt-in gate), the growth pipeline (`daydream/growth.py`),
the `plant` verb + WS refresh kinds, loader `contains`/`growth` validation,
the authored dreamseed in `worlds/clockmakers-loft.json`, `WORLD_VERSION`
1.2, the SPA vision prompt, the tier_long growth-compose probe + ratified
rung-(a) goldens, and the doc roll-forward. Test baseline: 511 short / 787
medium / 807 long (both engines) green at review HEAD; 512 / 788 green after
the fix loop. A live end-to-end playthrough against the running server +
real engines verified the true path (quest → seed → plant → The Firefly
Observatory → watercolor render). Chained `/security` pass over the 27
changed code files: 0 BLOCK / 0 WARN / 0 new NOTE.

**External reviewers:** None configured.

### Findings

[WARN] daydream/growth.py:279 — a malformed runtime growth block could raise
through `_user_prompt` and drop the planter's WS connection. **FIXED.**
  Evidence: the has-growth gate checked only `isinstance(growth, dict) and
  growth.get("exemplars")`, while `_user_prompt` indexed `ex["title"]` /
  `ex["seed"]` / `ex["description"]` and joined `theme`/`motifs` as string
  lists. Loader-authored seeds are validated, but `talk`'s allowlist includes
  `spawn_object`, whose new `properties` passthrough writes any LLM-supplied
  dict — including `{"verbs": ["plant"], "growth": {"exemplars": [{}]}}`.
  Planting such an object raised KeyError inside a try that catches only
  `LLMUnavailable`, propagating through `execute_command` →
  `ws._receive_loop` and closing the socket — violating the pipeline's
  "every failure path narrates in character and mutates nothing" contract.

[NOTE] daydream/growth.py:358 — the LLM refusal `reason` is narrated to the
player without an output banlist pass. Consistent with the existing
data-skill pipeline (`data.py` narrates `refusal.reason` identically), so
not new exposure; noted for a future shared tightening.

### Fixes Applied

- [WARN] daydream/growth.py — `_growth_shape_ok` validates everything
  `_user_prompt` touches (exemplars: non-empty list of dicts with non-empty
  str title/seed/description; theme/motifs: lists of str when present;
  palette/question: str when present) and now gates `execute_plant`,
  narrating the existing in-character no-growth line on failure. Paired
  regression test (`test_malformed_growth_refuses_in_character`). Re-review
  clean; tiers re-run green (512 short / 788 medium; the +1 is the new test).

### Accepted Risks

Carried forward from the prior entry (none aggravated; the growth path is
strictly tighter than the accepted `talk` baseline — engine-picked ids,
slugs, and directions; the LLM supplies text only):

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
non-transactional; no CSP/`X-Content-Type-Options` on the SPA shell; detail-inset
de-dup keys on object id first; keepsake captions are client-side flourish.
None aggravated this turn.

---
*Prior review (2026-07-01, commit 94f419a): refresh review of the Reading Room
playtest-fixes + README turn; 0 BLOCK / 0 WARN / 4 NOTE, no fixes needed.*

<!-- REVIEW_META: {"date":"2026-07-02","commit":"8b4e865","reviewed_up_to":"8b4e865cf5e827eb058ae412a8bfb2160dcaabeb","base":"origin/playtest-fixes-and-versioning","tier":"refresh","block":0,"warn":1,"note":1} -->
