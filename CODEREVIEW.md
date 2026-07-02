## Review — 2026-07-02 (commit: 3fdd91f)

**Summary:** Refresh review of the entire Zork platform turn (v0.6.0): 79
files, ~26K insertions since the prior clean review at 60001de — the largest
review scope this project has had. Focus set = full set (everything landed
this turn). Engine code read directly at full depth: the new modules
(worldstate, rules, worldverbs, clock, combat, lighting, retell, pronouns),
the new effect kinds (destroy_object, teleport_actor, kill_actor + the
authored death policy, fuses/daemons, adjust_score once-keys, win), the wide
parser (ALL/AND/EXCEPT, IT, AGAIN, THEN, GWIM, clarify), verbs.py's dispatch
integration + put handler, objects.py scope recursion, the events recipient
column + WS private routing/status, migrations 013–015, toons.live_world_id,
the three tools, and main.js's new render paths (textContent/createElement
only — no injection sinks). World data (~13K lines of envelope/walkthrough
JSON) is reviewed mechanically by its own fail-loud loader validation, the
static analyzer (110 rooms, ledger sums to exactly 350, byte-match
re-assembly), and the zero-LLM walkthrough replay. Tests at this HEAD: short
763 / medium 1072 / long 1105, all green, zero skips beyond the by-design
dfrotz-absent oracle skip. The turn's live rehearsal already surfaced and
fixed its own two real bugs in-turn (hardcoded picker world id; player-toon
determinism gap), both with regression tests. Chained `/security` over the 28
changed code files: 0 BLOCK / 0 WARN / 1 NOTE; SECURITY_META now at 3fdd91f.

**External reviewers:** None configured.

### Findings

[NOTE] daydream/parser.py:142 — one authenticated WS input line can expand to
arbitrarily many commands (THEN-chaining × AND-lists × ALL) with no per-line
cap; each expanded command ticks the clock and appends events. Self-inflicted
recoverable lag inside an authenticated boundary (same sink family as the
accepted unbounded-event-queue risk); no privilege gain. (From the chained
/security scan.)
  Suggested fix: cap input length and expanded-command count per line.

[NOTE] daydream/parser.py:191 — `_remember(actor_id, commands, text)` takes a
`text` parameter that is never used; all three call sites pass `text=None`.
Dead parameter left from an earlier design.
  Suggested fix: drop the parameter.

[NOTE] web/assets/main.js:setRoomBackground — carried forward (untouched this
turn): the bg-loading veil has no `onerror` unveil; a room art URL that fails
to load leaves the plate transparent.

### Fixes Applied

None. (The turn's in-flight fixes — the grue-fatal lampless descent, the
thief fight's turn alignment, the picker world id, the driver pacing — were
found and fixed by the turn's own verification loop before this review, each
argued in its commit.)

### Accepted Risks

Carried forward from the prior entry (none aggravated):

- **LLM-emitted effects take an unscoped, LLM-chosen target id.** `set_property`
  / `move_object` / `spawn_object` trust the effect's target id; `talk` + the
  deterministic verbs enforce a narrower per-verb `allowed` subset. No privilege
  escalation. The Zork turn narrows this further: every rule-only kind
  (set_flag/adjust_score/kill_actor/teleport/fuses/daemons/win) is unreachable
  from any LLM-facing dispatch. v2 `skills-authoring-and-security`. (SECURITY.md NOTE.)
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
*Prior review (2026-07-02, commit 60001de): refresh for the single-branch
consolidation push (docs-only tip; 81-commit diff already content-reviewed
across the recorded chain); 0 BLOCK / 0 WARN / 1 NOTE; security 0/0/0 at
60001de.*

<!-- REVIEW_META: {"date":"2026-07-02","commit":"3fdd91f","reviewed_up_to":"3fdd91f911d4205e6c3674f59336a0341589fcd8","base":"origin/main","tier":"refresh","block":0,"warn":0,"note":3} -->
