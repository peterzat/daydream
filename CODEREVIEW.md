## Review — 2026-07-02 (commit: 60001de)

**Summary:** Refresh review for the single-branch consolidation push: `main`
fast-forwarded to `60001de`, which is byte-identical to
`origin/playtest-fixes-and-versioning` (already on the remote), so this push
publishes no new content, it only moves the `main` ref. The 81-commit /
94-file diff vs `origin/main` is exactly the content reviewed across the
recorded chain (Reading Room UI at b971c08, playtest fixes + README at
8c755b0, Dreamseeds at e69bdcf, playtest-fix round at d8069f1). Focus set
since the last recorded review (`reviewed_up_to` f406c3c): two commits,
d8069f1 (review-record files, excluded from scope) and 60001de
(FIRST-FABLE.md Part 3, docs-only; light checks: link targets exist
(docs/history/GOAL.md, README.md), no secrets in prose, factually consistent
with the git history it describes). Tests re-run at this HEAD: 528 short /
807 medium green (matches the prior baseline). Chained `/security` over the
one code file changed since the last scan (tests/test_growth.py): 0/0/0,
SECURITY_META now at 60001de.

**External reviewers:** None configured.

### Findings

[NOTE] web/assets/main.js:setRoomBackground — carried forward (still
present): the bg-loading veil has no `onerror` unveil; if a room's art URL
fails to load (404/evicted cache), the plate stays transparent instead of
showing anything.

### Fixes Applied

None.

### Accepted Risks

Carried forward from the prior entry (none aggravated):

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

Growth refusal `reason` narrated without an output banlist pass (consistent
with the data-skill pipeline); parser raw-input not role-separated; toon-view
N+1 inventory query; dead `interpreter.py`; admin.py + bootstrap.py `_write_db`
non-transactional; no CSP/`X-Content-Type-Options` on the SPA shell;
detail-inset de-dup keys on object id first; keepsake captions are client-side
flourish. None aggravated this turn.

---
*Prior review (2026-07-02, commit f406c3c): refresh of the playtest-fix round
(7 commits, 17-file focus set): third-person NPC voice + memory binding,
engine open-reveal line, phrase-hinted growth direction, SPA veil/glow
polish; 0 BLOCK / 1 WARN (misnamed direction-hint test + untested up-hint
branch, fixed in one cycle) / 1 NOTE; security over 15 changed files 0/0/0.*

<!-- REVIEW_META: {"date":"2026-07-02","commit":"60001de","reviewed_up_to":"60001de72f8092c555c92d7d3eb2eee6949af335","base":"origin/main","tier":"refresh","block":0,"warn":0,"note":1} -->
