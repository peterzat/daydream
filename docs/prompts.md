# Prompt inventory & tuning ledger

Every prompt surface in daydream, what gates it, and which tuning levers are
deliberately unpulled. Written from the 2026-07-02 prompt audit and updated
for the 2026-09-26 pivot (surfaces 14-16 are new; 3-9 changed); update this
table when adding a surface or moving one. The runtime feed for prompt/latency
analysis is the `daydream.llm.usage` logger (one INFO line per LLM call:
`purpose`, model, gate wait, call latency, token counts) — grep the server log
for `llm purpose=` to profile.

## Text surfaces

| # | Purpose tag | Surface | Location | Temp | Shape | Gated by |
|---|-------------|---------|----------|------|-------|----------|
| 1 | `parser` | Grounded command parse | `daydream/parser.py` `SYSTEM` + `_user_prompt` | 0.0 | free text → strict-JSON `{verb, dobj_id, iobj_id, args}` against closed verbs + in-scope ids | `tests/drift/test_parser_grounding.py` (17-case corpus, tier_long); zero-LLM walkthrough spy |
| 2 | `dialogue` | Player-action affordances (2nd person) | `daydream/skills/data.py` `_DISPATCHER_SYSTEM` | 0.0 | narrate the player's own action; strict-JSON effects list, `DEFAULT_KINDS` | voice baselines (`tests/test_second_person.py`, `test_voice_baseline.py`) |
| 3 | `dialogue` | Legacy NPC dialogue system (3rd person) | `daydream/skills/data.py` `_dialogue_system` | 0.0 | voice the NPC by name; player is "you" only inside quotes. Only format-1 worlds (bunny) still use it | `tests/test_dialogue_voice.py`, `test_npc_voice.py`; voice-samples harness |
| 4 | `dialogue` | Legacy per-world NPC templates | format-1 envelopes (`worlds/bunny.json` `dialogue.prompt_template`, Jinja) | 0.0 | "You are <NPC>… memories… They say: {{player_input}}" | same as #3 |
| 5 | `drift` | Ambient NPC beats (voice-less NPCs only) | `daydream/drift.py` `_DRIFT_SYSTEM_PROMPT` + `_DRIFT_USER_TEMPLATE` | **0.8** | one 8–16-word third-person beat, JSON `{"narrate"}`. NPCs with authored pools never take it (authored-first, surface 15) | drift-voice samples harness, canned-pool fallback |
| 6 | `growth` | Dreamseed room composition | `daydream/growth.py` `GROWTH_SYSTEM` + `_user_prompt` | **0.7** (`GROWTH_TEMPERATURE`; 450 tok / 30 s) | one room inside authored boundaries; strict JSON; never sees ids/directions | `tests/drift/test_growth_compose.py` goldens (tier_long, fingerprinted at 0) |
| 7 | `retell` | Narration retell (scoped rung) | `daydream/retell.py` `_system_prompt` (built from world `voice`) | **0.8** | rephrase one line; nouns/digits preserved; JSON `{"text"}` | `tests/drift/test_retell_probe.py` golden (tier_long) + validation gates in code |
| 8 | `examine` | Lazy examine of spawned objects | `daydream/verbs.py` `_EXAMINE_SYSTEM` | **0.6** (`EXAMINE_TEMPERATURE`) | 1–2 soft sentences, JSON `{"text"}`, cached forever after (so warmth never makes one thing read two ways) | `tests/test_generative.py` |
| 9 | `journal` | Dream-journal recap on leave | `daydream/journal.py` `JOURNAL_SYSTEM` + `_user_prompt` | **0.5** (`JOURNAL_TEMPERATURE`; 220 tok / 20 s) | 2–3 past-tense second-person sentences over the toon's own events; strict JSON `{"entry"}`; refusal/length/banlist gates; skip-not-block | `tests/test_journal.py` (mocked); tier_long quality probe (pins 0); `DAYDREAM_JOURNAL_ENABLED` kill switch |
| 10 | — (offline) | World-bootstrap authoring | `daydream/llm/bootstrap.py` `_SYSTEM_PROMPT` | 0.0 | whole-world envelope authoring; DEPRECATED path (keyless `world load` is canonical) | envelope validator |
| 14 | `dialogue` | **Grounded voice-sheet dialogue** (SPEC 2026-09-26) | `daydream/dialogue.py` `build_prompt` (system + sectioned user) | **0.7** (`DAYDREAM_DIALOGUE_TEMPERATURE`; n-best `DAYDREAM_DIALOGUE_NBEST`=2 in parallel) | state injected: voice sheet + pronouns, wants, place/time/who is here, the closed cast, what the NPC knows (deeds first), relationship + recent exchanges, openings to avoid, open beats; JSON-schema `{"line", "advance": enum}`; reranked for pronoun canon, POV, opener novelty; an advanced beat speaks its AUTHORED line | `tests/test_dialogue.py` (mocked); model-eval canon + dialogue suites (docs/model-eval/); tier_long refusal probe |
| 15 | `drift` | **Authored-line variation** (authored-first drift) | `daydream/drift.py` `_VARY_SYSTEM` + `validate_variation` | **0.8** (`DAYDREAM_DRIFT_VARY_PROB`=0.3 of ticks) | lightly vary ONE authored line; length 0.6-1.4x, no quotes, no new capitalized names; the authored line stands on any miss | `tests/test_drift.py` |
| 16 | `director` | **Storylet ranking** (background arbiter class) | `daydream/director.py` `_SYSTEM` + `_context` | 0.7 (40 tok / 20 s) | choose ONE id from the eligible authored storylets/arrivals given a compact village view; JSON-schema enum; an out-of-set answer is an outage (seeded choice stands) | `tests/test_story.py` (mocked); `DAYDREAM_DIRECTOR_LLM` kill switch |

## Image surfaces

| # | Surface | Location | Shape | Gated by |
|---|---------|----------|-------|----------|
| 11 | Room/ephemeral render prompt | room seed text + `WHIMSY_PROMPT_SUFFIX` (`daydream/images/client.py`) | `"<seed> <suffix>"` into the workflow's positive-prompt node | `tests/test_whimsy_prompt_suffix.py` (suffix ↔ WHIMSY.md); `tests/drift/test_image_perceptual.py` dHash goldens (7 anchors, tier_long) |
| 12 | Negative prompt + sampler params | `daydream/images/workflows/painterly_room.json` | fixed negative list; SDXL base + watercolor LoRA 0.85; 1024×384, 22 steps, cfg 5.5, dpmpp_2m/karras | the workflow JSON is folded into every cache key AND the dHash goldens |
| 13 | Toon portrait render prompt | `appearance_seed` + `PORTRAIT_PROMPT_SUFFIX` (framing clause + WHIMSY suffix, `daydream/images/client.py`) | `"<appearance> <clause + suffix>"` into `painterly_portrait.json` (640×768, face/anatomy negatives, same checkpoint + LoRA) | `tests/test_whimsy_prompt_suffix.py` (clause ↔ WHIMSY.md); `portrait_*` dHash anchors (tier_long); framing A/B ratified 2026-07-07 |

## Duplication map (known, tolerated)

- **Tone boilerplate** ("cozy, soft, painterly, Spiritfarer / A Short Hike-adjacent, no
  modern tech, no harsh edges…") is hand-restated in surfaces 2, 3, 5, 6, 8, 10 and in
  every world template. Deliberately NOT extracted to a shared constant: each restatement
  is tuned to its surface, and every one is pinned by its own baseline/golden — a shared
  edit would cascade re-ratifications. Revisit only alongside a planned re-ratification.
- **`FOGGY_TEXT`** (the LLM-outage line) is now a single constant in
  `daydream/llm/client.py`, imported by ws/data/growth.

## Tuning levers deliberately not pulled (and their real cost)

- **`WHIMSY_PROMPT_SUFFIX` edits**: NOT folded into image cache keys (old art stays
  valid) but every NEW render and all 7 aesthetic dHash goldens follow it → a suffix
  edit is a tier_long re-ratification event. Change it in WHIMSY.md + client.py together.
- **Workflow JSON edits** (negative prompt, steps, cfg, sampler, resolution, LoRA):
  folded into every cache key → busts ALL room art AND re-ratifies the goldens. Use
  `bin/game image-test --lora/--model` for A/B before committing.
- **Prompt-body rewrites** on surfaces 1–8: each is baseline-gated; treat a rewrite as
  a mini-ratification turn (run the relevant harness, re-golden consciously).
- **Temperature** (revised 2026-09-26): every prose surface runs warm (dialogue 0.7,
  drift 0.8, growth 0.7, examine 0.6, journal 0.5, retell 0.8); only the parser stays
  at 0. The old claim that warmth trades JSON reliability no longer holds: the Qwen3.5
  9B parsed 20/20 JSON at 0.8 in the bake-off, and the dialogue surface's JSON schema
  constrains its shape outright. The JSON-adherence probe
  (`tests/drift/test_llm_json_adherence.py`) stays the canary; tier_long probes that
  fingerprint a surface pin temperature 0 by monkeypatch.
