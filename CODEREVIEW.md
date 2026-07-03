## Review — 2026-07-03 (commit: a78590c)

**Summary:** Refresh review. The only change since the prior clean review
(7ca0194) is `FIRST-FABLE.md` — a first-person rewrite of the essay-companion
log. No code changed since the last review, so the umbrella code and its
adversarial security pass carry forward unchanged; this pass is a documentation
check. Verified: all internal links resolve (README.md, docs/history/GOAL.md),
every referenced commit SHA exists in git, the three markdown links are
well-formed, no secrets leak in the prose, and every pre-registered prediction,
measure, and grade is preserved in substance (the change is voice, not
content). short tier green (783).

**Review scope:** Refresh review. Focus: 1 file changed since prior review
(commit 7ca0194), `FIRST-FABLE.md` (docs). 41 already-reviewed files unchanged
since that review — no regression risk, no new security surface.

**External reviewers:** None configured.

### Findings

No issues found.

### Fixes Applied

None.

### Accepted Risks

Carried forward from the prior entry (none aggravated; no code changed this
review):

- **LLM-emitted effects take an unscoped, LLM-chosen target id.** `set_property`
  / `move_object` / `spawn_object` trust the effect's target id; `talk` + the
  deterministic verbs enforce a narrower per-verb `allowed` subset. No privilege
  escalation. Every rule-only kind (set_flag/adjust_score/kill_actor/teleport/
  fuses/daemons/win) is unreachable from any LLM-facing dispatch. v2
  `skills-authoring-and-security`. (SECURITY.md NOTE.)
- Friend-scope on slot/session endpoints (CSRF-gated; `/ws` Origin-checked);
  liveness-gated claim takeover; `/status/*` + `/cache/...` session-unauthenticated
  but AccessMiddleware-gated. Cookie `https_only=False`; `100.64.0.0/10` CGNAT
  hardcoding; tailscale `is_authed` bypass. Stored prompt-injection via captured
  memory; bootstrap `$MODEL` heredoc; `cmd_logs` path component; qpeek clone;
  `world reset` `rm -rf` operator-trust. Slot-create body unbounded; event queues
  now bounded (EVENT_QUEUE_MAXSIZE=256, drop-oldest).
- Two by-design edges from the umbrella turn, recorded in BACKLOG: `regen-ui-gate`
  (no switch yet to disable the dev repaint endpoints) and `delete-slot-grace-window`
  (delete gated only on instantaneous WS liveness). Both inside friend-scope trust.

### Carried-forward open NOTEs (pre-existing)

Growth refusal `reason` narrated without an output banlist pass; parser raw-input
not role-separated; parser per-line command-expansion has no cap; dead `text` param
in parser `_remember`; toon-view N+1 inventory query; dead `interpreter.py`;
admin.py + bootstrap.py `_write_db` non-transactional; no CSP/`X-Content-Type-Options`
on the SPA shell; `main.js:setRoomBackground` has no `onerror` unveil; the arbiter
`stats()`-vs-admission observability skew. None touched this review.

---
*Prior review (2026-07-03, commit 7ca0194): full review of the GPU headroom +
modest multiplayer + prompt audit + image-regen UI turn, 42 files / +1900/-130;
two adversarial passes (concurrency; regen+auth) plus author read found 0 BLOCK /
0 WARN / 5 NOTE (3 fixed, 2 backlogged); security covered by the adversarial pass.*

<!-- REVIEW_META: {"date":"2026-07-03","commit":"a78590c","reviewed_up_to":"a78590c8f5232c0b42aa902fed1cf757d0e644bb","base":"origin/main","tier":"refresh","block":0,"warn":0,"note":0} -->
