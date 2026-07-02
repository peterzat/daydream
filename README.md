# Daydream

![A quiet meadow at dusk, watercolor — generated locally via SDXL + watercolor LoRA on the v1 image-gen pipeline](meadow-at-dusk.png)

A small atmospheric multiplayer web game running on a single dev box. Players enter a procedurally-generated daydream world that all players share and persistently mutate over time. Cozy goals (Animal Crossing-like self-driven storytelling) with MUD-style gameplay (Zork-like text, free-form input, contextual UI buttons).

The image above is the image-gen pipeline's first real output: prompt seeded from the meadow room, SDXL base + a watercolor LoRA via local ComfyUI, gated by the GPU arbiter, ~6 s of render on the dev box's RTX 4000 SFF Ada. It lives at the project root as a historical artifact — the cache layout has since changed (the file is no longer regenerable bit-for-bit by the current code path), but the rendering it captures is the moment v1 first proved itself. The aesthetic anchor is in [`WHIMSY.md`](WHIMSY.md): Spiritfarer / A Short Hike, soft and painterly.

## The idea: a game you can grow from the inside

Daydream is two things at once, and that is on purpose.

It is a **finished, cozy game** you can just play: wander a shared watercolor world, talk to the people in it, gather small keepsakes, mend a clock that stopped. It is also a **small engine for growing that game from the inside**: the machinery that lets the world be extended by the people playing it, not only by the people who authored it.

That second half can look like overbuild. One cozy game does not need a unified object/verb core, a permission model, and an allowlisted world-mutation API. But cloning a MUD was never the interesting part, and shipping a general game-design tool was never the goal. **The interesting part, the actual fun, is a game that players can meaningfully expand with a little in-game prompting.** The platform-shaped pieces exist only to explore that. We are not trying to become a popular way to build games like daydream; we are using daydream to try one specific idea, and to put *this* game online.

### Semi-procedural gaming

Call the idea **semi-procedurally generated** gameplay. Players are playing, not vibe-coding. Their character's actions are the inputs: "give the gear to Tace", "read the ledger", "go north". Those are not prompts in the Claude sense; they are ordinary moves, and the shared world responds to them and *remembers*. Play persistently changes the world.

The new part is that some moves can **expand the world itself**, and that expansion is neither pre-authored nor freely hallucinated. It is **seeded with agentic boundaries and combined with a short, in-character freeform input from the player.** The boundaries keep it coherent, safe, and in-world; the player's own words make the result theirs.

Here is where it is headed, concretely. A player finds a **magical world-seed**. They use it in a room and are asked, in character, "create a doorway to?". They answer with something small, like *"the sub-basement where we find a small hidden dormitory,"* and that new place comes into being and **persists**, there for everyone who wanders in afterward. The end state we are aiming at is enough control, expressed through gameplay and narrative rather than through a level editor, for a player to seed a small area and lay a **short quest** through it.

### Permissions and wizardry

World-shaping is powerful, so it is earned rather than free. Ordinary play (wander, talk, gather, use) stays open to anyone; reshaping the world (seeding rooms, authoring behavior) takes **"wizard" standing.** That implies a permission model layered over the object/verb core, with content filtering alongside it. The moment a player can author something that other players will trigger, permissions and filtering stop being optional, so they belong in the plan from the start rather than bolted on later.

### The local GPU is a deliberate limit

Every bit of live generation runs on one modest GPU (a 20 GB RTX 4000), and that ceiling is a **design choice, not an obstacle we are trying to route around.** The question we care about is not "can a giant LLM produce great gameplay?". With a big enough model, much of this simply gets easier. The question is the harder and more interesting one: **how far can small, targeted local models (a 7B language model for words, SDXL for pictures) be pushed to carry real, expandable gameplay?** The GPU budget is a rule of the game we are actually playing. Where the small models cannot reach, we pre-bake with a larger model at design time (see [Two dreamers](#two-dreamers)), never by calling a bigger model at runtime.

### Where this could go: a little logic under the language

The generative layer does not have to carry everything. A natural next step is to combine **plain logical building blocks (conditionals, if-then branches, simple state gates)** with the agentic LLM layer, so an authored or player-seeded area can hold real mechanics (a lever that opens a door, a gift that changes what a character will say) while the language model enriches the texture and voice around that logic. Deterministic bones, generative skin. That mix is where both the *playing* and the *making* get a lot richer.

### Objects, verbs, and free-form input

Underneath all of it is a small MOO-style core. The durable reference is [`CLAUDE.md`](CLAUDE.md); the short version:

- **Everything is an object.** Rooms, characters, and things live in one store, and where a thing *is* is just another object (the room it sits in, or the character carrying it). Objects can be spawned into the world at runtime, not only defined up front.
- **A closed set of verbs.** `look`, `examine`, `take`, `drop`, `talk`, `give`, `use`, `open`, `read`, `go`, and a handful more. Each verb knows what it can apply to, so "talk to a rock" or "take a person" are simply never offered, and two-object verbs like `give X to Y` and `use X on Y` are first-class.
- **Two ways to act, one bus.** Clicking an object or a verb sends a **structured command** straight to the engine, with no language model in the loop, so it is instant and deterministic. Typing free text goes through a **grounded local-LLM parser** that maps your phrasing onto a verb and the specific in-scope object you meant. "hand Tace the gear", "give the gear to Tace", and clicking Give then the gear then Tace all resolve to the same move.
- **Free phrasing, not a word list.** The parser is what keeps input natural: the vocabulary is not a fixed set of magic words. Novel phrasings are understood and *grounded*, but they always resolve to a real, permitted action on a real object, which is also what keeps a generative world from drifting into nonsense.
- **Action discovery.** The interface shows what is present and what you might do with it (a verb ribbon, clickable objects in the prose, exits on a compass), so you are never left guessing what the parser knows; the text box is for everything the buttons do not anticipate.

The same allowlisted, safety-checked path that runs a `talk` or an `examine` today is the path a world-shaping verb runs tomorrow. That is why the engine-shaped pieces earn their place: they are the groundwork for the semi-procedural world, not architecture for its own sake.

## The Reading Room

Daydream presents as a storybook you act inside. A matted room painting opens each place, the narration is drop-cap prose on a paper page, who and what is with you is noted in the margin, and your moves are quiet ink-tab choices ("what you might do") with a compass of ways out. Object mentions in the prose are clickable, and examining or reading one opens an inline detail inset. The durable UI design language is [`DESIGN.md`](DESIGN.md) (the interface counterpart to `WHIMSY.md`); the visual reference is [`docs/mockups/01-reading-room/`](docs/mockups/01-reading-room/).

![The Reading Room UI: the Stopped Clock room with a matted watercolor plate, a hand-lettered title, drop-cap narration with an opened-ledger detail inset, a right-margin column of who and what is here and what you carry, and an ink-tab action ribbon.](docs/pretty/reading-room-ui.png)

What you carry opens as a keepsakes spread, each thing a pressed specimen with room for what you have yet to find.

![The keepsakes backpack: a two-page Keepsakes spread showing carried items as pressed specimen cards beside empty collection slots.](docs/pretty/reading-room-keepsakes.png)

## Status

Latest stable cut: **v0.5.0** (dreamseeds — a quest-earned seed grows one persistent, LLM-composed room for everyone; the first world-growth loop on top of v0.4.0's playable quest and the Reading Room storybook UI). Runs on a single Linux dev box (RTX 4000 SFF Ada, 20 GB VRAM); designed to port to Cloudflare and containers later. Test gates: the fast and integration tiers (see [Tests](#tests)) are both 100% green; real-GPU drift + parser-grounding + growth-composition probes run on-demand under `bin/game test long`.

What works today:

- MOO-style object/verb core: toons, NPCs, things, and rooms are one `objects` table (containment by location, verbs by prototype). A closed verb set (Examine/Take/Drop/Talk/Say/Go, plus two-object Give/Use, state-gated Open/Read, and Plant) runs through one command bus; UI clicks send structured commands (no LLM), and free text is routed by a grounded local-LLM parser so natural phrasings ("say hi to rook", "pick up the lamp") resolve to the right verb + in-scope object. Things render as distinct, clickable chips with a verb bar; objects mentioned in narration are clickable. Verbs emit only the world-mutation effects they declare (`narrate`/`set_property`/`spawn_object`/`move_object`, plus the world-shaping `spawn_room`/`link_exit` that only `plant` may emit), and a dialogue can spawn a real, clickable object (Rook's "sheaf of papers"), described lazily on first examine and cached after. The local LLM is a hard runtime dependency for natural language: with vLLM down, free text degrades to "the dream is foggy" while clicks/exits/cached verbs still work.
- Multi-room world (5 rooms, bidirectional exits) with three hand-authored NPCs. The canonical world is **The Clockmaker's Loft** (`worlds/clockmakers-loft.json`): Tace the clockmaker, Bell the lamplighter, and Mott the sweeper, each reached via the `talk` verb (dialogue runs the safety + LLM + memory pipeline), plus one complete quest — read the repair ledger, find the escapement gear by the old well, give it to Tace for the case-key, use the key on the clock case, and open it so the great clock ticks again, for everyone.
- Dreamseeds — the world grows from the inside: finishing the quest earns a **dreamseed** alongside the cog. Carry it anywhere, `plant` it, and answer one in-character question ("Where does the new way lead?") with a short phrase; one local-LLM call composes a small new room inside the seed's authored boundaries (theme, palette, motifs, exemplar rooms baked into the world envelope at design time), a real exit opens in an engine-picked direction, and the place persists for every player, forever — provenance-stamped, walkable both ways, its watercolor painted lazily on first entry, the spent husk resting inside. Growth is bounded (strict schema + WHIMSY banlist + anti-copy validation, a per-world grown-room cap, seed scarcity as the permission model) and every failure path — outage, refusal, off-tone vision, cap, all exits taken — preserves the seed and mutates nothing.
- NPC drift loop emits per-NPC narrate ticks so the world feels inhabited (every 5 min idle, every ~4 min when a human is connected). Drift composes each tick via the LLM from the NPC's recent memories + mood, falling back to a mood-bucketed canned pool when vLLM is down or the response trips the WHIMSY banlist. Hand-authored NPCs draw their canned voice from a per-NPC pool; bootstrapped NPCs (and any NPC without one) fall back to a shared generic, name-templated pool so they drift on the offline path too. Witnessed, not hidden: drift is no longer suppressed in a room a human occupies — a co-located NPC's ambient body-language beat is shown to the present player as a quiet "the world is alive around you" moment (the room-filtered broadcast delivers it), on the minutes-scale present-player cadence; each tick has a small chance to nudge the NPC's mood to a different bucket so the world drifts over hours of play.
- NPC dialogue memory: each NPC exchange is captured to a per-world `memories` table with a 384-dim CPU embedding (BGE-small via `sentence-transformers`), and the next turn pulls top-K by `cosine_similarity * exp(-age/24h)` and weaves them into the prompt as context. Fail-closed (capture/retrieve return `None` / `[]` if the embedder isn't installed) so the dialogue path stays warm even before `bin/memory-bootstrap` runs. CPU-only by construction; no GPU arbiter contention.
- Watercolor SDXL backgrounds for any room, generated locally via ComfyUI behind the GPU arbiter. vLLM (Qwen 2.5 7B Instruct AWQ) serves narration. Both engines optional; the game runs at all engine combinations.
- Voice-bench audit-trail harness (`bin/game voice-samples`) captures dated narrate samples for any model swap; four baselines in tree under `docs/pretty/voice-samples/` (pre-fix and post-fix AWQ plus two Mistral-Nemo Q4 failure modes — see Release notes).
- World admin: `bin/game world list / archive / restore / snapshot / snapshot-restore / swap / load / verify / delete` covers per-world archival, full-bundle ship-to-friend, fast DB-only point-in-time snapshots (and restore-refusing-overwrite), live in-process hot-swap of the running server's world (`swap`, no restart; connected clients re-snapshot), keyless world authoring (`load`), integrity checks, cascade delete. World authoring is keyless per the generation policy: author the world in a Claude Code session, then `bin/game world load <envelope.json>` (no API key). (`bin/game world bootstrap`, which called the Anthropic API, is deprecated.)
- Friend-scope auth (shared password, single port). `DAYDREAM_ACCESS=tailscale` (default) or `public`.
- Session & presence: rooms describe themselves on entry (full on the first visit this session, a short line on re-entry); a fresh page load starts with an empty log (a reconnect resumes via `?since`); "leave the dream" wakes you to the character picker, releasing your toon; the 5-slot toon picker does create / claim / kick (rest) / delete.
- Playable, legible first entry: any session with no claimed toon lands on the character picker (never a phantom toon, so input never silently no-ops); the scene labels WHO YOU ARE / HERE WITH YOU / ON THE GROUND / YOU'RE CARRYING; the verb bar offers a verb only where it applies (Talk → toons, Take/Drop → things); an `inventory` command and a backpack control surface what you carry; "go to \<place>" and "look at \<thing>" resolve naturally; player ids never leak into chat; and a dropped connection shows one calm "the dream is sleeping…" overlay that recovers on its own (the same overlay is the "the dream shifts…" beat on a live world swap).

Pointers: full release narrative in [`## Release notes`](#release-notes) below; the GPU/model decision narrative (VRAM math, picks, what we tried and rejected) lives in [`docs/gpu-and-models.md`](docs/gpu-and-models.md); deferred items in [`BACKLOG.md`](BACKLOG.md); the active spec (if any) in [`SPEC.md`](SPEC.md).

## Aesthetic

Cozy, soft, painterly. Reference touchstones: Spiritfarer and A Short Hike. NOT pixel-art, NOT crunchy 8-bit, NOT melancholic. The durable tone bible is [`WHIMSY.md`](WHIMSY.md). Its interface counterpart is [`DESIGN.md`](DESIGN.md), the durable UI design language ("The Reading Room" storybook look); read it before touching the `web/` UI or authoring component CSS.

## Two dreamers

Daydream runs on one small dev box. A single RTX 4000 GPU (20 GB of VRAM) does every bit of the game's live generation, and that limit is deliberate. The work splits in two: what the running game dreams for itself, and what we dream for it ahead of time.

**The near dream** is everything the living game conjures while people are playing: room paintings, narration, the talk of NPCs and the ambient drift of a world left alone. It runs entirely on the local GPU — vLLM (Qwen 2.5 7B) for words, ComfyUI (SDXL + a watercolor LoRA) for pictures — and never reaches past the box. No production cloud key, ever. This is the dream the world dreams for itself, in real time.

**The deep dream** is for what the near dream can't reach alone: authoring a whole new world, seeding its first rooms and voices, the rare admin act the small local model can't be expected to imagine well. For those we lean on a greater dreamer — Opus, inside a Claude Code session, at design and development time. It lays the groundwork and steps back; it is never part of the running game.

The north star: **make daydream as lovely as a single RTX 4000 allows.** Where the near dream falls short, we pre-bake quality with the deep dream — an Opus-written room, a hand-seeded NPC voice — then let the small local models carry it at play time. Pre-bake at design time; dream locally at play time.

And a standing pact with the deep dreamer: **when something we want won't be compelling on the local hardware, say so — here, at design time, together** — so we can choose how to close the gap (pre-bake it, cache it harder, simplify it, or accept the edge) instead of quietly shipping something flat. Operator and agent specifics live in [CLAUDE.md "Generation policy"](CLAUDE.md).

## Run

First time:

```sh
cd ~/src/daydream
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
cp .env.example .env
$EDITOR .env   # set DAYDREAM_PASSWORD; review DAYDREAM_ACCESS
```

Daily:

```sh
bin/game up        # GPU-assuming default: preflight GPU, then FastAPI (0.0.0.0:54321) + vLLM + ComfyUI
bin/game up --no-gpu  # FastAPI only (CPU-only / no engines, no GPU preflight)
bin/game status    # process state, port reachability, access mode, where state lives
bin/game logs      # tail recent FastAPI output
bin/game down      # stop
bin/game world     # list / archive / delete worlds + their generated assets
```

Visit `http://<host>:54321` from another tailnet device (or `http://localhost:54321` from the box) and enter your password. Re-running `up` while up, or `down` while down, is a no-op.

`DAYDREAM_PASSWORD` is the only required setting. If `.env` is missing or that variable is unset, the auth endpoint refuses every login (503) — there is no published default. `~/.config/daydream/secrets.env` (per-host, gitignored) overrides anything in project `.env`.

### Network access

`DAYDREAM_ACCESS` in `.env` controls who the FastAPI server will talk to:

- **`tailscale`** (default): the `AccessMiddleware` in `daydream/api/access.py` rejects any HTTP/WS client whose source IP is not in Tailscale's CGNAT range (`100.64.0.0/10`) or loopback. Tailnet members reach the game; the wider internet sees a 403 (or a WebSocket close 1008) even if the port is somehow exposed.
- **`public`**: middleware lets all clients through.

`DAYDREAM_ACCESS=public` is an "agree to be public" flag at the app layer — flipping it does NOT also open UFW. For traffic to actually arrive from the internet you also need `sudo ufw allow 54321/tcp` and (probably) public DNS pointing at the box. `bin/game status` prints a UFW-reminder warning when `public`.

Internal services (vLLM on 8000, ComfyUI on 8188) bind `127.0.0.1` by default — daydream is their only consumer. To reach ComfyUI's web UI from another machine, SSH-tunnel: `ssh -L 8188:localhost:8188 <host>`. Or override `DAYDREAM_COMFYUI_HOST=0.0.0.0` to expose on the tailnet.

## Optional engines: LLM and image gen

The deterministic verbs (clicks on the verb bar / objects, exit buttons, and exact words like `look` / `take lantern` / `go north`) work without GPU or any external engine, since they resolve on the parser's fast-path with no LLM call. Natural-language free text, though, now goes through the grounded local-LLM parser: it is a hard runtime dependency for open text, so with no vLLM running those inputs narrate "the dream is foggy" (the deterministic surface stays usable). When a room has no cached background, the SPA shows a "painting..." overlay and queues an image-gen job; with no ComfyUI running the overlay disappears after the failed call and the placeholder stays. **The game stays usable at every engine combination — only natural-language input and live generation need vLLM up.**

To enable, follow the same `external/<engine>/` pattern (full rationale in [CLAUDE.md "External engines"](CLAUDE.md#external-engines)):

```sh
# ComfyUI: ~13 GB on disk (SDXL base + watercolor LoRA), ~10 min one-time
bin/comfyui-bootstrap
bin/game comfyui-up         # bin/game comfyui-down to stop

# vLLM: ~5 GB model cache + ~3 GB pip deps, ~10 min one-time
bin/vllm-bootstrap
bin/game vllm-up            # bin/game vllm-down to stop
```

The aesthetic A/B harness `bin/game image-test "<prompt>" [--model X --lora Y]` produces a one-shot PNG via the same workflow JSON the room-bg generator uses. Use it before locking in any LoRA choice. Output lands at `~/data/daydream/images/test/`; promote keepers to `docs/pretty/` (see [CLAUDE.md "Keeper images"](CLAUDE.md#keeper-images-docspretty)).

The voice-bench A/B harness `bin/game voice-samples` renders the 5-prompt corpus at `tests/drift/voice/*.json` against the current `DAYDREAM_LLM_MODEL` (vLLM must be up) and writes a dated, model-slugged markdown file under `docs/pretty/voice-samples/`. Same idea as the image A/B but for narration: each capture documents the vLLM flag set, per-prompt latency + token counts, and the rendered narrate verbatim, so a future bump can be eyeball-diffed against the prior baseline. Four baselines ship in tree: the pre-fix and post-fix Qwen-AWQ captures (showing the prompt-template tic before and after the variety pass) plus two Mistral-Nemo Q4 failure modes from the 2026-05-06/05-07 experiments.

For the live LLM ↔ image-gen serialization smoke (boots both engines, runs 5 alternating requests, asserts no OOM and clean output):

```sh
.venv/bin/python tools/arbiter-smoke.py
```

## NPC memory (optional)

NPC dialogue retrieval needs a CPU embedder (`sentence-transformers` BGE-small, ~100 MB). One-time install:

```sh
bin/memory-bootstrap     # ~200 MB CPU torch wheels + the BGE-small model
```

The script installs `sentence-transformers` against the PyTorch CPU wheel index (avoids the ~1.5 GB CUDA libs we never use; embedding runs on CPU by construction so the GPU stays free for vLLM + ComfyUI under the arbiter). Re-runs are no-ops. Skip it and the dialogue path still works — capture / retrieve fail closed and NPCs just have no memory until the bootstrap lands. Toggle the whole subsystem with `DAYDREAM_MEMORY_ENABLED` (default `1` in production, `0` in `tests/conftest.py`).

## Tests

```sh
bin/game test short     # unit / fast (~3s)      — pre-commit gate (418 tests)
bin/game test medium    # integration (~10s)     — pre-push gate (658 tests)
bin/game test long      # real-GPU drift (~15min) — on-demand / pre-release
bin/game test human     # aesthetic rubric via qpeek — async human review
bin/game review         # offline contact sheet: anchors + NPC voices, one glance
```

One entry point; four tiers; durations scale with what the tier verifies. Bare `.venv/bin/pytest` still runs every test (backward compat). The drift probes under `tests/drift/` exercise the real LLM + image-gen paths and compare to git-committed baselines under `tests/baselines/*.golden.json` — a divergence fails the test with a diff and the operator ratifies a new baseline with `mv .latest .golden` + commit. The tic-detection probe at `tests/test_voice_baseline.py` parses captured voice-bench markdown and asserts pairwise-distinct body-language openers; it now globs `docs/pretty/voice-samples/*.md` classified by a `baseline-class` marker, so a new tracked baseline auto-extends the regression with no code edit. `bin/game review` rolls the qualitative checks up into one offline contact sheet (anchor renders incl. the forge, a `talk` sample per NPC, the connection-overlay browser checklist) so a review is a single glance, not a live reset; the aesthetic critic is the Claude Code agent, which Reads the renders and grades them against `WHIMSY.md` in-session (no API key), escalating to `qpeek` or an in-game look when a human eye is wanted. The durable philosophy and extension guide live in [`TESTING.md`](TESTING.md); read it before adding a test or bumping a model / LoRA / workflow.

## How this is built (zat.env)

daydream is built one reviewed increment at a time on the [zat.env](https://github.com/peterzat/zat.env)
turn loop: a `SPEC.md` acceptance contract is consumed, implemented with paired tests, run
through adversarial `/codereview` + `/security`, and committed, with a pre-push marker
gating unreviewed code. The harness is deliberately thin (Markdown specs, bash hooks,
plain-text conventions) so that model-generation improvements express themselves directly
through it rather than being absorbed by scaffolding; the companion essay is
[The Bitter Lesson of Agentic Coding](https://agent-hypervisor.ai/posts/bitter-lesson-of-agentic-coding/).

Two experiment records live alongside the code:

- [`FIRST-FABLE.md`](FIRST-FABLE.md) — the project's first Claude Fable 5 session
  (2026-07-02), run as a pre-registered experiment on whether a model-generation step
  function expresses itself through the unchanged thin harness: predictions written down
  at the session break, results appended after the implementation turn.
- [`docs/history/GOAL.md`](docs/history/GOAL.md) — an earlier experiment driving whole
  increments unattended with Claude Code's `/goal` (two runs, pre-registered predictions,
  candid retrospective). `/goal` is not in active use.

## Release notes

### v0.5.0 — dreamseeds: the world grows from the inside (8/8)

The README's headline "semi-procedural" moment ships: play can now permanently grow the shared world. Opening the mended clock case reveals a **dreamseed** beside the warm brass cog — scarcity as the permission model (finish the authored quest, receive the power to grow). `plant` joins the closed verb set as the first and only consumer of the `spawn_room`/`link_exit` effect vocabulary (documented-not-built since v0.3.0, now real, and rejected for every other verb and every data skill by the allowlist gate). The pipeline (`daydream/growth.py`): pre-LLM gates → ONE local-LLM call composing title/prose/0–2 objects inside the seed's Opus-authored boundaries (the model never sees ids or directions) → strict validation (length windows, reject-not-truncate, WHIMSY banlist, anti-copy against the seed's exemplars, a refusal escape hatch) → a synchronous commit block that re-checks every raced gate before dispatching one ordered effect batch. Every failure path preserves the seed; `DAYDREAM_GROWTH_MAX_ROOMS` (default 12) bounds total growth. Grown rooms are first-class with zero reader changes: full description on entry, exits both ways, lazy watercolor art, provenance (`generated_by="plant:<seed-id>"` + a structured `grown` record of seed, planter, verbatim phrase, timestamp). Both producers drive it (click staging with a vision prompt; typed "plant the dreamseed …" grounded by the parser), and the planter's snapshot refreshes in place so the new exit simply appears. A new tier_long probe (`tests/drift/test_growth_compose.py`) renders the shipped seed's boundaries against real vLLM and gates the mitigation ladder; the deterministic golden playthrough gains the full plant extension. `WORLD_VERSION` → 1.2.

### v0.4.0 — a playable quest (8/8)

The substrate gets its first complete play loop: **discover → gather → exchange → unlock → reveal**. Two-object verbs (`give X to Y`, `use X on Y`) join the closed set with a `valid_iobj_kinds` gate symmetric to the direct-object gate; `open` is state-gated and `read` surfaces a readable's authored words (distinct from `examine`'s physical description). Object state is free-form `properties.state`, mutated through the existing effect API with no migration. The keyless world envelope can now author stateful interactive objects (a locked case, a readable ledger, an immovable `fixture`) and NPC `wants`/`gives`, and a `spawn_object` can grant per-object verbs (a given key becomes `use`-able). A brand-new canonical world — **The Clockmaker's Loft** — hosts one quest: read the repair-ledger, find the escapement gear by the old well, give it to Tace to earn the case-key, use the key on the clock-case, and open it so the great clock ticks again, for everyone. Both producers drive the new verbs: a deterministic parser fast-path for "give X to Y" / "use X on\|with Y", and a two-step click-staging UI (stage the verb, click the thing, click a kind-valid target). The deterministic golden playthrough (`tests/test_quest_playthrough.py`) is the durable regression guard the architecture was missing. `WORLD_VERSION` → 1.1; `bin/game world reset` targets the new world; `worlds/bunny.json` is retained as a loader-regression fixture. All 8 acceptance criteria closed across 8 test-green increments.

### v0.3.0 — a world of objects (18/19)

The largest single turn to date: a MOO-style object/verb refactor that makes in-world things first-class and routes player text through the local LLM. Toons, NPCs, things, and rooms unify into one `objects` table (containment by `location_id`, default verbs by `prototype_id`); a closed verb set (Examine / Take / Drop / Talk / Say / Go) runs through one `execute_command` bus fed by two producers — UI clicks (a structured command frame, no LLM) and free text (a grounded local-LLM parser). All runtime mutation flows through an allowlisted world-mutation effect API, and a dialogue can spawn a real, clickable object (Rook's "sheaf of papers"), described lazily on first examine and cached after. Landed as 10 committable, test-green increments: 377 fast tests (`tier_short`) and 591 integration tests (`tier_medium`), each 100% passing, plus a new real-GPU parser-grounding drift probe. 18 of 19 acceptance criteria closed; the one open is the destructive live world reset (operator action).

**What's new since v0.2.0:**

- *One object store.* Migration 011 unifies `rooms`/`toons`/`items` into `objects` (`kind` in room/toon/thing/prototype). Containment is a self-referential `location_id`; inheritance is `prototype_id` → a `kind='prototype'` row carrying default verbs. `daydream/objects.py` is the single access surface; `rooms.py`/`toons.py`/`items.py` are thin typed views over it (their old APIs preserved, so every caller + the suite kept working). Promoted columns are only the toon auth/slot fields + a partial unique slot index; everything else lives in `properties_json`.
- *Closed verbs + MOO dispatch.* `daydream/verbs.py` is a closed, engine-implemented verb set with arg-specs (needs a dobj? valid target kinds? per-verb effect allowlist?). `execute_command` validates scope + applicability (`verb in verbs_for(dobj)` rejects "take a toon" / "talk to a rock") then dispatches by MOO priority (player → room → dobj → iobj); an NPC's bound `talk` dialogue beats the generic stub. Deterministic verbs make no LLM call.
- *Grounded local-LLM parser.* `daydream/parser.py` maps free text to a grounded command: a fast-path (exit directions, bare verbs, "verb \<name>", legacy data-skill names) makes zero LLM calls; otherwise one JSON-constrained Qwen call picks a closed verb + grounds the target to an in-scope **id** ("say hi to rook" / "talk to rook" / "greet rook" → `talk(t-rook, "hi")`). The local LLM is now a hard runtime dependency for natural language: vLLM down → "the dream is foggy" for free text, while clicks / exits / cached verbs still work. A `tier_long` probe ran live against vLLM and grounded every case.
- *World-mutation effects + generative objects.* `skills/effects.py` generalized to `narrate`/`set_property`/`spawn_object`/`move_object` (with `add_item`/`set_mood` retained as aliases), with a per-verb allowlist gate (a disallowed kind mutates nothing). Promotion is explicit-only — narration is never auto-scanned for nouns: a verb's LLM output emits `spawn_object` to create exactly one clickable thing (deduped on name + location + provenance, so re-running never duplicates). `examine` is lazy-cache: a spawned object with no detail gets one LLM call, persisted as `properties.examined_text` and served from cache (zero LLM) thereafter.
- *Clickable-object UI.* The snapshot carries scene objects + inventory + a verb bar + an entity sidecar; the SPA renders toons / things / inventory as distinct clickable chips (verb-then-object targeting, object-click defaults to Examine), and in-scope object mentions in narration become clickable. No generic "go" button; per-direction exits remain the only nav affordance.
- *Keyless object-schema authoring.* `load_world` builds the object schema from an Opus-authored envelope carrying per-NPC `talk` dialogue bindings + aliases, with no LLM call and no API key. The reset world is authored at `worlds/bunny.json` (its Rook spawns the papers in an integration test).

**What's next:** the operator-driven live world reset (`bin/game down` → `bin/game world archive w-bunny` → `bin/game world load worlds/bunny.json` → install as `worlds-dev/live.db` → `bin/game up` → browser eyeball). Then the deferred depth recorded in [`BACKLOG.md`](BACKLOG.md): player-touch object promotion, two-object verbs (give/use), deep prototype inheritance, object clutter-GC, and the headline user-authored, LLM-driven world-building verbs.

### v0 — *the smallest dream* (10/10)

The first dream that runs. Single hardcoded toon (Wren) in a single hardcoded meadow at dusk; Python 3.10 + FastAPI + websockets in a single process tree; SQLite-per-world with an append-only events log as the spine; friend-scope shared-password auth; vanilla HTML / CSS / JS frontend. No LLM and no image gen yet. The point was proving the architectural spine: one process, events table is the source of truth, snapshot reconstruction from events, and a clean "join → see room → leave a footprint → reconnect → see your footprint" loop on a single dev box.

### v1 — image-gen pipeline (8/8)

SDXL base 1.0 + `ostris/watercolor_style_lora_sdxl` served by ComfyUI for room backgrounds; vLLM 0.19.1 serving Qwen 2.5 7B Instruct AWQ for free-form narration; both gated by an in-process GPU arbiter (`asyncio.Lock` at `daydream/gpu/arbiter.py`) that serializes inference on the 20 GB RTX 4000 SFF Ada so the engines never OOM each other. `tools/arbiter-smoke.py` runs 5 alternating LLM + image-gen requests and asserts no OOM in ~9 s wall-clock on this hardware; that's the live-stack canary to run after any engine bump. The arbiter lock is asyncio-only (single process); cross-process concurrency would need a flock and isn't on the table at v1's CCU. The hero `meadow-at-dusk.png` at the project root is this pipeline's first real output.

### v0.2.0 — second inhabited dream

v0.2.0 keeps v0.1.0's foundation (multi-room world, two NPCs, dialogue memory, image gen) and layers reactive depth on top. Drift narrates now compose from the LLM with each NPC's recent memories + mood (mood-bucketed canned pool retained as offline fallback), drift is suppressed in any room a human currently occupies, and each tick has a small probability of nudging the NPC's mood to a different bucket so the world drifts over hours of play. A drift voice-bench harness mirrors the dialogue voice-bench so tone drift in LLM-composed drift output is eyeball-diffable across model swaps. Tier gates green throughout: 320 fast tests (`tier_short`) and 451 integration tests (`tier_medium`), each 100% passing.

**What's new since v0.1.0:**

- *LLM-driven drift narrates.* `daydream/drift.py:_tick` runs a two-path tick when `DAYDREAM_DRIFT_LLM_ENABLED=1`: pulls up to K memories via `memories.retrieve(query=npc.seed)`, renders a tight Jinja prompt (npc_name + seed + mood + `<memory>`-wrapped recents), calls `acompletion_json` (which holds the GPU arbiter), runs `safety.first_banned` on the parsed `narrate`, emits. On any failure (`LLMUnavailable`, banlist hit, empty/missing narrate) it falls through to the canned pool. The canned pool is now mood-bucketed (`dict[str, dict[str, list[str]]]`) — Rook's existing 4 lines carry into the `content` bucket, Iris's into `thoughtful`, plus 4 new lines per NPC across the other buckets so the offline path stays varied.

- *Drift polish.* Per-NPC selection weights (`_NPC_DRIFT_WEIGHT` defaults equal; weight 0 excludes); room-occupancy suppression (`_occupied_room_ids` filter, default-on via `DAYDREAM_DRIFT_SUPPRESS_OCCUPIED`); probabilistic mood transitions (`_maybe_transition_mood` with `DAYDREAM_DRIFT_MOOD_DRIFT_PROB` default 0.2 + new `daydream/toons.py:set_mood` parameterized helper). The three compose: filter occupied rooms → weighted-pick from survivors → emit narrate → maybe-transition mood.

- *Drift instrumentation.* `bin/game drift-samples` writes dated markdown under `docs/pretty/drift-voice-samples/` from a 5-prompt corpus at `tests/drift/drift-voice/*.json` (covers Rook/Iris × content/thoughtful × empty/with-memories + a non-bucketed `weary` mood). Hermetic by construction — no DB, synthetic memories from the corpus. Plus `_TICK_COUNTS` outcome counters (`llm_emit` / `canned_fallback` / `noop`) surfaced via the `/status/drift` plain-text endpoint and a one-liner in `bin/game status` when any counter is non-zero.

- *Tooling.* `bin/install-hooks` (idempotent pre-commit + pre-push installer; marker-aware so user-written hooks aren't clobbered, refuses to overwrite hand-written hooks). Memory salience drift probe at `tests/drift/test_memory_ranking.py` pinning the `cosine_similarity * exp(-age/24h)` formula against `tests/baselines/memory_ranking.golden.json`.

**What's next:** capture the first drift voice-bench baseline (operator session: bring vLLM up, run `bin/game drift-samples`, commit the markdown); LanceDB-backed memory retrieval once memory counts cross ~10K per NPC (v0 is SQLite-only); drift voice-bench corpus expansion once the first baseline reveals what patterns are worth probing. Then anything else operator-driven.

### v0.1.0 — first inhabited dream

v0.1.0 takes the v1 image-gen pipeline as a substrate and builds a multi-room world with two hand-authored NPCs, a data-skill safety baseline, an asyncio drift loop emitting per-NPC narrate ticks while the player is elsewhere, NPC dialogue memory so Rook and Iris remember past exchanges, and a voice-bench audit-trail harness that captures dated narrate samples for any model swap. Tier gates green throughout: 290 fast tests (`tier_short`) and 401 integration tests (`tier_medium`), each 100% passing. Bare-mocked-LLM tests cover the data-skill safety pipeline + WS dispatch end-to-end; real-GPU drift probes run on-demand under `bin/game test long` against committed golden baselines.

**What works:**

- *World.* Five rooms (`r-meadow` spawn, `r-forge`, `r-bridge`, `r-attic`, `r-hollow`) connected by bidirectional `exits_json`; a player can `go north`, `go up`, etc., and the SPA renders the snapshot's exits as clickable buttons.
- *NPCs.* Rook (forge-keeper, slot 100, at `r-forge`) and Iris (attic archivist, slot 101, at `r-attic`). Each has a `presence_text` line that fires when the player enters the room, plus a `skills/<npc>.json` data-skill that handles dialogue (`rook hello` at `r-forge` dispatches Rook's voice via the LLM; the same `iris hello` at `r-meadow` falls through to the chat fallback because the `context_predicate` scopes to `room_slug=attic`).
- *Drift loop.* `daydream/drift.py` runs as an asyncio.Task in the FastAPI lifespan, sleeps `DAYDREAM_DRIFT_IDLE_SECONDS` (300 s) when no WS subscribers are connected and `DAYDREAM_DRIFT_BUSY_SECONDS` (1800 s) when ≥1 is. Each tick picks a random NPC, draws a line from a per-NPC pre-canned pool of 4 lines, emits a `narrate` event to the NPC's room. v0 is pre-canned — no LLM call, no GPU arbiter contention by design — so the BACKLOG entry's "yield arbiter on player input" requirement is vacuously satisfied until v1 introduces LLM-driven drift.
- *NPC dialogue memory.* Each Rook / Iris exchange is captured to a per-world `memories` table (migration 009) with a 384-dim CPU embedding via `sentence-transformers` BGE-small; the next turn pulls top-K by `cosine_similarity * exp(-age/24h)` and weaves them into the prompt as `<memory>...</memory>`-wrapped context. Capture short-circuits on the input banlist before INSERT (defense-in-depth against stored prompt-injection); retrieval is per-(npc, world) scoped. Fail-closed everywhere — capture/retrieve return `None` / `[]` if `bin/memory-bootstrap` hasn't run, so the dialogue path stays warm without the embedder. CPU-only by construction; the GPU stays free for vLLM + ComfyUI under the arbiter.
- *Safety baseline.* `daydream/llm/safety.py` plus the data-skill effect-allowlist in `daydream/skills/effects.py` give us: input-banlist short-circuit (banned mood / pixel-art / urgency triggers a soft-narrate fallback before the LLM is called), Jinja `SandboxedEnvironment` template render with `<player_input>` and `<memory>` role-separator tags, JSON `response_format` constraint at the LLM call site, refusal schema with default-reason fallback, and an output-banlist check on the parsed effects payload before any state mutation.
- *Voice-bench audit trail.* `bin/game voice-samples` writes `docs/pretty/voice-samples/<today>-<model_slug>.md`. Four durable baselines in tree: `2026-04-24-qwen2.5-7b-instruct-awq.md` (the pre-fix substrate, frozen as the regression-detection before-shot), `2026-05-06-qwen2.5-7b-instruct-awq.md` (the post-fix substrate after the prompt-template variety pass), `2026-05-06-mn-12b-rp-ink-q4_k_m.md` (RP-Ink failure mode), `2026-05-07-mistral-nemo-instruct-2407.md` (Instruct controlled-base failure mode). Plus a regression-detection probe at `tests/test_voice_baseline.py` that parametrizes over the pre-fix and post-fix AWQ baselines.
- *World admin.* `bin/game world list / archive / restore / verify / delete` covers per-world archival, full-bundle ship-to-friend, on-disk integrity checks, and cascade deletion (memory rows included). State lives under `~/data/daydream/`, never the project tree; archive bundles include a `MANIFEST.json` recording schema_version + asset counts.

**Engines and operational notes:**

- *vLLM.* 0.19.1 pinned, serving Qwen 2.5 7B Instruct AWQ on the RTX 4000 SFF Ada (compute capability 8.9). Tunings: `--enforce-eager` (avoids a CUDA-graph OOM hit on this card), `--gpu-memory-utilization 0.45` (~9 GB ceiling so SDXL fits alongside), `--max-model-len 8192`, `VLLM_LOGGING_LEVEL=ERROR`. **No `--kv-cache-dtype fp8_e4m3`**: deterministically broke tight-format JSON adherence on Qwen 2.5 7B AWQ during the `tools/arbiter-smoke.py` strict-JSON probe (model looped `!***` garbage tokens after one clean turn). Re-enabling the flag is gated on a calibration pass per the BACKLOG `calibrated-fp8-kv-scales` entry.
- *gguf packaging-bug workaround.* `bin/vllm-bootstrap` includes an idempotent post-install patch that injects `__version__` into the installed `gguf/__init__.py`. transformers 5.6's `is_gguf_available()` reads the version via `importlib.metadata.packages_distributions()` and falls back to `getattr(gguf, '__version__', 'N/A')`; every gguf release in vLLM's supported range (0.17.0 through 0.19.0) fails to register the import name and exposes no `__version__`, so the fallback returns "N/A" and `version.parse` rejects it, crashing vLLM startup any time it tries to load a GGUF model. Patch is applied unmodified across two GGUF model loads (RP-Ink + Instruct, both Mistral-arch) so it generalizes; remove the patch block when upstream gguf fixes its packaging metadata. See [`docs/gpu-and-models.md`](docs/gpu-and-models.md) "Things we tried and rejected" for the full diagnosis chain.
- *Image gen.* SDXL base 1.0 + `ostris/watercolor_style_lora_sdxl` via ComfyUI. ~6 GB resident, ~10-12 GB peak during inference. Coexists with vLLM behind the in-process arbiter (`asyncio.Lock`) at `daydream/gpu/arbiter.py`.

**What we learned (and what didn't work):**

- *Prompt-template variety.* The first AWQ baseline showed 4 of 5 narrate responses opening with the same 14-word phrase ("Rook pauses the steady rhythm of the bellows, wiping hands on the apron, and says,") — a template-induced tic from a flat list of candidate sensory beats. Eight prompt-template iterations later, the working configuration is: kind-specific input-anchor mapping (5 input kinds map to 5 distinct opener anchors), 3 illustrative exemplars showing varied openers + concrete spoken lines, explicit ban on the originating tic phrase by name. PREFER lists trigger direct phrase copying; AVOID lists prime the topics they ban; over-constrained prompts cause truncation. Iris was authored with these lessons baked in from version 1, no iteration needed.
- *Greedy decoding tax.* vLLM's `acompletion_json` defaults to `temperature=0.0`, which makes capture deterministic but funnels the model into ONE preferred response shape regardless of input. Variety has to come from the prompt's input-differentiating signals, not from sampling.
- *Mistral Nemo Q4 + data-skill pipeline = no.* Both `bartowski/MN-12b-RP-Ink-GGUF/MN-12b-RP-Ink-Q4_K_M.gguf` (creative-writing finetune) and `bartowski/Mistral-Nemo-Instruct-2407-GGUF/Mistral-Nemo-Instruct-2407-Q4_K_M.gguf` (controlled-base) fail the data-skill pipeline at our prompt template. RP-Ink returns `{"effects":[{}]}` (content-empty) deterministically; MN-Instruct fragments behavior across inputs (some non-JSON output, some `{"refused":true}` minimal refusals, some timeouts), and a direct probe with a simpler system prompt confirms it ALSO returns `{"effects":[{}]}` like RP-Ink. The pipeline incompatibility is base-architecture + Q4-quantization + prompt-shape, not RP-Ink-specific. The original "does a creative-writing finetune flex on Rook's voice?" question is parked under three forward-path BACKLOG entries (`creative-finetune-json-fluent-base`, `free-form-prose-pipeline`, `mistral-7b-instruct-fp16-ab`).

## Technical choices

The stack is deliberately small and single-box. Everything runs, and recovers, from a couple of scripts, so the binding constraint is the GPU rather than the infrastructure. Notes on the choices that took real thought:

### Data and persistence

- **SQLite per world, in WAL mode**, one DB file under `~/data/daydream/` and never in the repo. The spine is an **append-only event log**: scene state is reconstructed from events rather than stored as the source of truth, which makes reconnect-replay (`?since=<seq>`) and history essentially free.
- **One `objects` table** holds rooms, characters, things, and prototypes. Containment is a self-referential `location_id` and inheritance a `prototype_id`; everything kind-specific lives in a `properties` JSON column, so a new kind of object rarely needs a migration.
- **Generated images are content-addressed on disk.** The cache key folds the room's seed text and the canonical workflow JSON, so editing either busts the cache and triggers a re-render; a `generated_assets` table is the provenance index over that cache (model, LoRA, prompt, bytes, when).
- **NPC memory is a per-world vector table**: 384-dimension BGE-small embeddings computed on CPU (stored as float32 BLOBs), retrieved by `cosine_similarity * exp(-age_hours / 24)` so salience decays with time. It is SQLite-only by choice; a real vector store (LanceDB) is the upgrade once counts cross ~10K per NPC.
- **Operability without a server.** A world can be archived to a tarball (DB + image cache + manifest) to ship to another box, snapshotted as a DB-only point-in-time copy, or hot-swapped live into the running process. Two staleness axes are enforced so a stale process or world cannot silently mislead: a git build SHA (process vs working tree) and a `MAJOR.MINOR` world version stamped into each DB, checked at boot.
- **Why SQLite and not Postgres:** one box, one writer, and correctness that lives in the event log rather than the database engine. Containers, Postgres, and a Cloudflare port are a later step, not a v0 need.

### GPU, models, and how we fit them

One 20 GB **RTX 4000 SFF Ada** (compute capability 8.9) does every bit of live generation. Two engines sit resident on it: **vLLM** serving **Qwen 2.5 7B Instruct AWQ** (~5 GB) for words, and **ComfyUI** serving **SDXL base + a watercolor LoRA** (~6 GB resident, ~10-12 GB peak) for pictures.

- **An in-process arbiter serializes inference.** Daydream is the only GPU consumer, so the arbiter is a plain `asyncio.Lock` (no cross-process flock needed). Every LLM call and every image render passes through one of exactly two call sites, so the lock has a clean choke point and the two engines never peak at once on the 20 GB card.
- **Model choice is VRAM-driven.** AWQ INT4 weights keep Qwen resident at ~5 GB and leave headroom for SDXL during a render; FP8 weights would cross ~7 GB for marginal gain at the single-request decode latency this game actually generates. AWQ plus Marlin kernels is fast enough for that pattern.
- **Tunings that ride every launch** (inherited from careful experiments on this exact card): `--enforce-eager` (CUDA-graph capture OOM'd here), `--gpu-memory-utilization 0.45` (a ~9 GB ceiling so SDXL fits alongside), `--max-model-len 8192`, and vLLM pinned at `0.19.1`.
- **The optimization we deliberately left off: `--kv-cache-dtype fp8_e4m3`.** On a 14B model it buys a documented +58% decode throughput and ~0.9 GB of VRAM. On Qwen 2.5 7B AWQ it deterministically broke strict-JSON adherence (the model produced one clean turn, then looped garbage tokens); a 7B does not have the parameter headroom to absorb FP8 KV's precision loss. It is gated behind one of: a larger model, calibrated per-channel FP8 scales, or a 7B variant proven to tolerate it. A strict-JSON echo in the live-stack smoke (`tools/arbiter-smoke.py`) exists specifically to catch this class of regression the moment someone re-adds the flag.

The full narrative (VRAM math, everything tried and rejected, what to try later) is in [`docs/gpu-and-models.md`](docs/gpu-and-models.md).

### Web and frontend

- **Vanilla HTML, CSS, and JavaScript** under `web/`, with **no framework and no build step.** FastAPI serves the single-page shell and static assets directly; edit a file, refresh, done. (A framework is a deliberate non-choice for now, not an oversight.)
- **The live channel is a WebSocket** (`/ws`): the server pushes a `state_snapshot` on connect and event frames as the world changes, and a reconnect resumes missed events via `?since=<seq>`, so a dropped socket recovers on its own behind one calm overlay.
- **Two input producers, one bus.** Clicking an object or a verb sends a **structured command** frame (no model call, instant and deterministic); free text goes through the grounded local-LLM parser. The interface is the **"Reading Room" storybook** theme, whose design language, color/type tokens, and a **self-hosted display font (no CDN)** are pinned in [`DESIGN.md`](DESIGN.md) and guarded by a token-drift test.
- **LLM calls go through `litellm`** against vLLM's OpenAI-compatible endpoint, so the same code path can point at Cloudflare / OpenAI / Anthropic later with no rewrite.
- **Asset freshness without a pipeline.** `/assets/*` is served `Cache-Control: no-store` and stamped `?v=<build-sha>`, and an open tab that notices the server's build change reloads itself once into fresh JS/CSS. That closes the "stale tab after a redeploy" class of bug a build step would normally handle.
- **Access is friend-scoped**: a shared-password cookie session behind an outer middleware that, by default, rejects any client outside Tailscale's CGNAT range before any auth machinery runs.

### At a glance

| Layer | Choice |
|---|---|
| Backend | Python 3.10 + FastAPI + websockets, single process tree |
| Persistence | SQLite per world (WAL), append-only event log as the spine; world archive/restore via tarball bundling DB + per-world cache + manifest (`bin/game world archive/restore`), plus fast DB-only point-in-time snapshots (`bin/game world snapshot/snapshot-restore`) and a live in-process hot-swap of the running world (`bin/game world swap`) |
| LLM (optional) | vLLM 0.19.1 serving Qwen 2.5 7B Instruct AWQ, called via `litellm` so the same code path works against vLLM today and Cloudflare / OpenAI / Anthropic later. GGUF support in vLLM is patched-in via `bin/vllm-bootstrap`'s post-install workaround for the upstream gguf packaging-metadata bug — see Release notes above |
| Image gen (optional) | SDXL base + `ostris/watercolor_style_lora_sdxl` via ComfyUI, GPU arbiter shared with vLLM |
| GPU arbiter | `daydream/gpu/arbiter.py` (`asyncio.Lock`); serializes LLM and image-gen on the 20 GB card |
| Object/verb core | One `objects` table (rooms / toons / things / prototypes, `daydream/objects.py`); a closed verb registry + `execute_command` bus (`daydream/verbs.py`), including two-object `give`/`use` (a `valid_iobj_kinds` gate) and state-gated `open`/`read` over free-form `properties.state`; a grounded local-LLM parser for free text (`daydream/parser.py`); an allowlisted world-mutation effect API (`daydream/skills/effects.py`: `narrate`/`set_property`/`spawn_object`/`move_object`). Clicks send structured command frames (no LLM); natural language is parsed locally. See [CLAUDE.md "Objects, verbs, and the command bus"](CLAUDE.md) |
| World content | The canonical world is **The Clockmaker's Loft** (`worlds/clockmakers-loft.json`): five rooms (clocktower / loft / square / workshop / well), NPCs Tace / Bell / Mott reached via `talk` with per-NPC dialogue bindings, and one complete quest loop (read the ledger → take the escapement gear → give it to Tace → use the case-key → open the clock-case) built on two-object verbs (`give`/`use`) + persistent object `state`. `worlds/bunny.json` (Rook / Iris / Bram) is retained as a loader-regression fixture. Room-affordance data skills under `skills/<name>.json` with `context_predicate` room-scoping; `daydream/drift.py` emits per-NPC narrate ticks on the gentle-drift cadence (5 min idle / ~4 min when a human is connected) |
| NPC memory (optional) | Per-world `memories` table at `daydream/memories.py`; sentence-transformers BGE-small on CPU lazy-loaded on first call; embeddings stored as float32 BLOBs; retrieval ranks by `cosine_similarity * exp(-age_hours/24)`; `bin/memory-bootstrap` is the one-time CPU-torch + model install. v0 is SQLite-only; LanceDB is the v1 path once memory counts cross ~10K per NPC |
| Frontend | Vanilla HTML / CSS / JS under `web/` (no framework, no build step); the "Reading Room" storybook UI over a WebSocket, with design language + color/type tokens + a self-hosted display font pinned in `DESIGN.md` and guarded by a token-drift test |
| Auth | Friend-scope: shared password from `.env` on a single port |
| Network access | `DAYDREAM_ACCESS` toggle in `.env`: `tailscale` (default) or `public` |
| Target hardware | Single Linux dev box (RTX 4000 SFF Ada, 20 GB VRAM); designed to port to Cloudflare and containers later |

The full GPU/ML narrative — VRAM math, model selection rationale, what we tried and rejected (the fp8-KV-cache story especially), what to try later — lives in [`docs/gpu-and-models.md`](docs/gpu-and-models.md). [`CLAUDE.md`](CLAUDE.md) is the operator/agent reference for project conventions, lifecycle, the External engines pattern, and the `pretty <filename>` shorthand for promoting image outputs.
