# Voice samples — 2026-05-07 — `hosted_vllm/mistralai/Mistral-Nemo-Instruct-2407`

Rendered via `bin/game voice-samples`. Corpus: `tests/drift/voice/*.json`. Pipeline: `daydream.skills.data.execute_by_name` against `skills/rook.json` in a tmp DB (hermetic).

## Verdict

**Mistral Nemo Instruct (Q4_K_M GGUF) also fails daydream's data-skill pipeline, with different degenerate behaviors than MN-RP-Ink. Voice-quality A/B is therefore moot across both Mistral Nemo legs; the failure is base-architecture + quantization + prompt-shape, not RP-Ink-specific.** Closes the controlled-base hypothesis the spec was written to test.

**Base-architecture axis (Qwen-AWQ-Instruct vs MN-Instruct, both Instruct-tuned).** Qwen 2.5 7B Instruct AWQ produces 5/5 well-formed `narrate` effects under daydream's prompt template (see `2026-05-06-qwen2.5-7b-instruct-awq.md`); MN-Instruct produces 0/5 usable narrates under the same template, with three different failure modes across the corpus: 3/5 emit non-JSON-shaped output that fails `json.loads` (`inner_life` 88 tokens, `small_talk` 74 tokens, `forge_question` timed out at 10 s — the harness's `acompletion_json` raises `LLMUnavailable` and the pipeline emits the foggy fallback); 2/5 emit `{"refused":true}` with no `reason` field, which `safety.parse_refusal` resolves to the default reason text "the dream won't hold that thought" (`greeting` 8 tokens, `open_invitation` 8 tokens). A direct probe at vLLM with a simpler system prompt confirmed MN-Instruct ALSO returns `{"effects":[{}]}` (the same content-empty pattern as MN-RP-Ink) when the prompt is short and clear; the harness's longer prompt template fragments behavior across inputs.

**Finetune axis (MN-Instruct vs MN+RP-Ink, controlled-base).** Both Mistral Nemo Q4 legs fail to produce usable narrate; the failure modes differ in shape (RP-Ink: deterministic 5/5 `{"effects":[{}]}`; Instruct: varied per input) but the conclusion is the same — **the data-skill pipeline does not work on Mistral-Nemo + 12B Q4 + this prompt template, regardless of finetune.** The original 04-24 question ("does a creative-writing finetune flex on Rook's voice?") remains unanswered, but the answer space has shrunk: with both Nemo legs out, the question can only be answered by (i) a creative-writing finetune of a JSON-fluent base (Qwen, Llama 3.x) at fitting quantization, none of which is currently published in a drop-in form, OR (ii) a daydream pipeline change that accepts free-form prose and post-parses, OR (iii) a Mistral *7B* model (smaller, less Q4-sensitive, fits BF16 in our budget without GGUF). Paths (i) and (iii) are operator research; (ii) is an architectural change.

**Tic-detection probe heuristic (criterion 4 of this spec).** Running `tests/test_voice_baseline.py`'s `_parse_narrate_sections` and `_opener_of` against this capture yields 2 distinct openers across 5 sections (3× FOGGY fallback, 2× default-refusal text). The probe heuristic fails as expected: the captured text is system-emitted fallback prose, not Rook responses. The probe is NOT extended to parametrize over this file (criterion 4 explicitly preserves the AWQ-track scope of the probe).

**vLLM flags note.** Same as the MN-RP-Ink leg: `--enforce-eager`, `--gpu-memory-utilization 0.45`, `--max-model-len 4096` (the documented GGUF-specific deviation; 12B Q4 KV-cache budget at 0.45 mem-util has the same 7248 ceiling as the RP-Ink leg). `--served-model-name mistralai/Mistral-Nemo-Instruct-2407` for a clean filename slug. The `bin/vllm-bootstrap` gguf-`__version__` patch (commit 210bb51) applied unmodified — confirms the patch generalizes beyond the RP-Ink leg.

## Config

| setting | value |
|---|---|
| `base_url` | `http://localhost:8000/v1` |
| `enforce_eager` | `true` |
| `gpu_memory_utilization` | `0.45` |
| `kv_cache_dtype` | `fp16 (auto; see docs/gpu-and-models.md)` |
| `max_model_len` | `4096` |
| `model` | `hosted_vllm/mistralai/Mistral-Nemo-Instruct-2407` |

## Metrics

| prompt | tokens in | tokens out | wall seconds |
|---|---:|---:|---:|
| `forge_question` | — | — | 10.025 |
| `greeting` | 1156 | 8 | 6.398 |
| `inner_life` | 1163 | 88 | 9.185 |
| `open_invitation` | 1159 | 8 | 6.478 |
| `small_talk` | 1160 | 74 | 8.759 |

## Samples

### forge_question

**Player input:**

> what are you making today

**Narrate:**

> The dream is foggy right now; that thought slips away.

### greeting

**Player input:**

> hello

**Narrate:**

> the dream won't hold that thought

### inner_life

**Player input:**

> what do you think about while you work

**Narrate:**

> The dream is foggy right now; that thought slips away.

### open_invitation

**Player input:**

> tell me something

**Narrate:**

> the dream won't hold that thought

### small_talk

**Player input:**

> has it been quiet today

**Narrate:**

> The dream is foggy right now; that thought slips away.
