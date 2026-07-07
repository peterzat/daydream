# Prompt inventory & tuning ledger

Every prompt surface in daydream, what gates it, and which tuning levers are
deliberately unpulled. Written from the 2026-07-02 prompt audit; update this
table when adding a surface or moving one. The runtime feed for prompt/latency
analysis is the `daydream.llm.usage` logger (one INFO line per LLM call:
`purpose`, model, gate wait, call latency, token counts) — grep the server log
for `llm purpose=` to profile.

## Text surfaces

| # | Purpose tag | Surface | Location | Temp | Shape | Gated by |
|---|-------------|---------|----------|------|-------|----------|
| 1 | `parser` | Grounded command parse | `daydream/parser.py` `SYSTEM` + `_user_prompt` | 0.0 | free text → strict-JSON `{verb, dobj_id, iobj_id, args}` against closed verbs + in-scope ids | `tests/drift/test_parser_grounding.py` (17-case corpus, tier_long); zero-LLM walkthrough spy |
| 2 | `dialogue` | Player-action affordances (2nd person) | `daydream/skills/data.py` `_DISPATCHER_SYSTEM` | 0.0 | narrate the player's own action; strict-JSON effects list, `DEFAULT_KINDS` | voice baselines (`tests/test_second_person.py`, `test_voice_baseline.py`) |
| 3 | `dialogue` | NPC dialogue system (3rd person) | `daydream/skills/data.py` `_dialogue_system` | 0.0 | voice the NPC by name; player is "you" only inside quotes | `tests/test_dialogue_voice.py`, `test_npc_voice.py`; voice-samples harness |
| 4 | `dialogue` | Per-world NPC templates | world envelopes (`worlds/*.json` `dialogue.prompt_template`, Jinja) | 0.0 | "You are <NPC>… memories… They say: {{player_input}}" | same as #3; templates are authored world DATA |
| 5 | `drift` | Ambient NPC beats | `daydream/drift.py` `_DRIFT_SYSTEM_PROMPT` + `_DRIFT_USER_TEMPLATE` | 0.0 | one 8–16-word third-person beat, JSON `{"narrate"}` | drift-voice samples harness (`bin/game drift-samples`), canned-pool fallback |
| 6 | `growth` | Dreamseed room composition | `daydream/growth.py` `GROWTH_SYSTEM` + `_user_prompt` | 0.0 (450 tok / 30 s) | one room inside authored boundaries; strict JSON; never sees ids/directions | `tests/drift/test_growth_compose.py` goldens (tier_long) |
| 7 | `retell` | Narration retell (scoped rung) | `daydream/retell.py` `_system_prompt` (built from world `voice`) | **0.8** | rephrase one line; nouns/digits preserved; JSON `{"text"}` | `tests/drift/test_retell_probe.py` golden (tier_long) + validation gates in code |
| 8 | `examine` | Lazy examine of spawned objects | `daydream/verbs.py` `_EXAMINE_SYSTEM` | 0.0 | 1–2 soft sentences, JSON `{"text"}`, cached forever after | `tests/test_generative.py` |
| 9 | `journal` | Dream-journal recap on leave | `daydream/journal.py` `JOURNAL_SYSTEM` + `_user_prompt` | 0.0 (220 tok / 20 s) | 2–3 past-tense second-person sentences over the toon's own events; strict JSON `{"entry"}`; refusal/length/banlist gates; skip-not-block | `tests/test_journal.py` (mocked); tier_long quality probe; `DAYDREAM_JOURNAL_ENABLED` kill switch |
| 10 | — (offline) | World-bootstrap authoring | `daydream/llm/bootstrap.py` `_SYSTEM_PROMPT` | 0.0 | whole-world envelope authoring; DEPRECATED path (keyless `world load` is canonical) | envelope validator |

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
- **Temperature**: only retell runs warm (0.8, for variety on repeat tellings). Raising
  parser/dialogue temperature trades JSON reliability for variety on a 7B — the
  JSON-adherence probe (`tests/drift/test_llm_json_adherence.py`) is the canary.
