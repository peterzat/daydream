## Review — 2026-07-03 (commit: 7ca0194)

**Summary:** Full review of the "GPU headroom + modest multiplayer + prompt
audit + image-regen UI" turn: 42 files, +1900/-130 vs origin/main (6 commits,
400e483..7ca0194). The base (origin/main = f6b3265) postdates the prior
security scan, so every file in scope is new since it — reviewed at full depth.
The five substantive areas: (1) the GPU arbiter rewritten from a plain Lock
into a shared/exclusive future-queue gate (concurrent LLM slots, exclusive
image renders, text-priority admission, synchronous cancellation-safe
wake/release); (2) bounded drop-oldest subscriber queues in events.py that
never drop a WORLD_CHANGED control signal; (3) a slot-ownership guard on
kick/delete; (4) the vLLM `--max-num-seqs` flag + measured VRAM record; (5) the
dev room-image repaint UI (force/prompt_override render path, atomic write with
.prev, mtime-versioned cache URLs, new `api/rooms.py` endpoints, plate-tools +
dialog in web/). Two independent adversarial passes (arbiter/events concurrency;
regen + auth path) plus the author read found **0 BLOCK / 0 WARN** across the
whole diff — the concurrency cancellation paths, ring-buffer capacity/ordering,
path-traversal defense (room_id hits a parameterized DB lookup before any
filesystem path), CSRF/auth on the new POST, prompt non-persistence, atomic-
write containment, versioned-URL consistency, and the TOCTOU-free slot guard
were each traced and verified. Tests at this HEAD: short 783 / medium 1113 /
long 1116, all green (1 by-design dfrotz-oracle skip). Live-verified end to
end: the swarm probe (5 sockets survived, `llm 2/3 active`, text-priority
render wait, 0 events dropped) and the regen e2e (GET prompt, POST regen, mtime
bumped + .prev written + room_image_ready carried a newer ?v=).

**Security:** No separate `/security` run. The genuinely new external surface is
one HTTP endpoint pair (`api/rooms.py`) and one auth-guard change (`slots.py`);
both were covered at full depth by the dedicated security-lens adversarial pass
(auth, CSRF, path traversal, secret/ prompt retention, char cap, write
containment, guard bypass, TOCTOU — all clean). The remaining changed files add
no external-input handling (internal concurrency, a read-only tailnet-gated
status line, an env-int config reader, a dev CLI). SECURITY_META stays at
3fdd91f (no new findings; the scanned-paths set is unchanged in substance).

**External reviewers:** None configured.

### Findings

Five NOTEs, no BLOCK/WARN. Three were fixed in this turn (commit 7ca0194); two
are by-design edges recorded in BACKLOG.

[NOTE] daydream/events.py — `_put_bounded` carried a dead `global _dropped_total`
(it delegates counting to `_record_drop`), and its docstrings claimed control
signals are "NEVER" dropped, which is false for the unreachable, harmless
all-256-control-signals overflow. **Fixed:** global removed, docstrings
corrected.

[NOTE] daydream/api/rooms.py — the module docstring claimed the tool is
"expected to be turned off for real users," but no gate exists; any authed
tailnet session can repaint shared room art. **Fixed:** docstring now states the
gap and points at the BACKLOG gate. (See regen-ui-gate.)

[NOTE] daydream/api/slots.py + toons.py — `delete_slot` is irreversible yet gated
only on instantaneous WS liveness, so a transient socket drop can briefly mark a
live player's toon "abandoned" and let another session delete it. By-design under
friend-scope trust (mirrors claim's takeover); recorded as delete-slot-grace-
window in BACKLOG.

[NOTE] daydream/gpu/arbiter.py — `stats()` filters cancelled-ghost futures from
`waiting_llm` but the exclusive-admission guard uses raw `not _llm_q`, so a
cancelled queued llm can be briefly uncounted-yet-present. Cosmetic observability
skew only; provably self-corrects on the next release (the wake's first loop pops
ghosts before the exclusive loop runs). Not fixed (no code churn warranted).

[NOTE] web/assets/main.js:setRoomBackground — carried forward, untouched: the
bg-loading veil still has no `onerror` unveil; an art URL that fails to load
leaves the plate transparent. (The new repaint path reuses this same img and
overlay, so it inherits the same gap.)

### Fixes Applied

- [NOTE] events.py — removed the dead `global _dropped_total`; corrected the
  "NEVER dropped" docstrings to state the pathological, uncounted exception.
- [NOTE] rooms.py — corrected the "turned off for real users" docstring to admit
  no gate exists yet and point at the BACKLOG entry.
- BACKLOG — added regen-ui-gate and delete-slot-grace-window with revisit
  criteria.

### Accepted Risks

Carried forward from the prior entry (none aggravated):

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
  `world reset` `rm -rf` operator-trust. Unbounded slot-create body + event queues
  (the latter now bounded by EVENT_QUEUE_MAXSIZE=256, drop-oldest, this turn).

### Carried-forward open NOTEs (pre-existing)

Growth refusal `reason` narrated without an output banlist pass; parser raw-input
not role-separated; parser per-line command-expansion has no cap (parser.py:142);
dead `text` param in parser `_remember` (parser.py:191); toon-view N+1 inventory
query; dead `interpreter.py`; admin.py + bootstrap.py `_write_db` non-transactional;
no CSP/`X-Content-Type-Options` on the SPA shell; detail-inset de-dup keys on
object id first; keepsake captions are client-side flourish. None aggravated this
turn (parser.py/interpreter.py are below the review base — unchanged).

---
*Prior review (2026-07-02, commit 3fdd91f): refresh review of the entire Zork
platform turn (v0.6.0), 79 files / ~26K insertions; 0 BLOCK / 0 WARN / 3 NOTE
(parser command-expansion cap, dead parser `_remember` param, main.js onerror
unveil); chained /security 0/0/1 at 3fdd91f.*

<!-- REVIEW_META: {"date":"2026-07-03","commit":"7ca0194","reviewed_up_to":"7ca0194423154f61605c3ea1d93cfe850ac9133a","base":"origin/main","tier":"full","block":0,"warn":0,"note":5} -->
