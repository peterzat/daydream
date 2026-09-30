# Backlog

Durable register of considered proposals that were deferred, scoped out, or
rejected. Read before drafting a new SPEC.md; swept at turn close. Long-form
context for every entry below lives in `~/.claude/plans/let-s-design-a-fairly-giggly-narwhal.md`.

## v1: cozy single-player loop

### drift-pools-for-loft-npcs — CLOSED 2026-07-07 (shipped, v1.0 turn)
- **One-line description:** `daydream/drift.py`'s hand-authored canned pools (`_DRIFT_POOLS`) and selection weights (`_NPC_DRIFT_WEIGHT`) are still keyed to the retired bunny-world NPCs (`t-rook`/`t-iris`); the live Clockmaker's Loft NPCs (Tace/Bell/Mott) fall through to the shared generic pool on the offline path, so canned drift is voice-neutral in the canonical world. Author per-NPC pools for the loft, or better, let the world envelope carry pools so `world load` installs them for any future world.
- **Closure:** The envelope-carried option shipped (the better path): toon `properties.drift_pools` validated by the loader, `drift._pools_for` prefers authored pools over the legacy id-keyed dict, and `worlds/clockmakers-loft.json` authors WHIMSY-voice pools for Tace/Bell/Mott (own-mood + default buckets; Tace covers the post-quest `gladdened` mood). Any future world closes this for itself by authoring pools.
- **Origin:** state audit 2026-07-02 (first Fable session sweep).

### drift-variety-richer-beats — CLOSED 2026-09-26 (pivot, criterion 11)
- **Closure:** Drift is authored-first now: NPCs with authored pools speak authored lines (per-mood, per-phase, and per-phase-in-a-room buckets such as `night@r-lamphouse`), never repeating a line within its recent tellings in a room (`daydream/variants.py`); the local model may only lightly vary an authored line (validated, `DAYDREAM_DRIFT_VARY_PROB`, 0.3) and every varied line is tagged `src: "local"`. The Lost Hours cast authors 12 to 25 drift lines per resident.
- **One-line description:** Reduce NPC drift repetition beyond the v0 mitigation (laconic prompt + a "vary the beat" nudge in `_DRIFT_SYSTEM_PROMPT` + a consecutive-near-duplicate suppressor in `daydream/drift.py:_tick`). Options: per-NPC canned-pool rotation tracking recently-used beats, a "recently noticed" exclusion passed into the drift prompt, or richer hand-authored pools so Qwen 7B isn't leaned on for variety. The 7B reliably fixates on a seed's most salient image (Rook -> "hums softly, moving the bellows") regardless of mood/memory.
- **Why deferred:** v0's de-dup suppresses the *visible* consecutive repeats (the player won't see them stacked), so this is variety polish, not a correctness fix. Wants the drift-samples golden + a "distinctness over N ticks" metric before tuning.
- **Revisit criteria:** Playtesters report a room's NPC feeling samey across a session even with de-dup, or when adding NPCs whose seeds are similarly single-image.
- **Origin:** playtest follow-up (plan note-that-when-the-snuggly-music), drift-voice-samples 2026-06-30

### dialogue-refusal-fallback-on-benign-input — CLOSED 2026-07-07 (investigated, not reproducible)
- **One-line description:** Occasionally an in-character dialogue turn degrades to the "the dream won't hold that thought" fallback on a benign input (observed once on "hello" in `voice-samples`): the model's spoken line trips the output banlist / refusal path (`daydream/llm/safety.py`, `daydream/skills/data.py` `_BANNED_FALLBACK_TEXT`) or the narrate truncates. Investigate whether it's flaky (sampling) or systematic (a banlist false-positive / max-tokens), then tighten the trigger or raise the cap.
- **Closure (SPEC 2026-07-07 criterion 8):** The repeatability pass ran as a layer-attributing probe — `tests/drift/test_dialogue_refusal_probe.py` (tier_long) drives 21 live greeting turns (Tace/Bell/Mott × 7 greetings, real vLLM, temp 0) with pass-through spies on every layer (input banlist / LLM error / refusal parse / output banlist / empty effects). Result 2026-07-07: **0/21 fallbacks**, all layers quiet (evidence: `tests/baselines/dialogue_refusal_probe.ratified.json`, the git-tracked copy of that run; the journal probe's graded run is likewise tracked at `tests/baselines/journal_probe.ratified.json`). The single 2026-06-30 observation predates the dialogue-voice rework (third-person `_dialogue_system` + per-NPC authored templates, 2026-07-01/02) and does not reproduce on the current pipeline; verdict: sampling flake on the retired prompt shape, no systematic false positive. The probe stays as the tier_long regression (≤15% gate + hard-zero input-banlist), and `tests/security/test_benign_refusals.py` pins the deterministic halves (greetings never trip the input banlist; horological/craft vocabulary never trips the output banlist; each banlist category still blocks its own words).
- **Correction (2026-09-26):** that 0/21 run drove `execute_by_name`, which resolves no NPC for envelope `dlg-*` skills, so it measured the second-person dispatcher prompt, not the third-person dialogue voice `talk` uses. The probe now takes the production `talk` path (`npc=`, talk's effect allowlist). Re-measured on the real path with the new model (Qwen3.5 9B): still 0/21, and the verdict stands (`dialogue_refusal_probe.ratified.json` re-ratified).
- **Origin:** playtest follow-up (plan note-that-when-the-snuggly-music), voice-samples 2026-06-30

## v2: shared world + skill authoring

### multi-env-layout
- **One-line description:** Add `--env dev|preview|prod` flag in `bin/game` that pins separate ports (8080/8081/8082) and separate `~/data/daydream/worlds-{env}/` dirs; vLLM and ComfyUI shared across envs (one warm process serves all three FastAPI processes).
- **Why deferred:** v0 only has dev. Multi-env needs world-hot-swap + snapshot to be useful (otherwise three identical envs is just three ports).
- **Revisit criteria:** At least one stable "preview" config worth running alongside dev for stakeholder review.
- **Origin:** plan let-s-design-a-fairly-giggly-narwhal

### multi-user-shared-world
- **One-line description:** Single asyncio task drains event log to disk per world (single-writer pattern); websocket fanout to all sockets in a room from `daydream/api/ws.py`; per-toon human-NPC handoff with grace period and reconnect tokens; load-test harness (10 bots, 10 min) with smoke metrics in `bin/game status`; nightly snapshot cron retaining 14 days under `~/data/daydream/snapshots/`.
- **Why deferred:** v0 is single-user. Concurrency design needs careful write-contention testing and benchmarks before claiming readiness.
- **Partially landed (2026-07-02, plan let-s-do-a-small-compiled-umbrella):** the GPU-contention half shipped — arbiter v2 (shared LLM slots / exclusive renders / text-priority admission, `daydream/gpu/arbiter.py`) so concurrent players' text no longer serializes behind each other or a cold render; bounded drop-oldest subscriber queues so one wedged socket can't balloon memory (`daydream/events.py`, control-signal-safe); a slot ownership guard so a second session can't kick/delete an active player's toon (`daydream/api/slots.py`); `/status/arbiter` gate+event-drop metrics in `bin/game status`; and a modest load probe `tools/ws_swarm.py` (N≤5 bots, walk+chatter, socket-liveness assertion) — the "10-bot harness" line, modest edition. **Still stands:** single-writer event drain, reconnect/handoff tokens with a grace period, the full 10-bot/10-min load test as a gate, and the nightly snapshot cron.
- **Revisit criteria:** Two or more humans want to share a session, or before claiming the v2 "shared dream" milestone done.
- **Origin:** plan let-s-design-a-fairly-giggly-narwhal

### skills-authoring-and-security
- **2026-06-30 reframe (objects + verbs spec):** verbs now largely replace skills as the interaction surface, and the same allowlist + role-separation + refusal/banlist pipeline now guards LLM-driven **world-mutation** effects (`narrate`/`set_property`/`spawn_object`/`move_object`), not just dialogue. This entry narrows to the web authoring UI + the deeper pipeline (jsonschema, content-safety classifier, audit/undo); the effect-allowlist substrate it depended on is in tree and generalized.
- **One-line description:** Web UI at `daydream/api/` for admin to edit `prompt_template`, dry-run against a sandbox, and publish; full six-layer security pipeline (Jinja2 SandboxedEnvironment, role separation with `<player_input>` tags, jsonschema validation, effect allowlist enforced in `daydream/skills/effects.py`, content-safety classifier in `daydream/llm/safety.py`, `audit` table + `bin/game world undo --invocation N`).
- **Why deferred:** v1 ships data-skills-cli (admin authors via JSON files); the web UI + full security pipeline land in v2 once a real authoring rhythm exists and the threat model is exercised.
- **Revisit criteria:** Admin uses JSON-CLI authoring frequently enough that a UI pays off; or first time a data skill produces an unwanted effect that needs to be rolled back.
- **Origin:** plan let-s-design-a-fairly-giggly-narwhal

### litellm-proxy-fallbacks
- **One-line description:** Stand up the LiteLLM proxy as a separate process; configure Qwen → Claude fallback chain on local outage; add cost tracking and per-model rate limits in proxy config rather than game code.
- **Why deferred:** v0/v1 use `litellm` as a Python library only — no extra process, no extra port. The proxy adds operational overhead that pays for itself only once a third backend or an automatic-fallback need exists.
- **Revisit criteria:** Want to add Cloudflare Workers AI as a third backend, OR want automatic fallback when local vLLM is unreachable, OR multiple environments need shared rate-limiting.
- **Origin:** plan let-s-design-a-fairly-giggly-narwhal

## v2: objects + verbs (deferred depth, captured 2026-06-30)

Deferred depth from the objects + local-LLMs spec (plan `the-output-of-this-greedy-hedgehog`). The object/property/verb core, command bus, grounded parser, clickable UI, and the explicit-spawn + lazy-cache generative slice shipped; these are the prepared-for next increments.

### player-touch-object-promotion
- **One-line description:** The "later" half of generative objects: a noun mentioned in narration but never `spawn_object`'d gets promoted to a real object when a player tries to interact with it (e.g. examines/takes a thing the narration named). Today promotion is explicit-only (a verb's LLM output must emit `spawn_object`); narration is deliberately never auto-scanned.
- **Why deferred:** Fully spec'd as the documented next increment in the 2026-06-30 plan; the explicit-spawn path landed first as the irreducible, safe foundation. Player-touch promotion needs a resolution story for "which mentioned noun did they mean" that the grounded parser's in-scope-id model does not yet cover (the noun isn't an object yet, so it has no id).
- **Revisit criteria:** The explicit-spawn slice feels good in play AND players visibly reach for nouns the dialogue named but didn't spawn.
- **Origin:** plan the-output-of-this-greedy-hedgehog (§6, the hybrid's later half).

### object-lifecycle-clutter-gc
- **One-line description:** Salience / TTL / `last_accessed_at` pruning of generated objects so a long-played world doesn't accumulate clutter. The flags are already in place (`properties.generated_by`, an `ephemeral` flag, `last_accessed_at`) so the first GC pass needs no migration (mirrors `generated_assets.pinned`).
- **Why deferred:** No clutter exists yet; the generative slice just landed. GC is premature until a world accrues enough spawned objects to feel noisy.
- **Revisit criteria:** A played world accumulates enough ephemeral spawned things that rooms feel cluttered, OR a spawned-object count crosses a threshold worth measuring.
- **Origin:** plan the-output-of-this-greedy-hedgehog (§6, provenance + minimal lifecycle).

### deep-prototype-inheritance-and-per-object-verbs
- **Behavior-overrides slice: SHIPPED via the rule engine (2026-07-02, Zork turn).** Objects/rooms/worlds now declare ordered first-match RULES that dispatch BEFORE the engine handler (dobj -> iobj -> room -> world), which IS per-object verb behavior override in data (a bolt that turns, a bell whose ring is a ritual, a room that ejects you). What remains here is deeper: multi-level prototype chains and PYTHON-handler replacement (rules shadow the legacy handlers; they never replace them).
- **Per-object-verbs slice: SHIPPED (2026-07-01).** The playable-quest-loop turn added a `fixture` prototype (immovable: examine only) and lets authored objects declare per-object `verbs` in the world envelope (a case is `open`-able, a given key is `use`-able) and a spawn declare its own verbs (`spawn_object` verbs passthrough → the given case-key becomes use-able). The `properties.verbs` union with prototype defaults (`objects.verbs_for`) is now load-bearing, exercised by the Clockmaker's Loft quest. What REMAINS deferred is the multi-level part below.
- **One-line description (remaining):** Multi-level prototype chains (today inheritance is one level, shallow) + per-object *behavior overrides* beyond adding verbs (an object that overrides a verb's default HANDLER, not just its verb list). The MOO "generic object" pattern taken further.
- **Why deferred:** v1 has one handler per verb and one prototype level; the resolution ORDER (player→room→dobj→iobj) is already implemented so overrides slot in without re-architecting. Depth is only worth it once authored content wants a prototype that extends another prototype or an object that replaces a verb's behavior.
- **Revisit criteria:** Authored content needs an object that OVERRIDES a verb's default behavior (not just adds a verb), or a prototype that extends another prototype.
- **Origin:** plan the-output-of-this-greedy-hedgehog (§2); per-object-verbs slice shipped by plan this-plan-will-be-peppy-kay.

### user-authored-llm-driven-world-building-verbs
- **2026-09-26 (pivot):** grown rooms now join the story through dreams: an in-session Opus dream furnishes every room players grew (a description pass, residents, hooks) while keeping the planter's phrase verbatim (`live.furnish`, daydream/dream.py); growth boundaries also accept world `never_words`. The player-authored verb surface below remains deferred.
- **2026-07-02 narrowing (Dreamseeds spec, SHIPPED same day):** the effect-vocabulary half is built. The Dreamseeds increment implemented `spawn_room` + `link_exit` behind an ENGINE-authored verb (`plant`), gated by a quest-earned seed item whose Opus-authored `growth` boundaries constrain one local-LLM room composition; the kinds are per-verb opt-in (`effects.DEFAULT_KINDS` excludes them for every `allowed=None` caller). What remains in this entry is the player/admin-AUTHORED verb surface: a player authoring a verb whose LLM output builds rooms/objects, plus the authoring UI + safety story. (`destroy_object` SHIPPED 2026-07-02 in the Zork turn: rule-only kind, contents drop to the holder's location, combat's death path consumes it.)
- **One-line description (remaining):** A player/admin authors a verb whose LLM output BUILDS new rooms and objects (MOO-style).
- **Why deferred:** The authoring surface + the safety story for player-authored world-mutation are the work. Couples to `skills-authoring-and-security` and `player-authored-skills`.
- **Revisit criteria:** Dreamseeds ships and feels good in play (the effect vocabulary + boundary model exercised on an authored verb first); appetite to hand authoring to players.
- **Origin:** plan the-output-of-this-greedy-hedgehog (the explicit future direction; §5 future-prepared vocabulary); narrowed by the Dreamseeds spec 2026-07-02.

### per-npc-event-log-visibility-filtering — SUPERSEDED 2026-09-26 (pivot, criterion 7)
- **Superseded by:** NPC knowledge is data now: authored facts plus deed facts that name the player and spread NPC to NPC on an authored real-time schedule (`daydream/knowledge.py`); the dialogue prompt carries only what that NPC knows. Visibility of raw events no longer drives dialogue.
- **One-line description:** Filter which events an NPC "sees" so dialogue stays consistent (an NPC shouldn't reference an event that happened in another room or that it couldn't have witnessed). A research-suggested consistency guard for the LLM dialogue path.
- **Why deferred:** Single-player, two-NPC scale; the room-filtered broadcast already keeps cross-room events off a player's stream. NPC-side visibility matters once dialogue starts citing world events.
- **Revisit criteria:** Dialogue or memory starts surfacing events the NPC couldn't plausibly know about.
- **Origin:** plan the-output-of-this-greedy-hedgehog (out-of-scope list).

### parser-latency-and-throughput-tuning
- **One-line description:** Every free-text input is now one ~256-token parse call serialized behind the GPU arbiter with image-gen. Tune throughput (batching, a smaller/faster parse model, or speculative fast-paths) if it gates UX. The click-bypass + deterministic fast-path keep this off the hot path today.
- **Why deferred:** Single-stream decode is sub-second warm; clicks and exact words make no LLM call. No user-visible pressure yet. Ties to `calibrated-fp8-kv-scales` (a 7B fp8-KV recovery would help here too).
- **Eased (2026-07-02, plan let-s-do-a-small-compiled-umbrella):** the arbiter no longer serializes parse calls behind each other OR behind image-gen — LLM calls take shared slots (cap `DAYDREAM_LLM_CONCURRENCY`, default 3; vLLM `--max-num-seqs 4`) and a queued parse is admitted ahead of a queued render (text priority). So the "serialized behind image-gen" framing above is now false: a player's free-text parse under a concurrent render waits only for a shared slot, not the whole render. The remaining levers (batching, smaller/faster parse model, speculative fast-paths, fp8-KV) still stand if decode itself becomes the bottleneck under real multi-human load.
- **Traded (2026-09-26):** the model swap to Qwen3.5 9B (docs/model-evals/2026-09-26-bakeoff.md) bought quality with latency: an LLM parse went from ~0.6 s to ~1.0 s p50 and a `talk` from ~1.6 s to ~2.7 s. Measured, not naive: decode is bandwidth-bound (~53 tok/s per 5.3 GiB of weights on this card), CUDA graphs are already on, and FP8 KV buys nothing at ~1k-token prompts, so the remaining levers are shorter outputs (the 9B's dialogue averages ~108 tokens vs the old 83) and the fast-path.
- **Revisit criteria:** Natural-language input feels laggy in play (e.g. multiple humans, or NPC dialogue chains). First cheap lever: tighten `max_tokens` / brevity on dialogue and measure with `bin/game model-eval run --suites dialogue,parser`.
- **Origin:** plan the-output-of-this-greedy-hedgehog (parser latency/arbiter contention note).

## The Village of Lost Hours (captured 2026-09-26, agent playtest day)

Defects the four agent playtests raised that were not fixed in the turn (the
full disposition list is docs/playtests/2026-09-26/SUMMARY.md).

### reply-banks-select-dont-write
- **One-line description:** Opus authors a large reply bank per resident (small talk, each other resident, each place, each time of day, each open thread), and the local model selects the best authored line, writing something short only when nothing fits. The next step of docs/REFLEXES.md's "select, don't write".
- **Why deferred:** The turn shipped the cheap half (a free-form line naming a topic gets the authored answer) and the measurement (every local line is tagged; the dream digest lists them). A bank needs authoring scale and a selection prompt measured against improvisation.
- **Revisit criteria:** The next playtest or dream digests still show local lines as the weak spot (the first day: 15% of lines, nearly all the worst ones).
- **Origin:** docs/REFLEXES.md; playtest 2026-09-26 (chatterbox: "free-form talk is a coin flip").

### npc-memory-of-player-disclosures
- **2026-09-28 (beta rehearsal):** half of this landed another way. Residents now remember DREAMERS (`daydream/trace.py`: asked about a player by name they read the record, last seen and the deeds they know, and the prompt carries it), and a disclosure can come back as a dream's second-person topic for that player alone (dream-2026-09-28: Tace on the notebook). What still stands is the runtime half: a per-player "what they told me" list in the prompt without a dream in between.
- **One-line description:** Residents remember what a player told them about themself (name, a keepsake, "I keep bees") across sessions and days, not only the last few exchanges; the dialogue context gets a short per-player "what they told me" list.
- **Why deferred:** Keeping a line whole (the parser fix) and recent exchanges cover a session; durable disclosure memory needs extraction (deterministic or local) and a privacy story (a per-player, per-NPC note, never gossiped).
- **Revisit criteria:** Being remembered stays the lowest rubric score (2.5 on the first day).
- **Origin:** playtest 2026-09-26 (chatterbox, rule-breaker).

### thinking-indicator — CLOSED 2026-09-28 (shipped, beta rehearsal)
- **Closure:** `daydream/live.py` sends a transient `thinking` frame to the asker's page before the model is asked (dialogue and growth); the SPA shows "Tace considers..." / "the seed stirs" until the reply lands. Both beta rehearsal playtests had read the silence as a lost line.
- **One-line description:** While an improvised reply is coming (2 to 8 seconds), the SPA shows a quiet transient line ("Tace considers...") so a player knows it is on its way; a WS frame, never a logged event.
- **Why deferred:** Client plus one WS frame; the turn cut latency instead (one candidate when busy, no parser call for say/talk).
- **Revisit criteria:** The operator or a playtest still reads silence as a lost line.
- **Origin:** playtest 2026-09-26 (explorer, chatterbox).

### dusk-after-an-early-first-dusk
- **One-line description:** Mending the clock brings an early first dusk (so the first guest arrives), which means the real 18:00 dusk on day one passes with nothing marking it. Consider a small real-dusk beat (lanterns relit, lights on the Dusk Road) whenever dusk begins, even on a day whose dusk events already fired.
- **Why deferred:** The early dusk is the designed beat; the gap only shows on day one, for players still on at 18:00.
- **Revisit criteria:** A player notices again, or the director gains a per-phase ambient hook.
- **Origin:** playtest 2026-09-26 (explorer, rule-breaker).

### shared-thread-contention
- **2026-09-28 (beta rehearsal):** seen again with a household's pace: the gamer closed the prologue and Pim's nap within the hour, and the two who came after met two closed arcs. Eased, not fixed: Quill now gives every keeper a dreamseed of their own, three stray minutes a day are private, and letters, hand-overs and the record of dreamers give the latecomer something the fast player left rather than took. Still open: a per-player beat for a closed guest (a small thing of your own to do for it, with a keepsake), and `config.director.max_open_guests` 3 with a second arrival on a dusk an arc closed early (docs/playtests/2026-09-28-beta-rehearsal/SUMMARY.md, proposals).
- **One-line description:** Latecomers found both open threads finished by others ("both main threads were finished by others before I got to them"). More concurrent threads per day, per-player versions of small guest threads, or a director that brings the next guest sooner when a thread closes early.
- **Why deferred:** One day, four players at once, is a heavy load for a village designed around one or two coffee-break visitors; the director already brings a guest each dusk.
- **Revisit criteria:** The operator or a later playtest runs out of things to do on day one.
- **Origin:** playtest 2026-09-26 (rule-breaker).

### scenery-nouns
- **2026-09-28 (beta rehearsal):** the sharpest cases are now in GROWN rooms, whose things the local model names in prose but never spawns ("crumpled notes", a paperweight that cannot be read); a dream furnishes them (the second dream did), and the last words of a name now ground ("brass hand"). The general map is still the engine feature.
- **One-line description:** Details named in room text should answer when touched, in general: an engine scenery map on rooms (noun to short text, examine only, never listed), so every described detail can say something without cluttering "Around you".
- **Why deferred:** The world-data pass covered the details playtesters named with aliases and a few fixtures; a general map is an engine feature.
- **Known gaps (2026-09-26):** a bare "read a letter" in the post office asks which letter (a bare alias would collide with the rain-spotted letter); a four-word target ("scratch Tock behind the ears") is past the fast path's name grounding and goes to the model.
- **Revisit criteria:** More "You don't see the X here" on things the prose describes.
- **Origin:** playtest 2026-09-26 (explorer: "a prose detail that refuses to exist is the most deflating response").

## The household (captured 2026-09-28, beta rehearsal)

Proposals from docs/playtests/2026-09-28-beta-rehearsal/SUMMARY.md not built in the session.

### dusk-names-who-walked-through
- **One-line description:** A dusk ritual line in the square names the dreamers who were in the village today ("Two dreamers walked through today: Wren and Halloran"), from the input log: the evening player's honest substitute for a friends list, in Bell's voice.
- **Why deferred:** The margin's "also dreaming" and the Ledger's signature page cover the live and the durable case; this is the in-between, and it needs a storylet whose text the engine fills.
- **Revisit criteria:** A household member says they never know who was on that day.
- **Origin:** beta rehearsal 2026-09-28 (the veteran's "as a social game").

### leave-a-thing-for-someone
- **One-line description:** `give X to Fen for Wren` files a thing the way a letter is filed (private to the recipient, told on arrival, listed in threads), so a dead-drop in the dead-letter drawer carries a name.
- **Why deferred:** Letters cover the words; the veteran used the drawer for things and the world kept them but not the addressing. The post's machinery is there; it needs the parser form and Fen's line.
- **Revisit criteria:** The digest shows things left in the drawer for someone by name.
- **Origin:** beta rehearsal 2026-09-28 (the veteran's defect 13).

### per-dreamer-beat-for-a-closed-guest
- **One-line description:** After a guest arc closes, each dreamer who did not help can still do one small authored thing for it (sit with the kept nap, read to it), once, for a keepsake: the latecomer's share of a story the fast player finished.
- **Why deferred:** Content across six arcs; the day-two fixes give latecomers other things of their own first.
- **Revisit criteria:** The digest shows a household member meeting closed arcs two days running.
- **Origin:** beta rehearsal 2026-09-28 (the gamer closed both day-one arcs within the hour).

### room-prose-by-phase
- **One-line description:** Grown and furnished room descriptions are written once and read at every hour ("deepening blue" at breakfast); a per-phase sentence the engine appends from authored data, or a rule that furnish text names no hour.
- **Why deferred:** The runbook rule is in place; the engine half waits for a second offender.
- **Revisit criteria:** A player reads dusk at breakfast again.
- **Origin:** beta rehearsal 2026-09-28 (the critic's day two, defect 6).

### dozing-handover-of-village-things
- **One-line description:** `give X to <dreamer>` when that dreamer is dozing tucks the thing into their satchel; a village thing (one with a `home`) then waits on a rest that a closed page may never make. Refuse village things on the dozing branch (keepsakes only), once walkthrough players count as awake (today every walkthrough hand-over runs through the dozing branch, and `prologue-together` hands the gear that way).
- **Why deferred:** The refusal broke the arc contract in the review's fix cycle (CODEREVIEW.md 2026-09-29); `world rest-toon` and `account delete` send such a thing home meanwhile.
- **Revisit criteria:** A village thing goes missing into a dozing friend's satchel in play, or the walkthrough runner gains live sessions.
- **Origin:** codereview 2026-09-29 (the beta rehearsal's review).

### placeholders-over-player-text
- **One-line description:** `trace.expand_placeholders` fills `{dreamers_today}` in every narrated text, player text included (a letter's body, a dreamer's name); neutralise braces in player fields or expand authored strings only.
- **Why deferred:** No confidentiality impact (the clause is public); found by the security scan at the end of the beta rehearsal's review.
- **Revisit criteria:** A second placeholder is added, or a player pranks a letter with one.
- **Origin:** /security 2026-09-29b.

## Quality and tooling (GPU/ML follow-ups)

Captured from the comprehensive GPU/ML doc pass; full rationale per item lives in `docs/gpu-and-models.md` "Things we have not tried yet".

### watercolor-lora-ab
- **One-line description:** Try `ntc-ai/SDXL-LoRA-slider.watercolor` (slider-style; lets you dial intensity) and `lora-library/B-LoRA-watercolor` (decoupled style/content via B-LoRA technique) against the current `ostris/watercolor_style_lora_sdxl`. 12 MB each. Use `bin/game image-test "<prompt>" --lora <new>.safetensors` for the A/B.
- **Why deferred:** Current pick (`ostris`) produces visibly painterly output matching the WHIMSY anchor; no concrete complaint to fix. Surfaced as a revisit candidate in 6 prior proposals (2026-04 through 2026-05) without ever being selected — the audit-trail-substrate-landed gate alone has consistently failed to motivate the work, so the criterion is tightened to require an actual aesthetic complaint before resurfacing.
- **Revisit criteria:** A specific aesthetic complaint about current renders (e.g., "trees too sharp", "skies look uniform", "watercolor edges feel inconsistent across rooms") that we want to address by trying a different LoRA. The audit-trail substrate is in tree (`bin/game test human` qpeek output to `docs/pretty/aesthetic-samples/`) and ready to capture before/after comparisons whenever this entry activates.
- **Revisit criteria (now MET, 2026-07-01):** `forge-render-legibility` below is a concrete complaint (the forge doesn't read as a forge; hard objects don't render under `ostris`), which is exactly the trigger this entry was waiting for. A LoRA A/B is one candidate fix for that item.
- **Origin:** docs/gpu-and-models.md (Image-gen alternatives we considered and did not test); revisit-criteria refresh 2026-05-07 (was double-gated; tightened to single complaint-driven gate after 6 declines).

### forge-render-legibility
- **One-line description:** "The Quiet Forge" doesn't render as a blacksmith's forge. Across five seed variants (2026-07-01, via `bin/game image-test` + agent review), SDXL + the `ostris` watercolor LoRA turned "iron anvil / leather bellows / forge" into soft vessels, kilns, pots, and cottages in warm tones — cozy and on-palette, but never a legible anvil or forge. The loose watercolor style actively fights the crisp silhouette a recognizable hard object needs. This is the general "hard objects don't render legibly under a loose style LoRA" limit, surfaced on the forge.
- **Why deferred:** Out of scope for the verification-infrastructure turn (which was about tests, not fixing one room's image). Candidate fixes, none free: (a) reframe the room to what renders well (a warm rustic workshop / hearth-nook — cheapest, drops the blacksmith concept); (b) pre-bake a picked forge image as a pinned `r-forge` asset (keeps the concept, no global change); (c) lower the LoRA strength or A/B a different LoRA per `watercolor-lora-ab` (most likely to yield a real anvil, but a GLOBAL workflow change that re-baselines every room). Which one is a product/aesthetic call for the operator.
- **Revisit criteria:** The operator picks a direction (reframe / pre-bake / LoRA A/B), OR a second authored room needs a hard object (tool, machine, sign) and hits the same wall — at which point the general fix is worth more than the per-room workaround.
- **Coordinate with:** `watercolor-lora-ab` (a LoRA swap is fix option c); the `image_forge.golden.json` perceptual baseline (re-ratify after any fix).
- **Origin:** 2026-07-01 forge-render agent-review loop (this turn), flagged per the CLAUDE.md "flag local limits at design time" process rule.

### calibrated-fp8-kv-scales
- **One-line description:** Run vLLM's FP8 calibration pass over a representative dataset to produce per-channel FP8 KV scales for `Qwen/Qwen2.5-7B-Instruct-AWQ`, then re-enable `--kv-cache-dtype fp8_e4m3` in `bin/game cmd_vllm_up`. Recovers localreview's documented +58% decode TPS / ~0.9 GB freed VRAM win that was lost when we rejected naive fp8_e4m3 on the 7B (model looped garbage tokens).
- **Why deferred:** Real engineering work (calibration dataset, vLLM scale-export pipeline, validation run). Only worth it if LLM throughput becomes a bottleneck. Today single-stream decode latency is sub-second warm; no user-visible pressure.
- **Revisit criteria:** LLM round-trip latency starts gating UX (e.g., NPC dialogue chains feel laggy with multiple humans connected); OR vLLM ships an official calibration recipe for Qwen 2.5 family that drops the engineering cost meaningfully.
- **Largely moot (2026-09-26):** the shipped model is now Qwen3.5 9B, and naive `fp8_e4m3` KV on it does NOT break JSON (measured with `bin/game model-eval`), so no calibration is needed for correctness. But it bought no latency (weights, not KV, dominate bandwidth at ~1k-token prompts) and its startup workspace fails to boot beside a resident SDXL at 0.45. Reopen only if prompts grow to multi-thousand tokens.
- **Origin:** docs/gpu-and-models.md (The fp8-KV story, condition #2)

### llm-14b-if-sdxl-offloaded
- **One-line description:** Qwen3 14B AWQ tied the shipped Qwen3.5 9B on blind-graded prose (+0.18, CI -0.07 to 0.43) and was the only model with a perfect parser (48/48), but it needs a 0.60 vLLM slice. Beside a resident SDXL that left ~0.65 GB free during a portrait render. If ComfyUI stops keeping SDXL resident (offload to CPU RAM between renders; renders are cached and infrequent), the ~6 GB it frees makes the 14B fit with margin.
- **Why deferred:** The 9B already captures most of the quality gain inside the unchanged VRAM envelope; offloading SDXL costs a cold-load on every render and changes the arbiter's memory story.
- **Revisit criteria:** Parser grounding misses show up in play that the 14B would have caught, OR a render-latency budget is found that tolerates an SDXL reload (measure with `bin/game image-test` under `--lowvram`/offload).
- **Origin:** docs/model-evals/2026-09-26-bakeoff.md.

### gemma4-12b-brevity
- **One-line description:** Gemma 4 12B it (official QAT w4a16) wrote the best-graded rooms and object descriptions in the 2026-09-26 bake-off, but broke the two-sentence dialogue contract on a third of replies, ran ~1.7x the 9B's latency, and needs a ~0.68 slice. A per-surface split (Gemma for growth/examine, which are rare and not latency-critical) would need two resident LLMs, which this card can't hold beside SDXL.
- **Why deferred:** Doesn't fit the VRAM budget as a second model; as the only model it is too slow and too verbose for dialogue.
- **Revisit criteria:** A smaller Gemma 4 variant with the same prose quality, OR the SDXL-offload path above frees enough VRAM to reconsider.
- **Origin:** docs/model-evals/2026-09-26-bakeoff.md.

## Test architecture follow-ups

Captured from the test-architecture landing (2026-04-23); scaffolding for these is in place, the work itself is deferred until the triggering signal arrives. See `TESTING.md` for the full architecture and philosophy.

### archive-restore-roundtrip-test — CLOSED 2026-07-06 (shipped, v1.0 turn groundwork)
- **One-line description:** Add a `tier_long` test that archives a world via `bin/game world archive`, deletes it, restores from the archive, then diffs the restored DB + cache against the pre-archive state. Goes deeper than the current `test_admin.py` unit coverage (belt-and-suspenders on the E2E flow).
- **Why deferred:** `test_admin.py` already covers archive + restore individually with the round-trip construct in `test_restore_round_trip`; a dedicated drift-tier end-to-end would be redundant until we have multi-world state + a non-trivial cache to diff.
- **Revisit criteria:** First Opus-bootstrapped world worth keeping; OR first operator incident where archive/restore loses state and the existing unit coverage didn't catch it.
- **Origin:** test architecture plan (2026-04-23)
- **Closure:** `tests/test_admin_roundtrip.py` (tier_long) archives → cascade-deletes → restores and diffs the full world fingerprint (rows + cache files); ran green in the 2026-07-07 GPU batch.

### security-tests-tier — CLOSED 2026-07-07 (shipped, v1.0 turn)
- **One-line description:** Dedicated `tests/security/` directory covering banned-word filter regression, session-cookie tamper detection, AccessMiddleware fuzz (invalid CGNAT edge cases), `daydream/admin.py` path-traversal edge cases beyond the current CVE-2007-4559 coverage. Marker mix: some `tier_short`, some `tier_medium`.
- **Why deferred:** Couples to `safety-baseline-v1` (no LLM-driven state mutation in v0 means no banned-word surface to regress against). AccessMiddleware fuzz is lower-priority since the middleware is heavily tested already.
- **Revisit criteria:** `data-skills-cli` + `safety-baseline-v1` land; OR a security-review pass surfaces a class of risk not covered today.
- **Origin:** test architecture plan (2026-04-23)
- **Closure:** `tests/security/` exists with the regen kill-switch gate, delete grace window, loopback-only swap (groundwork commits) and the benign-refusal corpus (`test_benign_refusals.py`, criterion 8). AccessMiddleware fuzz + cookie tamper remain covered by their existing suites (`test_access_middleware.py`, `test_auth.py`).

### load-test-harness
- **One-line description:** Add a `tier_long` capacity test: 10 simulated bots holding WS connections for 10 minutes, sending a modest input cadence, assert no OOM / no arbiter deadlock / bounded room-image queue depth. Under `tests/load/` to keep it distinct from drift.
- **Why deferred:** v0 has 1 user per world; capacity is a v2 concern. Arbiter smoke already exercises serialization; this is the multi-user extension.
- **Revisit criteria:** `multi-user-shared-world` lands; OR oncall starts seeing WS queue backpressure in real usage.
- **Origin:** test architecture plan (2026-04-23)

### ci-pipeline — CLOSED 2026-07-06 (shipped, v1.0 turn groundwork)
- **One-line description:** Add `.github/workflows/test.yml` that runs `bin/game test ci` on push / PR. Skips `tier_long` unless the runner has a GPU (AWS EC2 G-family or a self-hosted runner).
- **Why deferred:** Single-dev box today; `bin/game test ci` is run locally. CI earns its keep when a second contributor lands or when we need to enforce green-on-push across branches.
- **Revisit criteria:** Second contributor joins; OR cross-branch churn makes local-only verification feel unsafe.
- **Origin:** test architecture plan (2026-04-23)
- **Closure:** `.github/workflows/test.yml` runs lint + the GPU-free medium tier on Python 3.10 and 3.12 on push/PR (groundwork commit acbee0b).

### mypy-gate
- **One-line description:** Add `[tool.mypy]` to `pyproject.toml` with `strict = true` and include a mypy pass in `tier_short`. Probably needs typing backfill across `daydream/` first.
- **Why deferred:** The typing work itself is weeks. Ruff B + UP already catches ~80% of what mypy would on this codebase today. Low marginal signal per hour invested.
- **Revisit criteria:** A typing-related bug slips past ruff and causes real damage; OR a contributor with typing momentum lands.
- **Origin:** test architecture plan (2026-04-23)

### staging-probes
- **One-line description:** Implement the `DAYDREAM_TARGET=staging` tier_medium probes. Today the knob is scaffolded (`config.target()` + `_resolve_target` fixture in `tests/conftest.py`) but all tier_medium tests skip with "staging not yet wired" under that target. The real probes would hit `/healthz`, login flow, WS handshake against a deployed staging URL — read-safe, no DB mutation.
- **Why deferred:** No staging environment yet.
- **Revisit criteria:** Staging env exists; `multi-env-layout` lands.
- **Origin:** test architecture plan (2026-04-23)

### prod-verify-probes
- **One-line description:** Implement the `DAYDREAM_TARGET=prod_verify` tier_long probes. Read-only; hits health, auth form, public asset endpoints to confirm a deploy is live after a push. Never writes DB state.
- **Why deferred:** Prod is one box today; there is no "deploy" to verify beyond a local restart.
- **Revisit criteria:** Multi-box prod deploy lands (whether as Cloudflare Workers per the tech-sketch plan or a second physical box).
- **Origin:** test architecture plan (2026-04-23)

### drift-alarms
- **One-line description:** When a baseline diff lands on main, auto-open a Claude Code session (via the `schedule` skill or a push-notification hook) with the diff as context. Keeps the "baseline changed — why?" review loop warm without relying on a human noticing the commit.
- **Why deferred:** Today there's one contributor; every baseline update passes through that person's eyes by construction. The alarm becomes valuable when ratified drift happens on branches that the author doesn't review.
- **Revisit criteria:** Second contributor joins AND starts ratifying baselines independently.
- **Origin:** test architecture plan (2026-04-23)

### latency-regression-corpus
- **One-line description:** Tighten the per-call latency windows in `tests/drift/*.py` as multi-run trend data accumulates. Today wall-clock fields are recorded to `.latest.json` but not gated (too noisy on a single sample). Once we have ~10 same-config runs, derive p50 + p95 from the trend and set windows at (p50 / 2, p95 * 2).
- **Why deferred:** Need samples. Until then, recorded values are the substrate, not the contract.
- **Revisit criteria:** 10+ `bin/game test long` runs in `.latest.json` history (moved to a branch-local scratch dir since `.latest.json` is gitignored — maybe add a `tests/baselines/history/` append-only log as part of this work); OR a regression in wall-clock that eyeballs caught but no probe alarmed on.
- **Origin:** test architecture plan (2026-04-23)

## Open questions

### player-authored-skills
- **One-line description:** Open data-skill authoring to non-admin players (currently admin-only via CLI in v1, admin-only via web UI in v2). Plan explicitly defers the question of review workflow gating: dry-run sandbox + admin approval queue, vs. trusted-friend flag, vs. full auto-publish with audit/undo as the safety net.
- **Why deferred:** Plan punts to v2 because the security surface is too large to design without first learning what skills feel good when admin-authored. Friend-scope security stops being load-bearing the moment a player can author LLM prompts that any other player triggers.
- **Revisit criteria:** skills-authoring-and-security shipped (admin web UI + six-layer pipeline both done); clear desire to expand authoring beyond admin (a player asks "can I make a skill?").
- **Origin:** plan let-s-design-a-fairly-giggly-narwhal

### creative-finetune-json-fluent-base
- **One-line description:** Re-attempt the voice-quality A/B with a creative-writing finetune of a JSON-fluent base (e.g., Qwen 2.5 7B/14B AWQ, Llama 3.x AWQ). Drop-in `DAYDREAM_LLM_MODEL` / `DAYDREAM_VLLM_MODEL` swap; same harness path (`bin/game voice-samples`); compare against `docs/pretty/voice-samples/2026-05-06-qwen2.5-7b-instruct-awq.md`.
- **Why deferred:** As of 2026-05-07 no published creative-writing finetune of a JSON-fluent base is known to fit our 20 GB VRAM budget. Mistral Nemo 12B Q4 was the closest viable candidate and failed the data-skill pipeline (base-arch + Q4 + prompt-shape interaction; see `docs/gpu-and-models.md` "Things we tried and rejected"). A Qwen-family or Llama-family creative-writing finetune at AWQ or fp16 (where it fits) would close the original 2026-04-24 question.
- **Revisit criteria:** A creative-writing finetune of a JSON-fluent base (Qwen 2.5 7B/14B, Llama 3.x 7B/8B, or comparable) publishes on HF AND fits under `--gpu-memory-utilization 0.45-0.7` at AWQ or fp16; OR voice quality becomes a UX-gating concern that justifies the search effort.
- **Origin:** spec 2026-05-07

### free-form-prose-pipeline
- **One-line description:** Daydream pipeline change in `daydream/skills/data.py` to accept free-form prose responses from the LLM and post-parse for `narrate` effects, instead of requiring strict-JSON `response_format`. Would enable prose-continuation finetunes (RP-Ink and similar) that don't fit the current pipeline. Touches `acompletion_json` call site, safety layers (`safety.parse_refusal`, `safety.first_banned`, `_emit_narrate` fallbacks), and the effect-allowlist contract.
- **Why deferred:** The Mistral Nemo experiments (2026-05-06/05-07) showed strict-JSON breaks prose-continuation finetunes, but the current pipeline depends on `json.loads` validation + the effect-allowlist for safety. A pipeline change is architectural and touches multiple components; defer until a specific finetune is worth the cost. The change would also need a new safety story for free-form text (no banned-word output filter today operates on raw LLM text before structured parsing).
- **Revisit criteria:** A specific creative-writing finetune emerges that's worth using AND only works with free-form prose output (not JSON); OR the v2 `skills-authoring-and-security` work picks up this question as part of a broader pipeline refactor.
- **Origin:** spec 2026-05-07

### mistral-7b-instruct-fp16-ab
- **One-line description:** A/B Mistral 7B Instruct at fp16 against the current Qwen 2.5 7B Instruct AWQ for narration voice. Mistral 7B fp16 is ~14 GB resident (fits at `--gpu-memory-utilization 0.7` with ComfyUI down); separates the quantization axis from the architecture axis after the 12B Q4 Nemo experiments came up inconclusive. Same harness path (`bin/game voice-samples`); compare against `docs/pretty/voice-samples/2026-05-06-qwen2.5-7b-instruct-awq.md`.
- **Why deferred:** Diminishing returns after 3 turns of voice-bench work. The Nemo Q4 result already shrunk the answer space; a 7B Instruct A/B would close a specific axis question (is the failure quant or arch?) rather than answer the original "does a creative-writing finetune flex?" question. Worth doing only if a future decision needs that closure.
- **Revisit criteria:** Operator wants definitive closure on Mistral arch suitability before authoring a different LLM-pipeline change; OR a Mistral 7B creative-writing finetune publishes on HF (which would make the Mistral-vs-Qwen axis question load-bearing).
- **Origin:** spec 2026-05-07

## UI & presentation (captured 2026-07-01 Reading Room turn)

### regen-ui-gate — CLOSED 2026-07-06 (shipped, v1.0 turn groundwork)
- **One-line description:** The dev room-image repaint UI (`daydream/api/rooms.py` + the plate-tools/dialog in `web/`) has no switch to disable it; any authed (tailnet) session can repaint shared room art. Add a `DAYDREAM_REGEN_UI` flag (default on in dev) that both the endpoints (404/503 when off) and the SPA (hide the plate-tools) honor, so "turn it off for real players once live" is a config flip rather than a code edit. Today the only off-switch is removing the router registration in `server.py`.
- **Why deferred:** The 2026-07-02 turn shipped the feature ungated by explicit request ("no need to guard against weird stuff, we'll probably turn this off for users once the game is live"). Fine under the current single-box friend-scope trust model; the gate matters when a shared preview/prod deployment appears.
- **Revisit criteria:** A shared preview/prod deployment, OR the feature graduates from dev-only, OR real (non-friend) users get access.
- **Origin:** plan let-s-do-a-small-compiled-umbrella (increment 5); codereview NOTE 2026-07-02.
- **Closure:** `DAYDREAM_REGEN_UI` (default on) gates the endpoints (404 when off), rides the snapshot `features` block, and the SPA registers plate tools only when true (groundwork commit 7708993; tests/security/test_regen_gate.py).

### delete-slot-grace-window — CLOSED 2026-07-06 (shipped, v1.0 turn groundwork)
- **One-line description:** `delete_slot` (irreversible: drops carried items, wipes memories) is gated only by instantaneous WS liveness (`_require_slot_actionable` → `is_session_live`), so a transient socket drop (laptop sleep, network blip, background-tab throttle) briefly marks a live player's toon "abandoned" and lets another session permanently delete it. Kick has the same gate but is recoverable, so it's fine; delete is not. Options: a short "recently-live" grace window keyed on last-seen, or restrict delete to the controlling session only (never another's, even if currently dead-WS) while leaving kick lenient.
- **Why deferred:** By-design per the shipped guard (delete of an abandoned toon is allowed, mirroring claim's dead-session takeover), and inside the friend-scope trust model where grief isn't the threat. The sharp edge is only that delete is irreversible.
- **Revisit criteria:** Any report of a lost toon after a reconnect, OR access widens beyond trusted friends, OR a soft-delete/undo lands (which would neutralize the irreversibility).
- **Origin:** plan let-s-do-a-small-compiled-umbrella (increment 4); codereview NOTE 2026-07-02.
- **Closure:** delete requires the controller to have been offline ≥120 s (`is_session_recently_live`), so a transient drop can't open a delete window; kick stays lenient by design (groundwork commit 7708993; tests/security/test_delete_grace.py).

### snapshot-enrichments-for-reading-room
- **One-line description:** Three small server-side snapshot enrichments the client-only Reading Room turn deliberately skipped: item description/provenance in the snapshot's `_object_card` so keepsake specimen cards read richer than name + generic tag; exit destination TITLES so the compass can say "up — the Clockmaker's Loft" without leaking room ids; a server-derived objective string for the "a small errand" marginalia group.
- **Why deferred:** The Reading Room spec was explicitly client-only (no server/world change, no WORLD_VERSION bump); each of these is a deliberate server change weighed against that stance.
- **Revisit criteria:** The next server-touching increment lands (cheap to ride along), or playtest feedback that the compass/keepsakes feel thin.
- **Origin:** SPEC proposal block 2026-07-01 (Reading Room turn), preserved here when the Dreamseeds spec replaced that block.
- **2026-09-26 (pivot):** snapshots gained the village time, per-NPC ask-about topics, the Book of Stray Minutes, and the once-only while-you-slept note; exit destination titles and a server-derived errand string are still open.
- **Partial (2026-07-07, v1.0 turn):** the item-detail slice shipped — `_object_card` carries `detail` (examined/authored text) and the keepsake cards render it. Exit destination titles and the errand string remain open (see docs/ROADMAP.md v1.x).

## Closed

## Zork turn deferrals (captured 2026-07-02)

**2026-09-26: Zork is frozen** (the pivot to The Village of Lost Hours). Zork I stays in tier_medium as the engine's regression net (its walkthrough still ends at 350); no edits under `worlds/zork1*` or its walkthrough. The entries below are parked, not abandoned; the retell layer is not enabled for the Lost Hours world.

### zork-oracle-ratification-run — DONE 2026-07-07
- **Outcome:** GREEN against real Zork I (dfrotz 2.44 built from the on-box
  frotz source; story R119/880429 compiled from the design-time ZIL tree;
  `DAYDREAM_ZORK_ORACLE_SEED=4`, one segment needed 2 attempts). The
  "possibly small accommodations on first contact" prediction understated
  it: first contact taught the harness zero-cost save/restore-bracketed
  probes, disarm-recovery combat, status-line filtering, and per-segment
  bounded retry (a 400-seed sweep proved a single straight-line RNG stream
  can never thread the wandering thief — retry against interpreter RNG,
  which restore deliberately does not rewind, asks the honest question:
  CAN the real game follow this walkthrough and agree at every
  checkpoint). The walkthrough itself absorbed six real-game lessons:
  carry-weight limits (sword dropped at the altar; lamp-only coffin and
  reservoir trips), wound-shrunk capacity (kit shed in the den before the
  loot takes), the ~8-held-items cap (kit parked at Round Room across the
  dam trip), dynamic trophy-case scoring (no egg case-parking), the
  thief's floor-item shell game (key/grating choreography cut; kit carried
  to the ceremony), and the four-dig scarab (our world was authored one
  dig short — now fixed to the original's count).
- **Origin:** SPEC 2026-07-02 criterion 14, checked off 2026-07-07.

### zork-fidelity-relaxations-second-pass
- **One-line description:** Small documented divergences from the original, each noted in its region-file comment, revisitable as a batch: the Loud Room garbles no commands (the bar take refuses instead); drop-a-weapon-while-aboard and attack-from-the-boat do not puncture (boarding and stowing do); River 5 refuses the falls instead of killing; the maintenance-room flood blocks entry but never drowns a lingerer; the reservoir refill cannot drown a wader; the bat's drop room is fixed rather than random; the skeleton's curse is a bark without the item banishment; the machine ignores non-coal contents rather than slagging them; the thief stops stealing once confronted in his den.
- **Why deferred:** None is load-bearing for the 350 or the oracle's checkpoint comparison; each was cut consciously to keep rules/data simple (most would be one more rule or one engine hook).
- **Revisit criteria:** The operator playtest or the oracle run trips over one of them, or a fidelity-polish pass gets appetite.
- **Origin:** region-file comments, Zork turn 2026-07-02.

### walkthrough-turn-alignment-brittleness
- **One-line description:** Combat and daemon rolls key on (rng_seed, turn, purpose) with turn = command index - 1, so ANY dataset edit upstream of the thief fight shifts its counter-roll turns; the fight is currently aligned to the safe 103-107 window with one authored filler (`examine thief`). A future dataset edit needs the roll table re-derived (the two-model union: death turns 102/107/114/117/118 at 8%). Consider a small tool that recomputes safe windows, or an authored `counter_kill_chance: 0` on the thief if the brittleness bites repeatedly.
- **Why deferred:** The dataset is stable and green; the brittleness only matters when someone edits the walkthrough's first ~100 commands.
- **Revisit criteria:** Any walkthrough restructure, or a second alignment hunt.
- **Origin:** swap rehearsal 2026-07-02 (the turn-key discovery).

### retell-rung-revisit
- **One-line description:** The retell layer shipped at the SCOPED rung (authored line first, LLM varies repeat tellings; plain-words prompt). The full-ON rung (first tellings too) reopens if a stronger local model lands or the prompt improves further; the probe (`tests/drift/test_retell_probe.py`) plus in-session grading is the ladder's gate either way. Also unexplored: retell for fuse/daemon narrations (sync path today) and per-player retell variety (currently one shared telling stream per world).
- **Why deferred:** The 7B's thesaurus-itis damaged the dry register on first tellings; scoped is the honest rung (flag-local-limits pact).
- **Revisit criteria:** Model bump on the box, or playtest reports the echoes reading better than the firsts.
- **Origin:** retell ratification commit 2026-07-02.

### zork-postgame-and-polish
- **One-line description:** Post-win play is unshaped: the map appears and the barrow accepts the winner, but there is no "inside the barrow" beat (the original ends there advertising the sequel), diagnose is minimal, and the deaths counter surfaces nowhere in the UI. Also unshipped: OOPS, save/restore verbs (R5: operator snapshots are the save), spirit-mode afterlife (pre-registered skip).
- **Why deferred:** Out of the 16-criterion contract by design; the win records and play continues cleanly, which is what the spec asked.
- **Revisit criteria:** Operator playtest reaches the barrow and wants a beat there; or Zork II appetite (same platform, new envelope).
- **Origin:** SPEC 2026-07-02 out-of-scope list + turn-close sweep.

Resolved and rejected entries, compressed to a line each; full narratives live in git history (this file, pre-2026-07-02) and the linked plans.

- **two-object-verbs — done 2026-07-01.** `give`/`use` (+ state-gated `open`, `read`) shipped as the playable-quest-loop turn; exercised by the Clockmaker's Loft quest, guarded by `tests/test_quest_playthrough.py`.
- **claude-vision-quality-gate — done, reframed 2026-07-01.** The aesthetic critic is the Claude Code agent Reading renders against `WHIMSY.md` in-session; the env-gated litellm vision gate was removed for needing an API key (generation policy). Human escalation: `qpeek` or in-game.
- **toon-delete-drops-items — done 2026-06-30.** `toons.delete_slot` reparents carried things to the toon's room before deletion; belongings persist in the world.
- **forge-render-drift-anchor — done 2026-06-30, golden pending re-ratification.** The forge dHash anchor + golden shipped; NOTE (2026-07-01): the render was later judged NOT to read as a forge (see `forge-render-legibility`, still open), so the golden gets re-ratified after that fix.
- **present-player-drift-cadence-guard — rejected 2026-06-30.** Redundant: the busy-cadence magnitude is already pinned in tier_short (`test_compute_next_interval_busy_default`). Kept so a future design pass does not re-propose it.
- **voice-baseline-add-model-helper — done 2026-06-30.** `tests/test_voice_baseline.py` derives its parametrization from a glob + `baseline-class` markers; new tracked baselines auto-extend the regression with no code edit.

## Security review follow-ups (captured 2026-09-29)

What the security review of 2026-09-29 left open in the repo itself, for any
instance. Items that concern one deployment's own account, zone or box are
kept with that deployment, not here.

### shared-origin-with-the-pages-site
- **One-line description:** An instance served under a path of a shared host (the Worker's route, e.g. `/daydream*`) shares its origin with whatever else that host serves: any script on that origin can use a signed-in player's session and register a service worker over the instance's path. Guard the rest of the host with a strict CSP on every page it serves (`script-src 'none'` or `'self'`, `worker-src 'none'`, `frame-ancestors 'none'`), and keep other Workers off the host's routes. The structural fix is the instance on its own hostname.
- **Why deferred:** The rest of a shared host lies outside this repo; an own hostname is a product decision (cookies, the edge flag, CLOUDFLARE-SETUP.md).
- **Revisit criteria:** Before anything else on the host gains a script or a third-party embed; or at the next edge rework.
- **Origin:** security review 2026-09-29 (L2).

### sign-in-rate-rule-covers-every-post
- **One-line description:** The Worker refuses encoded slashes, so a spelling of a path cannot slip a POST past a WAF rule written for the login and invite paths. A fork's rate rule may cover every POST under its base instead (players rarely POST; commands ride the socket), which makes the rule independent of how a path is spelled.
- **Why deferred:** A dashboard setting, per instance; the Worker's refusal already closes the known gap.
- **Revisit criteria:** When a rate rule is next touched, or if another path trick turns up.
- **Origin:** security review 2026-09-29 (L4).

### sleeping-page-polls-gently
- **One-line description:** A tab left open while the village sleeps retries every 30 s (a socket and `api/me`), and the asleep page polls `edge/status` every 60 s; a dozen forgotten tabs over a long sleep spend a large share of the free quota. Back off to 5-10 minutes once the answer is "planned sleep", with one `edge/status` request instead of two.
- **Why deferred:** Small client change; not urgent at today's scale.
- **Revisit criteria:** Before a multi-day sleep with friends' tabs open.
- **Origin:** security review 2026-09-29 (info).

### prod-supply-chain-pins
- **One-line description:** Pin hashes in `ops/requirements-prod.lock` (`--require-hashes --only-binary=:all:`), pin ComfyUI to a commit and refresh it deliberately (the checkout is April's), and consider replacing litellm (a very large dependency used only to call a local endpoint) with plain httpx. The keepsakes and offsite timers run the working tree's `bin/game` rather than a tested release; point them at `/srv/daydream/current`.
- **Why deferred:** Each is a small change with its own test run; none is exploitable on its own.
- **Revisit criteria:** At the next dependency upgrade.
- **Origin:** security review 2026-09-29 (info).

### username-lockout-softer
- **One-line description:** Five wrong guesses from anywhere lock a known username out of password sign-in for fifteen minutes (existing sessions are unaffected). Count a username's failures only from addresses without a recent success, or give each address its own softer budget.
- **Why deferred:** Accepted: the window is short, sessions last thirty days, and the per-username cap is what stops guessing.
- **Revisit criteria:** A friend locked out by someone else.
- **Origin:** security review 2026-09-29 (L6).

### agent-sessions-without-root
- **One-line description:** The operator's Claude Code session runs as a user in the docker group (root-equivalent) and holds the box's credentials, while player text reaches its context. The structural fix is agent sessions under a separate OS user with no docker group, no credentials beyond what prod work needs, and an egress allowlist, so nothing depends on the model's judgement or on pattern-matched permission rules. A lighter step first: run dreams and playtests (the sessions that read player text) in a session without the prod grant, and hand the committed patch to a short prod session.
- **Why deferred:** A box-level change (users, groups, where the credentials live) and a workflow change; the guard hook, the player-text policy and the scan cover the near term.
- **Revisit criteria:** Before more than a handful of players, or the first flagged text-scan item.
- **Origin:** security review 2026-09-29 (H1).

### engines-under-their-own-user
- **One-line description:** vLLM and ComfyUI listen unauthenticated on loopback and run as the operator, and the prod service can reach both. Run the engines as their own system user with no home, no docker group and write access only to their model and output directories, so a foothold in the prod service cannot become the operator through an engine.
- **Why deferred:** Accepted risk since going live (SECURITY.md); ComfyUI now runs without its API nodes, and the prod venv is sealed.
- **Revisit criteria:** The next time the engine lifecycle (`bin/game vllm-up|comfyui-up`) is reworked.
- **Origin:** security review 2026-09-29 (L7).

### agent-guard-credential-mentions
- **One-line description:** `tools/agent_guard.py` denies any command that names a credential path, including a commit message, a grep pattern or a heredoc that merely mentions one. Denying only path-shaped words and asking on bare mentions would cut the friction, but it loosens a control on the agent's own actions, so it is the operator's decision.
- **Why deferred:** Kept strict on purpose (CODEREVIEW 2026-09-29c); the friction is small.
- **Revisit criteria:** The guard blocks routine work often enough to matter.
- **Origin:** codereview 2026-09-29c.

### prod-check-probes-the-new-edge-rules
- **One-line description:** `bin/game prod check` verifies the edge's redirects and locks, but not the two rules added on 2026-09-29: plain http under the base answers 301 to https, and an encoded slash under the base answers 400. Add both probes so a Worker regression shows up in the check.
- **Why deferred:** Small; verified by hand at deploy time.
- **Revisit criteria:** The next change to `edge/src/worker.js` or `daydream/prodcheck.py`.
- **Origin:** security review 2026-09-29 (M1, L4).

### topic-chips-link-in-the-text
- **One-line description:** When a line names something a resident can be asked about, the chip appears (and glows), but nothing in the line itself marks the word. Morrowind hyperlinked a topic where it was first mentioned; a quiet link style for askable subjects in a resident's answer would tie "who is Bell?" to the sentence that raised it. Related: chips reorder on the next snapshot after an ask, under a finger that may be about to tap again (settle the order per visit instead).
- **Why deferred:** The chip rule shipped first (playtest 2026-09-29); this wants a second link style that does not blur with the in-scope object links.
- **Revisit criteria:** A playtest where a player misses a newly opened topic.
- **Origin:** playtest 2026-09-29 and its research (Morrowind, Blue Lacuna).

### quiet-verbs-for-secret-affordances
- **One-line description:** The verb bar offers a world verb whenever something in view takes it, which is a fair nudge for a windable clock but would give away a puzzle whose answer is an unusual action on a hidden thing. An authored per-object `quiet_verbs` list (answered when typed, never a button) would keep such secrets; room-rule verbs are already never shown.
- **Why deferred:** No shipped content needs it yet (DESIGN.md "What the page offers" records the rule).
- **Revisit criteria:** The first puzzle whose answer is a verb on a thing in view.
- **Origin:** playtest 2026-09-29.

### credentials-an-agent-session-holds
- **One-line description:** An operator's Claude Code session that reads player text (dream digests, `play` output, letters, dreamer names) should hold only credentials that are worth little if they leak. Give it a fine-grained token limited to the repos it pushes, with no gist or key-admin scope and an expiry; an SSH key with a passphrase held in an agent, or per-repo deploy keys; and an IP-restricted Cloudflare token (CLOUDFLARE-SETUP.md already asks for one). Keep interpreters and `gh`/`git` out of any global allow list that runs them without review, and remember that repos holding shared agent tooling (skills, hooks) are the most valuable push target of all, since a change there runs inside every future session.
- **Why deferred:** Account and box settings, outside the repo; the guard hook, the player-text policy and the scan cover the near term.
- **Revisit criteria:** Now, for any live instance; and whenever a new credential is placed on the box.
- **Origin:** security review 2026-09-29 (H1).

## Carried from specs

### launch-demonstrations
- **One-line description:** Demonstrate the nine going-live criteria that were built but not yet shown end to end: prod sandboxed as its own user (9), pinned and reversible releases including a rollback drill (10), dev and prod coexisting (11), each content path reaching prod (12), a backup restored into dev (13), the village sleeping visibly (15), keepsakes while asleep (16), the launch with a first friend's full flow from a phone (17), and an offsite backup restored (22). Full text: SPEC.md at d121a16.
- **Why deferred:** The 2026-09-29 spec turned to play quality; these are operational drills, most of whose machinery already runs in prod.
- **Revisit criteria:** Before inviting the second wave of friends, or at the next maintenance window, or when an incident exercises one of these paths.
- **Origin:** spec 2026-09-27 (Going live), closed 14/23 on 2026-09-29.

### prompt-economy-remaining-surfaces
- **One-line description:** Apply "Prompting the reflexes" (docs/REFLEXES.md) to the surfaces the 2026-09-30 audit found: `model_eval.suite_growth` hand-copies the growth call (no `GROWTH_TEMPERATURE`, no second try, no never-word check), so it scores a path the game never runs, and `room_seed` largely repeats `description` (up to ~75 of 450 written tokens, about 2 s); the dialogue system prompt carries the NPC and player names, so no prefix is shared across calls, and `advance` is written even with no story moments; the drift suite scores `_llm_narrate`, which the village (authored pools) never runs; the director could pick among short numbered labels instead of ids.
- **Why deferred:** Out of scope for "Reflexes and few dead ends"; each change re-ratifies a surface's eval or drift golden and wants its own measurement.
- **Revisit criteria:** The next model swap or bake-off, a growth or dialogue latency complaint, or the next change that touches `growth.py` or the dialogue prompt.
- **Origin:** spec 2026-09-29, the prompt audit after criterion 3.

### promise-guard-deflection-cost
- **One-line description:** The promise guard (`dialogue.py`) gives the authored deflection when every draft fails: about half the adversarial probes, 3 of 34 canon questions ("which way is the old well"), and "help Tace" in the battery, where a deflection reads oddly. Options: when all drafts fail, answer from an authored topic the line names; count deflections in the dream digest so a dream can author the missing answer; a third draft only when the arbiter is idle.
- **Why deferred:** The measured cost was accepted for honesty (the operator's decision); a repair draft costs a second dialogue call (about 2.5 s).
- **Revisit criteria:** Play logs or the digest show deflections answering plain questions, or friends say a resident "won't answer".
- **Origin:** spec 2026-09-29 criterion 8 measurements.

### battery-leftovers-2026-09-30
- **One-line description:** Three lines from the replayed creative-break battery (docs/playtests/2026-09-29-creative-break.md, "The battery, replayed"): `reach up` in the cellar reads as no command (the first run's model examined the highest shelf); `count the jars` reads "You can't take the jars" (the model chose take); `look at the hands` in the cellar reads the labels "in many hands".
- **Why deferred:** None is one of the playtest's ten classes; each is a single parser or glimpse wording fix best made with the next battery run.
- **Revisit criteria:** The next battery replay, or a player hitting one of them.
- **Origin:** spec 2026-09-29 criterion 14.

### repeated-things-caps
- **One-line description:** Cap or collapse repeated objects in the parser's scope list (`parser._scope_entries`, uncapped) and in the scene snapshot, so any future way to multiply things (a spawn without a per-player gate) cannot overflow the model's 8,192-token context or stall the event loop rebuilding a scene.
- **Why deferred:** The one known vector (Umber's cup) is gated per player (review 2026-09-30); this is defence in depth.
- **Revisit criteria:** A new authored spawn that can repeat, a dream that adds one, or a room whose scope list passes ~60 things.
- **Origin:** /security 2026-09-30 (the tea-cup WARN).
