## Spec — 2026-04-24 — NPC dialogue (Rook speaks)

**Goal:** give Rook a voice via the existing data-skill pipeline. Author `skills/rook.json` as a per-NPC data skill scoped to r-forge; the player types `rook <text>` at the forge and the LLM composes Rook's response in WHIMSY tone, emitted as a `narrate` effect. Closes the "feels alive" arc started by first-NPC + presence-narration without adding new infrastructure, and directly unblocks `voice-samples-capture` and `qwen-2.5-7b-rp-ink-trial` (both gate on real NPC narration).

### Acceptance Criteria

- [x] **`skills/rook.json` ships as a data skill that voices Rook, scoped to r-forge.** A new file `skills/rook.json` declares `name: "rook"`, `context_predicate: {"room_slug": "forge"}`, a non-trivial WHIMSY-toned `prompt_template` that establishes Rook's persona (seed + appearance_seed voice: slow-moving, hums at the bellows, kind eyes) and asks the LLM to compose a single `narrate` effect describing Rook's response in third-person prose. The author file passes the existing `bin/game world skill add` validation gate.

- [x] **At r-forge, `rook <text>` dispatches Rook's response through the data-skill pipeline.** When the controlled toon is at r-forge and types `rook <anything>` (via canonical bypass with the room-filtered skill list) OR types free text that the interpreter routes to the "rook" skill, the data-skill executor runs through safety (banlist + player_input tag wrap) -> Jinja `SandboxedEnvironment` render -> LLM call -> refusal parse -> output banlist -> effects dispatch. With a mocked canned LLM response containing one `narrate` effect, the narrate event reaches the client with the canned text intact. Empty args (`rook` alone, e.g. from a button click) render the template with empty `player_input` and still produces a response (the template guides the LLM to invite a question).

- [x] **Rook is hidden outside r-forge.** At any non-forge room, the "rook" skill does NOT appear in `state_snapshot.skills`, and typing `rook <anything>` does NOT dispatch the skill — it falls through to the LLM interpreter with a room-filtered candidate list that excludes "rook", then produces the normal chat-fallback narrate for uninterpreted input. This is the existing context-predicate gate; criterion is a regression guard.

- [x] **Rook's response path inherits the safety baseline unchanged.** Banlist hits on player args short-circuit before the LLM call (fallback narrate, no LLM round-trip). Banlist hits on the LLM's response (across `text`, `seed`, `name`, and `mood` fields in any emitted effect) drop the effects and emit the fallback narrate. Refusal schema (`{"refused": true, "reason": "..."}`) short-circuits effects and narrates the reason. Jinja `SandboxedEnvironment` blocks template-side reach into protected attributes. These are the existing `daydream/skills/data.py` contracts; criterion asserts the authored `rook.json` template does not accidentally bypass any of them.

- [x] **Tests cover the dialogue flow without GPU or network, and existing tests stay green.** New tests (tier_medium unless noted): (a) `skills/rook.json` installs via `admin.main(["skill", "add", ...])` and registry.find("rook") returns the data spec. (b) At r-forge with a mocked LLM returning a canned narrate, `rook <text>` produces the expected narrate event with the canned text, AND the prompt passed to the LLM wraps player_input in `<player_input>...</player_input>` tags. (c) At r-meadow, `rook hello` falls through to the interpreter (no rook dispatch, no rook-voice narrate in the resulting events). (d) Banned-input short-circuit: `rook <pixel-art ...>` at r-forge emits the fallback narrate and does NOT call the LLM. (e) Refusal path: a canned refusal response narrates the reason, no effects applied. All new tests are no-GPU / no-network via the existing LLM mock. `bin/game test short` + `bin/game test medium` both green before and after.

### Context

**Adopted from proposal (2026-04-24 turn-close), direction 1.** The proposal named four candidate directions; this spec is direction 1, "`say to <npc>` + reactive NPC response." The testing-debt direction (gameplay-scenario-tests + security-tests-tier, two turns aging) stays deferred for one more turn; `toon-slot-management` and the keeper-image moment stay deferred.

**Scoping choice: Option B (NPC-as-data-skill) over Option A (new `say_to` core skill).** Authoring each NPC as a data skill named after them reuses every piece of the existing pipeline — context predicates scope the NPC to their room, the safety baseline gates the LLM round-trip, the effect allowlist constrains what the NPC can cause, Jinja sandboxing protects the template. The player verb becomes the NPC's name itself (`rook <text>`), which matches the project's existing data-skill UX (`forge <text>`). Option A would have required an async-aware core skill or a new `say_to` parser + separate response path; Option B is strictly additive, zero new infra, and each future NPC is just another authored JSON file. Tradeoff noted: players type `rook hello` rather than `say to rook hello`; that's a verb-noun ordering the project already uses for `forge`, and the interpreter handles natural-language variants ("hi rook", "hey rook there") by routing to the closest matching skill.

**Why narrate instead of a new "say" effect.** The existing effect allowlist (`narrate`, `add_item`, `set_mood`) has no "say as another toon" kind. Adding one would require a new allowlisted effect, schema work, and `events.append` with actor_id routed to the NPC. v1 narrate suffices: Rook's response reads as third-person prose ("Rook looks up from the anvil: 'the embers keep me good company'") which is natural in a cozy text adventure. A first-class `say` effect by a non-player actor becomes relevant when NPCs can initiate dialogue unprompted (drift-loop territory); deferred until then.

**Where things live.**
- `skills/rook.json` (new). Mirrors the shape of `skills/forge.json`. Non-trivial prompt_template that: establishes Rook's persona; wraps `{{ player_input }}` (already role-separator-protected by the executor); guides the LLM to compose ONE narrate effect in third-person WHIMSY tone, or refuse via the standard schema if the request is off-tone or outside what a small cozy forge would hold.
- `bin/game world skill add skills/rook.json` installs the skill; the existing CLI upsert and validation cover this end of the flow.
- No Python changes required. The WS bypass uses the room-filtered list, the data-skill executor runs end-to-end, the safety baseline applies. This spec is primarily content work + tests.
- `tests/test_ws_rook.py` (new, parallel to `tests/test_ws_forge.py`) — or add to an existing file; implementer's choice. The important properties: install from the authored file, happy path with canned LLM, hidden-outside-forge regression, banlist + refusal sub-cases.

**Out of scope for this spec** (deferred; do NOT build):
- **NPC memory.** Rook has no persistent memory of prior conversations. `npc-memory-retrieval` BACKLOG entry stays deferred.
- **NPC-initiated dialogue.** Rook doesn't speak unprompted. `npc-drift-loop` stays deferred; would need a drift scheduler and the "say as another toon" effect kind.
- **Voice A/B with the Qwen RP-Ink finetune.** `qwen-2.5-7b-rp-ink-trial` stays deferred but its revisit criterion ("real NPC dialogue lands") is triggered by this spec; pairs naturally with the next turn.
- **Aesthetic voice-samples capture.** `voice-samples-capture` stays deferred; same "real NPC dialogue" revisit criterion now triggered.
- **A second NPC.** Rook is the only NPC; a second would be another migration + another data skill file. Not in this scope.
- **`say to <npc>` natural-language parsing.** The verb is the NPC's name. "say to rook hello" routes via the interpreter like any other free-text; no dedicated parser.
- **`talk to <npc>` / `greet <npc>` synonyms.** The interpreter handles natural-language variants by routing to the closest matching skill; no per-variant coding needed in v1.

**zat.env conventions to respect.**
- Small committable increments; tests in the same commit as the code / content they cover. Since this spec is largely content (one JSON file) + tests, a single commit covering both is fine.
- Commits attribute to `user.name` only; no Co-Authored-By trailers. Push only when explicitly asked.
- Re-run `bin/game test short` after each change; confirm clean baseline before adding new work.
- The authored prompt_template is the voice-critical artifact. WHIMSY.md is the authoritative tone bible; read it before drafting. The drift-catcher test pattern in `tests/drift/` covers image / JSON drift; voice drift for Rook's prompt is not spec'd yet (belongs in `voice-samples-capture`).

**Critical files to create or modify:**

- `skills/rook.json` (new; the showcase NPC dialogue skill)
- `tests/test_ws_rook.py` (new, or extend an existing test module)
- Possibly adjust one or two existing tests if they assert on the exact set of data skills installed (none known to do this today, but verify).

---
*Prior spec (2026-04-24): NPC presence narration shipped 5/5 — migration 007 adds `toons.presence_text` (Rook's greeting author-set, Wren's NULL), WS broadcast loop emits one narrate per co-located NPC with non-empty presence text in the controlled-move branch only (initial connect and effect-mutation refresh both stay silent), forge E2E tests updated to consume the new narrate.*

### Proposal (2026-04-24)

**What happened.** NPC dialogue shipped 5/5 in one single-commit increment per the spec's content+tests scoping: `skills/rook.json` authors Rook as a data skill scoped to r-forge (context_predicate `{"room_slug": "forge"}`, WHIMSY-toned prompt_template that wraps `{{ player_input }}` via the safety baseline's role-separator tags and asks for one `narrate` effect composing Rook's response as third-person prose + one quoted line of dialogue, refusal schema explicitly taught for off-tone requests). No Python changes; the authored skill plugs into the existing data-skill pipeline end to end. `tests/test_ws_rook.py` (7 tier_medium cases): install + registry view, happy path with player_input tag-wrapping assertion, empty-input acknowledgement, hidden-in-meadow via dispatch (one LLM call proves it) + hidden in the snapshot's skills list, banned-input short-circuit, refusal schema narrates the reason while dropping companion effects. 335 -> 342 short+medium green.

**Questions and directions.**
- *Voice-samples-capture + the Qwen RP-Ink trial, paired*. Both BACKLOG entries' revisit criteria triggered this turn ("real NPC narration lands"). The smallest coherent slice: render Rook's responses to 3-5 anchor player inputs to `docs/pretty/voice-samples/<date>.md`, then A/B `Qwen/Qwen2.5-7B-RP-Ink` against the current `Qwen2.5-7B-Instruct-AWQ` across the same prompts. Directly pays off the "feels alive" arc by closing the loop on voice quality and arming the agent to catch voice drift going forward.
- *Second NPC + npc-drift-loop*. A second NPC would plant the drift-loop's "at least 2 NPCs" revisit criterion; drift then makes NPCs feel active between player visits. Bigger scope (second migration + scheduler + mood/weather deltas) but meaningfully different texture from turn-to-turn.
- *Testing debt, still aging*. `gameplay-scenario-tests` + `security-tests-tier` have been deferred candidates for three and two turns respectively. The existing forge + rook WS tests ARE scenario tests; formalizing the tier would cement the pattern. `security-tests-tier` is lower urgency given the unit coverage in test_safety.py + test_data_skills.py, but still worth naming explicitly.
- *Keeper image moment (not a spec)*. Rook now speaks. A `bin/game up` + browser eyeball of Rook-at-the-forge with a real LLM + a `pretty rook-at-forge` capture would be a lovely turn-close before context moves on. Operator-initiated, not infra.

**Revisit candidates** (BACKLOG sweep; criteria now plausibly hold):
- `voice-samples-capture` — revisit criterion ("real NPC dialogue lands") just triggered this turn.
- `qwen-2.5-7b-rp-ink-trial` — same trigger; pairs naturally with voice-samples-capture.
- `gameplay-scenario-tests` — three turns of revisit-candidate standing; test_ws_rook.py and test_ws_forge.py are already the scenario pattern in practice.

<!-- SPEC_META: {"date":"2026-04-24","title":"NPC dialogue (Rook speaks)","criteria_total":5,"criteria_met":5} -->
