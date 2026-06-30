## Spec — 2026-06-30 — objects + local LLMs: a MOO-style object/verb core with natural-language input

**Goal:** Make in-world things (toons, NPCs, items, rooms) first-class **objects** with properties and **verbs**, unify them under one store, and route player text through the local LLM so natural phrasings ("say hi to rook", "talk to rook") do the right thing. Establish the durable building blocks — objects, properties, verbs, a structured command bus, an allowlisted world-mutation effect API — that let the local model + game loop produce natural, growing interactions, and ship a small generative-object slice (Rook's "sheaf of papers"). Includes a destructive world reset onto the new schema.

Adopted from plan `~/.claude/plans/the-output-of-this-greedy-hedgehog.md` (read it for full background, the MOO/LLM research, and the scope rationale). Scope decisions are locked there and summarized in Context.

### Acceptance Criteria

*Object model & schema (full single-objects unification)*

- [x] **One unified object store.** A single `objects` table holds rooms, toons, and things, discriminated by `kind`; the separate `rooms`/`toons`/`items` tables no longer exist after migration. Verifiable: schema inspection (an `objects` table with id, world_id, kind, name, aliases, a containment link, a prototype link, and a properties bag; old tables absent) and `bin/game test medium` boots its TestClient against the new schema.
- [x] **Containment via location.** A room's contents are the toons + things located in it; a toon's inventory is the things located on it; rooms are top-level. Moving a thing (take/drop) or a toon (go) updates its location and is reflected in the next `state_snapshot`. Verifiable via the object access layer + a WS snapshot test.
- [x] **Prototypes provide default verbs/properties.** Prototype objects (`kind='prototype'`) exist for at least `npc`, `thing`, `readable`, `room`; a concrete object references a prototype and inherits its verb set. Verifiable: a `readable` thing exposes the readable/thing verbs without per-object re-declaration.
- [x] **Slot lifecycle intact on the new schema.** Create / claim / kick / delete / leave all still work and per-world slot uniqueness for human toons is enforced (a second create in an occupied slot is refused). Verifiable via the existing slot/session tests adapted to the new schema.

*Verbs & dispatch*

- [x] **Closed verb registry with arg-specs.** `look`, `examine`, `take`, `drop`, `talk`, `say` are engine-implemented verbs, each declaring whether it needs a direct/indirect object and which target kinds are valid; an object's available verbs derive from its kind/prototype. Verifiable.
- [x] **MOO dispatch priority.** A command resolves its handler by searching player → room → direct-object → indirect-object (first match wins); a verb bound to a specific object (e.g. an NPC's `talk` dialogue) is selected over a generic default. Verifiable: `talk` to Rook runs Rook's bound dialogue, not a stub.
- [x] **take/drop move objects; invalid targets are refused.** `take` moves a thing into the actor's inventory and `drop` moves it to the current room, via the world-mutation effect API, reflected in the next snapshot; a target that is out of scope or the wrong kind (e.g. `take` a toon, `talk` to a rock) is rejected with narration and no state change. Verifiable.

*Structured command bus & local-LLM parser*

- [x] **One executor, two producers.** UI clicks and free text both produce a structured command `{verb, dobj_id?, iobj_id?, args?}` executed by a single `execute_command`; a UI command frame (`{kind:"command", …}`) executes with **no LLM call**. Verifiable: assert the command path issues zero LLM calls.
- [x] **Grounded natural-language parsing.** Given the in-scope object list, the parser maps free text to a grounded command (selecting object **ids**): with a mocked LLM, "say hi to rook", "talk to rook", and "greet rook" (Rook in scope) all resolve to `talk(t-rook, "hi")`; bare "say hi" resolves to `say("hi")`. Verifiable via mocked-LLM unit tests.
- [x] **Deterministic fast-path.** Exact exit directions (e.g. "north") and bare verb words resolve to commands without an LLM call. Verifiable: assert zero LLM calls on these inputs.
- [x] **Malformed/unresolvable parses fail safe.** A parser result naming an unknown verb, or a direct/indirect object that is out of scope or ambiguous, mutates no state and yields a graceful "I don't understand"-style narration. Verifiable by injecting such mocked LLM output.
- [x] **LLM is a hard dependency; outage degrades gracefully.** When the LLM is unavailable, free-text natural-language input yields a "the dream is foggy" narration, while deterministic click/exit verbs (examine-of-cached, take, drop, go) still execute. Verifiable via `LLMUnavailable` injection.

*World-mutation effects & generative objects*

- [x] **Allowlisted world-mutation effect API.** All state change flows through an allowlisted effect vocabulary (`narrate`, `set_property`, `spawn_object`, `move_object`); a verb's emitted effects are validated against its per-verb allowlist and a disallowed effect kind is rejected (not applied). Verifiable: an effect outside a verb's allowlist does not mutate state.
- [x] **Explicit-spawn generative objects.** A verb whose (mocked) LLM output emits `spawn_object` creates exactly one persistent, clickable `thing` (e.g. Rook's papers) located in the room or on the NPC; narration is never auto-scanned for nouns; re-running the verb does not duplicate the object. Verifiable via mocked-LLM test.
- [x] **Lazy-cache examine.** Examining an object that lacks cached detail generates its description via one LLM call and persists it as a property; a second examine returns the cached text with **zero** LLM calls. Verifiable via mocked-LLM test (one call, then none).

*UI: visible, distinct, clickable objects*

- [x] **Objects render, distinct and clickable, with a verb bar.** The SPA renders the room's things + toons + the player's inventory as clickable elements carrying object id + kind (items, previously sent-but-unrendered, now appear); in-scope object names appearing in narration render as clickable; a verb bar offers Examine / Take / Drop / Talk with verb-then-object targeting and object-click-defaults-to-Examine; there is no generic "go" button (direction buttons remain the only nav affordance). Verifiable via a frontend markup test (clickable object spans, data attributes, verb bar, absence of a generic go control) + a one-time browser eyeball.

*World authoring (keyless) & reset*

- [x] **Keyless object-schema authoring.** `load_world` builds a valid new-schema DB from an Opus-authored JSON envelope with **no LLM call and no API key**, including rooms/toons/things/prototypes/aliases and per-NPC `talk` dialogue bindings, and refuses a malformed envelope. Verifiable via a `tier_medium` fixture test (no network, no key).
- [ ] **The live world is reset onto the new schema.** The existing w-bunny world is archived (insurance), then re-authored on the object/verb schema and installed as the live world; the game boots and a seeded NPC affordance can spawn the canonical papers object. Verifiable: server boots on the reset world + a one-time browser check. *(Code complete + verified: the reset world is authored at `worlds/bunny.json`, loads keyless, and its Rook spawns the papers in an integration test. The remaining step is the destructive operator action — `bin/game down` → `bin/game world archive w-bunny` → `bin/game world load worlds/bunny.json` → install as `worlds-dev/live.db` → `bin/game up` — plus the browser check. Left to the operator since it disrupts live state and brings the server up.)*

*Cross-cutting*

- [x] **Tiers green; a parser drift probe; docs + backlog rolled forward.** `bin/game test short` and `bin/game test medium` exit 0 with paired tests for each item above (all GPU/LLM-free via mocked LLM); a `tier_long` drift probe grounds real Qwen output to in-scope ids across a small command corpus (JSON adherence + correct verb/dobj selection). CLAUDE.md documents the object/verb/world-mutation model and the "LLM is a hard runtime dependency" stance; README updated; `BACKLOG.md` swept (the four shipped 2026-06-29/30 entries — room-description-on-entry, session-presence-polish, world-authoring-in-session, world-hot-swap — marked done) and the new deferred items recorded (player-touch promotion, object lifecycle/clutter-GC, deep prototype inheritance, two-object verbs, user-authored LLM-driven world-building verbs).

### Context

**Generation policy (load-bearing — CLAUDE.md "Generation policy").** Runtime uses ONLY local models on the RTX 4000; there is no production API key. The natural-language parser, talk dialogue, and examine-generation all run on the local Qwen 2.5 7B Instruct AWQ via vLLM behind the GPU arbiter. Design-time world authoring is Opus-in-Claude-Code writing a keyless envelope (`load_world`). This turn makes the local LLM a **hard runtime dependency**: "the dream is foggy" is an outage message, not a play mode (the `bin/game up` GPU preflight is the guard). Tests must remain GPU/LLM-free by mocking `daydream.llm.client` (the existing suite already does this).

**Locked scope decisions (from the plan's Q&A).** Full single-`objects` schema (not additive). Verbs this turn: Examine/Take/Drop/Talk, single-object only (give/use two-object → backlog). Generative objects: explicit `spawn_object` + lazy-cache now; **player-touch promotion is out of scope this turn** (documented next increment). Verbs are closed/engine-implemented; the effect vocabulary is deliberately shaped as a general world-mutation API (future `spawn_room`/`link_exit`/`destroy_object` documented, not built) so future **user-authored, LLM-driven world-building** slots in without re-architecting.

**"LLM as parser/grounder, deterministic engine as executor."** The LLM never mutates state; it only selects a verb (closed set) + grounds entities to in-scope ids. The engine validates and dispatches; mutation happens only through the allowlisted effect API. This generalizes daydream's existing effect-allowlist + `wrap_player_input` role-separation + refusal/banlist safety (`daydream/skills/{effects,data,interpreter}.py`, `daydream/llm/safety.py`) — carry those forward, do not regress them.

**Key seams (verify against current code; full list in the plan).** New `daydream/objects.py` (object access layer) + refit of `toons.py`/`rooms.py`/`items.py` and their callers (`api/ws.py`, `api/slots.py`, `memories.py` npc_id→object_id, `admin.py`, image-cache `target_kind`). Generalize `skills/{registry,core,data,interpreter,effects,prompts}.py`. New `migrations/011_*` creating `objects` + prototypes and dropping the old tables. Update `daydream/llm/bootstrap.py` (`_validate_envelope`, `_write_db`, `_SYSTEM_PROMPT`) for the object envelope. The canonical world id stays `w-bunny` so existing hardcoded references survive. Frontend: `web/index.html`, `web/assets/main.js` (`renderSnapshot`/`renderEvent`/exit+skill bars/`sendInput`), `web/assets/style.css`.

**zat.env practices (this is the largest turn to date).** Land it as small, individually-tested, committable increments — the plan's suggested order is schema + object layer (green) → verbs/command-bus → parser → UI → generative → reset + docs. Write paired tests in the same increment as the code; never stack untested changes; run `bin/game test short` between increments. Acceptance criteria are the contract the pre-push `/codereview` checks for spec alignment. **Pre-agreed cram fault-line:** if mid-build the turn is too large, defer the generative slice (the two "generative objects" criteria) to its own follow-up turn — the object/verb/parser/UI core + reset is the irreducible foundation. Verification is TestClient/mocked-LLM oracles plus the noted one-time browser eyeballs; the destructive reset removes data-migration risk.

---
*Prior spec (2026-06-29): session & presence — room descriptions on entry, fresh sessions, toon delete, keyless authoring; closed 8/8.*

<!-- SPEC_META: {"date":"2026-06-30","title":"objects + local LLMs: a MOO-style object/verb core with natural-language input","criteria_total":19,"criteria_met":18} -->

<!-- The object/verb/parser/UI/generative core landed as committable, test-green increments (short + medium tiers pass; a tier_long parser-grounding probe ran live against vLLM and grounded all cases correctly). The only open criterion is the destructive LIVE world reset (archive + install + boot + browser eyeball), left as a flagged operator action since it disrupts live state and brings the server up; the reset world is authored, loads keyless, and spawns the papers in an integration test. The UI criterion's frontend markup + WS-snapshot tests pass; its one-time browser eyeball is the same flagged manual confirmation prior specs used. (Original meta said criteria_total 18; the actual count is 19.) -->

