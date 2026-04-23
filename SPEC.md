## Spec — 2026-04-23 — data skills + safety baseline

**Goal:** Unlock LLM-driven content variety by letting JSON-authored "data skills" extend the skill registry (with `forge` as the v1 showcase), and land the v1 safety floor (banned-words filter, refusal-schema handling, prompt-injection tag wrapping) in the same slice so no LLM-driven state mutation ever runs unprotected. Smallest change that moves the game beyond `look`/`say`/`examine`/`go` into a world where skills can mutate state under a reviewed safety contract.

### Acceptance Criteria

- [ ] **`bin/game world skill add <path>` installs a data skill from JSON.** Reads the file, validates the declared shape (required fields: `name`, `ui_hint`, `description`, `context_predicate_json`, `prompt_template`, `effects_schema_json`), and upserts a row in the existing `skills` table with `kind='data'` and `author` recorded. Malformed JSON or a missing required field exits non-zero with a diagnostic and writes nothing. Re-running with the same `name` updates in place (idempotent). The command runs with the server down; no requirement on a running FastAPI process.
- [ ] **The `forge` data skill ships as JSON and works end-to-end against a mocked LLM.** A checked-in `skills/forge.json` carries a non-trivial `prompt_template` that matches the WHIMSY tone. When the controlled toon is at `r-forge` and types `forge <something>`, the skill dispatches: the LLM returns JSON matching the skill's `effects_schema_json`, at least one effect beyond `narrate` is applied (e.g., an item is added to the forge room), and the player sees a `narrate` event describing the outcome. `forge` does NOT appear in `state_snapshot.skills` when the toon is in a non-forge room (the meadow, bridge, attic, or hollow).
- [ ] **Context predicates gate data-skill availability.** `registry.list_available_for_room(room_id)` returns every core skill plus every `enabled=1` data skill whose `context_predicate_json` matches the room. The v1 predicate format supports at minimum `{"room_slug": "<slug>"}`; an empty predicate `{}` means always-available. The WS `state_snapshot.skills` list and the LLM interpreter's candidate set both reflect the filtered view. A predicate the implementation does not understand fails safe (skill hidden, not leaked).
- [ ] **Effects execute through an explicit allowlist, not dynamic dispatch.** A data skill's LLM output is JSON shaped per its `effects_schema_json`. Only effect kinds enumerated in an allowlist in `daydream/skills/effects.py` are executed; the v1 allowlist covers at minimum `narrate`, `add_item`, and `set_mood` (the exact final set is the implementer's call but must be explicitly enumerated). An effect kind not on the allowlist is dropped with a log warning and replaced by a tone-appropriate `narrate` fallback; state is not mutated.
- [ ] **Banned-words filter blocks both input and LLM output.** A regex banlist in `daydream/llm/safety.py` (curated against WHIMSY.md: no modern-tech, no urgent/violent, no pixel-art / crunchy vocabulary) is applied at two points: **(a)** the player's free-text args reaching a data skill's prompt template — a hit short-circuits to a `narrate` "the dream won't hold that thought" (or similar), and no LLM call is made; **(b)** the LLM's narrate-text fields before effects apply — a hit drops effects and emits the same fallback. A tiny canonical banlist is checked in (enough to demonstrate both paths in tests); expanding it is not part of this spec.
- [ ] **Prompt-injection containment wraps player_input in role-separator tags.** When a data skill's `prompt_template` renders, the value bound to the `player_input` variable is wrapped in `<player_input>...</player_input>` tags before the LLM sees it, and any literal `</player_input>` inside the player text is neutralized (escaped, stripped, or equivalent — implementer's choice) so the player cannot break out of the tag. Template rendering uses Jinja2's `SandboxedEnvironment` so the template itself cannot reach protected attributes (`__class__`, `__globals__`, etc.).
- [ ] **Refusal schema short-circuits effects.** When the LLM's JSON response has `{"refused": true, "reason": "..."}` (the keys may be nested under `safety` or similar — the schema is the implementer's call), the executor emits a `narrate` event carrying the reason (or a tone-rewritten version) and applies NO effects from the same response, even when effects are present in the payload. Tests cover: refused-with-effects (effects dropped), refused-without-reason (generic tone-fallback narrate), non-refused-with-effects (effects applied normally).
- [ ] **Data skills load without a server restart.** After `bin/game world skill add <path>` (or an equivalent direct DB write) against a running server, the next WS snapshot reflects the new skill's availability without needing `bin/game down && up`. The mechanism (per-call DB read, registry refresh hook, something else) is the implementer's call; the observable is the criterion.
- [ ] **Tests cover the full path without GPU or network.** New unit tests in `tests/test_safety.py` exercise the banlist on input and output, the `player_input` tag-wrapping and break-out neutralization, and the refusal schema. New integration tests for the `forge` path with a mocked LLM client cover happy path, banned-input short-circuit, banned-output short-circuit, refused-response, and unknown-effect-kind. `tests/test_game_script.sh` (or an equivalent unit) covers `bin/game world skill add` success and malformed-JSON failure. All new tests run in the `tier_short` tier. `bin/game test short` passes before and after the change; no new `tier_medium` or `tier_long` cost.

### Context

**Adopted from BACKLOG entries** `data-skills-cli` and `safety-baseline-v1` (both now annotated `(ACTIVE in spec 2026-04-23)`). The backlog is explicit that these two must ship together: data skills let the LLM propose effects, and safety is load-bearing the moment that happens. Shipping data-skills-cli without safety-baseline-v1 leaves LLM-authored content mutating game state with no filter; shipping safety without data-skills leaves the filter with nothing to guard. The forge skill doubles as the v1 showcase and the smoke test.

**State coming in.** Multi-room-navigation shipped 7/7 (SPEC 2026-04-23), extending the world to 5 hand-seeded rooms. The existing `r-forge` room — "the quiet forge with embers drifting like sleepy fireflies" — is where the showcase `forge` skill will activate. The broader skill spine (`daydream/skills/core.py` + `registry.py` + `interpreter.py`) is stable: core skills `look`/`say`/`examine`/`go` are in place, the WS layer already asks `registry.list_available_for_room()` to build the skill list, and the LLM interpreter already receives that list as its candidate set. Adding data skills to the registry's return is the cleanest extension point.

**Schema already anticipates this.** `migrations/001_initial.sql` defined `skills(id, name, kind, context_predicate_json, prompt_template, ui_hint, effects_schema_json, author, safety_rating, enabled)` — every column this spec needs is already present. No new migration is required unless the implementer adds a column. Keep that option open if the prompt-injection containment or effect logging wants a dedicated field.

**Where things live (guidance, not prescription).**
- `daydream/skills/registry.py` — extend to load from DB alongside `CORE_SKILLS`; today the dict is hardcoded.
- `daydream/skills/data.py` (new, likely) — JSON-to-SkillSpec loader, context-predicate matching, the effect-dispatch loop.
- `daydream/skills/effects.py` (new) — allowlisted effect kinds (at minimum `narrate`, `add_item`, `set_mood`) + a dispatch function that mutates state + emits events. Every game-state mutation by a data skill goes through here.
- `daydream/llm/safety.py` (new) — regex banlist + `wrap_player_input()` helper + refusal-schema parser.
- `daydream/admin.py` — add a `cmd_skill_add` alongside the existing world commands, wired into `bin/game world skill add ...` (mirrors the `world archive/restore/delete` dispatch pattern).
- `skills/forge.json` (new, checked in) — the showcase data skill.
- `tests/test_safety.py`, `tests/test_data_skills.py` — new test modules.

**Aesthetic anchor (locked).** Spiritfarer / A Short Hike. Any `prompt_template`, refusal reason, fallback narration, and banlist entry needs to match the WHIMSY tone. The `forge` skill should read like a slow, warm ritual, not a crafting-sim mechanic. Banlist regex entries should target the anti-tones WHIMSY.md already names (urgent, pixel-art, modern-tech, violent). `WHIMSY.md` is the authority.

**Out of scope for this spec** (deferred; do NOT build):
- **Web UI for skill authoring.** Stays in `skills-authoring-and-security` (v2 BACKLOG). v1 authors via JSON files on disk.
- **`audit` table + `bin/game world undo --invocation N`.** Stays in v2. v1 trusts the allowlist + safety filter.
- **Content-safety ML classifier.** v1 is regex-only; the classifier is v2.
- **Strict `jsonschema` validation of every effect payload.** v1 validates effect *kind* against the allowlist; shape beyond that is the skill author's responsibility. Full `jsonschema` is v2.
- **Player-authored skills.** `player-authored-skills` BACKLOG entry stays deferred; v1 is admin-JSON-authored only.
- **Hot-reload cache invalidation across multiple worker processes.** Single-process daydream only.
- **NPC-authored skills / NPC dialogue.** No NPCs in v1 per `npc-drift-loop` still being deferred.

**zat.env conventions to respect.**
- Python venv at `.venv/`; `PIP_REQUIRE_VIRTUALENV=true` is global. Add `jinja2` to `pyproject.toml` if not already present.
- Commits attribute to `user.name` only; no Co-Authored-By trailers. Push only when explicitly asked.
- Work in small committable increments; tests in the same increment as code; re-run `bin/game test short` after each functional change.
- Per zat.env "Spec is code": `/codereview` will check this implementation against the nine criteria before any push.

**Critical files to create or modify:**

- `daydream/skills/data.py` (new; JSON loader, predicate matcher, dispatcher)
- `daydream/skills/effects.py` (new; effect allowlist + mutators)
- `daydream/skills/registry.py` (modify; union core + DB-loaded data skills)
- `daydream/llm/safety.py` (new; banlist, input wrapping, refusal parser)
- `daydream/llm/prompts.py` (modify; expose player_input wrapping helper for data-skill templates)
- `daydream/admin.py` (modify; add `cmd_skill_add`)
- `bin/game` (modify; dispatch `world skill add <path>`)
- `daydream/api/ws.py` (modify if registry API changes require it; the current `list_available_for_room` call site should not need to change if the API stays the same)
- `skills/forge.json` (new; the showcase data skill)
- `pyproject.toml` (modify; add `jinja2` if missing)
- `tests/test_safety.py` (new)
- `tests/test_data_skills.py` (new; forge end-to-end with mocked LLM)
- `tests/test_game_script.sh` (modify; skill-add CLI coverage)
- `WHIMSY.md` (optionally modify; codify the banlist's anti-tone vocabulary if it isn't already there)

---
*Prior spec (2026-04-23): multi-room navigation shipped 7/7 — migration 004 seeds 5-room world with bidirectional exits, `go` core skill + `set_current_room` helper, WS `_state_snapshot` exposes `current_room_id` + `room.exits` dynamically, SPA renders exits as clickable buttons via the canonical-bypass path.*

<!-- SPEC_META: {"date":"2026-04-23","title":"data skills + safety baseline","criteria_total":9,"criteria_met":0} -->
