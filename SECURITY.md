## Security Review — 2026-06-30 (scope: paths)

**Summary:** Path-scoped review of the playtest-polish turn (HEAD `f3da4f5`, the
10-commit run `ebc43bd`..`f3da4f5`, SPEC 2026-06-30 14/14), all of which lands
after the prior security pass at `777a289`. Scope: the picker-first WS entry +
two-producer command bus (`daydream/api/ws.py`), the witnessed-drift loop
(`daydream/drift.py`, new to security scope), the grounded parser's new
"look at"/"go to place" fast-paths (`daydream/parser.py`), the closed verb
registry + inventory verb + examine/say handlers (`daydream/verbs.py`), the
data-skill pipeline's second-person dispatcher (`daydream/skills/data.py`), the
typed toon view (`daydream/toons.py`), the SPA's scene/inventory/overlay/slot
rendering (`web/assets/main.js`) and its static structure (`web/index.html`, new
to scope), and the Opus-authored world envelope (`worlds/bunny.json`). Trust
model is unchanged friend-scope: `AccessMiddleware` (tailnet CGNAT `100.64.0.0/10`
+ loopback) and `CsrfOriginMiddleware` are the outer gates; in default
`tailscale` mode `auth.is_authed()` is True unconditionally, so tailnet
membership is the authorization. The WS endpoint still gates on `is_authed`
(`ws.py:396`) and closes 1008 otherwise.

The security spine held under tracing across every changed file. **The LLM never
mutates state directly:** the parser only selects a verb from the closed registry
and grounds dobj/iobj to ids it must find in the actor's enumerated scope
(`parser.py:107-122`), and the executor independently re-validates the verb is
known, the target resolves via `_resolve_in_scope`, and `verb in
objects.verbs_for(dobj)` (`verbs.py:144-163`), so a hallucinated or
client-supplied out-of-scope id cannot act at a distance. **The click/command
path is strictly narrower than free text:** `_handle_command` routes only through
`execute_command`, whose `get(verb)` knows only the closed `VERBS` dict, so a
command frame cannot invoke a data skill, and a stale/forged `dobj_id` is rejected
by `_resolve_in_scope`. **Per-verb effect allowlists are enforced:** each verb's
effects pass through `dispatch_effects(allowed=spec.allowed_effects)`; `talk`
deliberately omits `move_object` (`verbs.py:88`), and examine's `set_property` is
engine-constructed against the in-scope examined object with a hardcoded
`examined_text` key (`verbs.py:266-269`). **No new injection:** the new
`dobj_name` path ("take the moon" then "You don't see the moon here") and the
"You can't go X from here" line echo player free text into a narrate, but all
narrate/say text is escaped on the client before insertion. **No XSS:** every
`innerHTML` in `main.js` is a clear (`""`), an `escape()`-wrapped server string,
or `linkifyEntities` (which escapes the full text first, then injects only spans
whose attribute values are themselves `escape()`d); the new dream-overlay uses
`textContent` with static strings; the new scene chips set ids/kinds/verbs via
`dataset` and labels via `textContent`; slot rows escape `t.name` and interpolate
only an integer slot number; `img.src` takes server-built cache URLs and is not a
script sink. **No SQL injection:** every statement in `toons.py` is parameterized;
`_query`'s templated WHERE receives only hardcoded literal clauses from internal
callers, never user input. **No secrets / no PII:** the secret-pattern scan over
all nine scoped files returned only `{name}`-token references in `drift.py`
comments; `worlds/bunny.json` is fictional content (Wren, Rook, Iris, Bram) with
no real names, keys, or tokens. **The picker-first change is a net security
improvement:** it removed the legacy `t-wren` shared-toon fallback (a prior
accepted risk), so an unresolved session now controls no toon and is routed to
the picker via `needs_toon` instead of silently sharing one seeded toon. Net:
0 BLOCK / 0 WARN / 0 new NOTE.

Two changes lightly touch existing accepted risks without raising their severity.
(1) Witnessed drift (`drift.py`, `toons.py` dropped the now-dead
`occupied_room_ids`) makes a co-located NPC's ambient beat visible to a present
player. That beat can be tone-influenced by captured-memory prompt injection (the
accepted memory risk), but the drift LLM path is banlist-checked
(`drift.py:460`), escaped on render, room-scoped, and emits only a narrate plus a
fixed-bucket mood nudge (no `set_property`/`move`/`spawn`), so it cannot be turned
into a mutation vector. (2) The standalone room-affordance data-skill path
(`stoke`/`tend`) still dispatches with `allowed=None`, i.e. the full
`ALLOWED_KINDS` (`ws.py:384` to `data.py:394`), the documented v1 posture carried
below.

### Findings

No security issues identified in the reviewed scope.

### Accepted Risks

Carried forward from prior reviews; none re-flagged as findings. Items verified
against in-scope code this run are marked; the rest live in modules outside this
path-scoped scan and are carried unexamined.

- **LLM-chosen effect targets are unscoped, and per-skill
  `effects_schema.allowed_kinds` is advisory (verified in scope).** The
  standalone room-affordance data-skill path dispatches with the full
  `ALLOWED_KINDS` (`data.py:383-395` `execute_by_name` calls `execute` with no
  `allowed=`; `ws.py:384`), and an effect's `target_id`/`object_id`/`dest_id` is
  trusted without a scope/ownership check. Bounded to friend-scope game-state:
  `set_property` writes `properties_json` only and cannot reach the auth columns
  (`slot`, `controller_session`, `is_human_controlled`, `kicked_at`), so no
  privilege escalation; the `talk` verb still enforces its narrower per-verb
  allowlist (`verbs.py:88`, no `move_object`); all such content renders escaped.
  Reliability is low (the local 7B must break character and emit a precisely
  targeted effect with a valid unguessable id). Deeper fix is v2 BACKLOG
  `skills-authoring-and-security` (per-effect jsonschema, enforce each skill's
  declared `allowed_kinds`, target-authorization).
- **Stored prompt-injection via captured memory bypasses `wrap_player_input`
  containment (verified in scope).** NPC dialogue templates in `worlds/bunny.json`
  render `{{ m.text }}` (captured player text, `data.py:374-375`) without the
  `<player_input>` wrapper; `drift.py` wraps memory in `<memory>` tags but the
  same captured text feeds both. Output is banlist-checked and escaped; v0 impact
  bounded to mild voice/tone deviation. Witnessed drift makes such a deviation
  slightly more likely to be seen, with no new mutation capability (see summary).
  Deeper fix is v2.
- **v1 friend-scope on slot/session endpoints (verified in scope).** Any authed
  session may create / claim / kick / leave / delete any slot; `delete`
  permanently destroys the toon's carried things + memories
  (`toons.py:262-277`). CSRF on bodyless POSTs is closed by
  `CsrfOriginMiddleware`. Per-session ownership is v2 `multi-user-shared-world`.
- **Tailscale-mode auth (carried).** `auth.is_authed()` returns True
  unconditionally and `POST /api/login` short-circuits to authed; `AccessMiddleware`
  (CGNAT `100.64.0.0/10` + loopback) is the real gate; cookie `https_only=False`
  (LAN/Tailscale only). `AccessMiddleware`/`access.py` not in this scan's scope.
- **Object lifecycle / clutter-GC deferred (carried).** A player who
  prompt-injects an NPC's `talk` into repeated `spawn_object` effects can litter a
  room (bounded by `max_tokens`, the arbiter's single-stream serialization, and
  the `generated_by` dedup guard). v2 BACKLOG `object-lifecycle-clutter-gc`.
- **Operator-trust / out-of-scope-this-run (carried).** `AccessMiddleware`
  source-IP handling + CGNAT hardcoding; admin restore tar extraction
  (CVE-2007-4559 guarded); `bin/game world swap` loopback; `bin/game` env-file
  sourcing; engine bootstrap clones; unbounded slot-create body + event-subscriber
  queues. Live in modules outside this path scope; unchanged this turn.

**Resolved this turn:** the prior `LEGACY_TOON_ID = "t-wren"` shared-toon fallback
(every unclaimed session controlling one seeded slot-1 toon) is removed by
picker-first entry (`ws.py:402-412`); an unresolved session now controls no toon.

---
*Prior review (2026-06-30, paths, commit `777a289`): the objects+verbs+local-LLM-parser turn (unified `objects` store, closed verb registry + command bus, grounded parser, allowlisted effect API, per-NPC `talk` dialogue, keyless world load, the SPA's clickable-objects rendering). Found 0 BLOCK / 0 WARN / 1 NOTE (LLM-emitted effects take an unscoped, LLM-chosen target id; standalone data-skill path dispatches with the full effect vocabulary; bounded to friend-scope game-state, accepted). That NOTE carries forward here as the first accepted risk, verified unchanged.*

<!-- SECURITY_META: {"date":"2026-06-30","commit":"f3da4f54dcd8999cdb2bf658de4314bf682e1e86","scope":"paths","block":0,"warn":0,"note":0,"scanned_files":["daydream/api/ws.py","daydream/drift.py","daydream/parser.py","daydream/skills/data.py","daydream/toons.py","daydream/verbs.py","web/assets/main.js","web/index.html","worlds/bunny.json"]} -->
