## Review — 2026-07-02 (commit: f406c3c)

**Summary:** Refresh review of the playtest-fix round
(`8b4e865..f406c3c`; 7 commits from the operator's first live playthrough):
third-person NPC dialogue voice + direct memory binding (the dlg-* zero-rows
fix), the engine open-reveal line, phrase-hinted growth direction + lowercase
composed names + the husk rename (`rename_object`, restricted), the SPA
stale-art veil + narrate glow de-dup, natural articles in refusal lines, and
FIRST-FABLE.md Part 2. Focus set: 17 files, all read at full depth. Tests:
528 short / 807 medium green after the fix loop. The third-person voice fix
was additionally verified LIVE against real vLLM (Mott: "Mott looks up from
the broom... 'Good evening...'"; no player-body narration). Chained
`/security` over the 15 changed code files: 0/0/0.

**External reviewers:** None configured.

### Findings

[WARN] tests/test_growth.py:334 — the direction-hint suite misnamed its
order-contract test and left the up-hint branch untested. **FIXED.**
  Evidence: `test_phrase_hint_picks_up_and_compass` planted "a balcony under
  the stars" and asserted the exit opens DOWN — it pins the hint-declaration
  order (down's "under" beats up's "stars"), not an up pick; no test
  exercised `_DIRECTION_HINTS`' up branch, though it is live behavior.

[NOTE] web/assets/main.js:setRoomBackground — the bg-loading veil has no
`onerror` unveil: if a room's art URL fails to load (404/evicted cache), the
plate stays transparent instead of showing anything. The pre-existing
behavior in that path (broken-image glyph / stale art) was also degraded;
acceptable for now.

### Fixes Applied

- [WARN] tests/test_growth.py — renamed the order-contract test to
  `test_phrase_hint_order_down_wins_over_up` (docstring states the
  declaration-order contract) and added `test_phrase_hint_picks_up`
  ("a balcony in the sky" → up exit, "down" reverse, "above" in the payoff).
  Re-review clean; 528 short / 807 medium green (+1 is the new test).

### Accepted Risks

Carried forward from the prior entry (none aggravated; `rename_object` is
restricted like the world-shaping kinds and engine-produced only):

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
*Prior review (2026-07-02, commit 8b4e865): full-depth refresh of the
Dreamseeds turn (35 files); 0 BLOCK / 1 WARN (malformed-growth gate, fixed in
one cycle) / 1 NOTE; security 0/0/0-new.*

<!-- REVIEW_META: {"date":"2026-07-02","commit":"f406c3c","reviewed_up_to":"f406c3c0f36d77bc68e00b8b2ab1419609493674","base":"origin/playtest-fixes-and-versioning","tier":"refresh","block":0,"warn":1,"note":1} -->
