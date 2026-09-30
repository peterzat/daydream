# Jev (TypeSafe AI): research notes

Researched 2026-09-30. Everything below comes from public pages; no call was made with the key.
The docs serve raw markdown at `https://docs.typesafe.ai/<page>.md`, and the full index is at
https://docs.typesafe.ai/llms.txt. Copies of the pages I read are in `scratchpad/docs/`, and
shallow clones of the official repos are in `scratchpad/gh-*`.

## 1. What it is

- Jev is TypeSafe's "first System One model": a hosted, proprietary decision model. It is **not an LLM and does not generate text**. You send a `state` (text or JSON) and a map of typed questions. It returns typed answers with probabilities.
  Sources: https://typesafe.ai, https://docs.typesafe.ai/concepts/system-one.md, https://docs.typesafe.ai/introduction/coding-agents.md
- There are three question types ("primitives"):
  - **Choice**: pick one of up to 255 named options. Returns the chosen option, a probability for every option, and a confidence.
  - **Score**: an ordered rubric of 2 to 10 levels. Returns an expected level, per-level probabilities and a confidence.
  - **Noul**: yes/no. Returns P(yes) in [0,1], with no separate confidence.
  Source: https://docs.typesafe.ai/api.md
- **"Typesafe" means** the output is always one of the values you declared. They say it is "type-safe by construction" and "never makes type errors". It is not a JSON-schema generator. You cannot ask for free strings or arbitrary schemas; the only output shapes are Choice, Score and Noul.
  Sources: https://docs.typesafe.ai/concepts/how-to-build-with-system-one.md, https://typesafe.ai/blog/introducing-system-one-models-and-jev
- Training is "RLCD" (Reinforcement Learning for Calibrated Decisions), aimed at calibrated probabilities. Wikipedia quotes the company as saying it is "transformer-based and trained exclusively on synthetic data". The architecture, parameter count and weights are not published. MindStudio describes it as non-autoregressive, with all outputs coming from one pass.
  Sources: https://docs.typesafe.ai/introduction/machine-learning-primer.md, https://en.wikipedia.org/wiki/Jev_(AI_model), https://www.mindstudio.ai/blog/jev-system-one-model-launch
- Company: San Francisco, founded 2024 by Diogo Almeida (CEO, ex-OpenAI RLHF/InstructGPT), Erik Gafni and Sasha Sheng. $40M seed led by DCVC. Early access opened 2026-09-15.
  Source: https://en.wikipedia.org/wiki/Jev_(AI_model)
- The claimed use cases are routing, classification, scoring, guardrails, verification, and "real-time applications". The launch demos include Minecraft and simulator-based driving and drone runs.
  Sources: https://typesafe.ai/blog/introducing-system-one-models-and-jev, https://www.mindstudio.ai/blog/jev-system-one-model-launch

## 2. API

- **Endpoint:** `POST https://api.typesafe.ai/v1/systemone`
- **Auth:** `Authorization: Bearer <API_KEY>` and `Content-Type: application/json`.
  Sources: https://docs.typesafe.ai/api.md, https://docs.typesafe.ai/introduction/quickstart.md
- **Other endpoint:** `GET https://api.typesafe.ai/v1/models` returns `{"models":[{"name","description","release_date"}]}` and currently lists only the aliases. The SDK source has exactly two paths, `/v1/systemone` and `/v1/models`.
  Sources: https://docs.typesafe.ai/models.md; `gh-typesafe-sdk-python/src/typesafe_sdk/_core/constants.py`
- **Request:**

  ```json
  {"state": "<string|object|array>", "model": "jev-latest",
   "questions": {"<your_id>": {"type": "choice", "instructions": "...", "criteria": {"optA": "desc", "optB": null}},
                 "<id2>": {"type": "noul", "instructions": "...", "criteria": {"true": "...", "false": "..."}},
                 "<id3>": {"type": "score", "instructions": "...", "criteria": ["lvl0", "lvl1", "lvl2"]}}}
  ```

  - `instructions` and criteria values can be strings, objects or arrays. Structured instructions can put data in named fields and refer to it in backticks.
  - The question id is never shown to the model. **Option names and their descriptions are both sent to the model.**
  Sources: https://docs.typesafe.ai/api.md, https://docs.typesafe.ai/primitives/choice.md
- **Response:**

  ```json
  {"model": "jev-1.13.0",
   "answers": {"<id>": {"type": "choice", "choice": "...", "probabilities": {...}, "confidence": 0.81}, ...},
   "usage": {"input_tokens": N, "output_tokens": M}}
  ```

  - A Noul answer is `{"type":"noul","noul":0.95}`. A Score answer adds `score`, `legend`, `probabilities` and `confidence`.
  - Choice confidence is computed as `(n*max_p - 1)/(n - 1)`, clamped to [0,1]. With many options, a moderate winning probability therefore still reads as fairly confident.
  - The response header `x-typesafe-request-id` identifies the call.
  Sources: https://docs.typesafe.ai/api.md, https://docs.typesafe.ai/confidence.md; SDK constants
- **Errors:**

  | Status | Meaning |
  | - | - |
  | 401 | Bad key |
  | 422 | Validation failure |
  | 429 | Rate limit (honor `retry-after` / `retry-after-ms`) |
  | 529 | Overloaded |

  The SDK maps 400/401/403/404/422/429 to typed errors and has no special 402 class.
  Sources: https://docs.typesafe.ai/api.md; `gh-typesafe-sdk-python/src/typesafe_sdk/_core/errors.py`
- **SDKs:**
  - Python: `pip install typesafe-sdk`, v0.7.2, Python >= 3.10, MIT, deps `httpx2` + `pydantic` + `tenacity`. It provides `TypeSafeClient` and `AsyncTypeSafeClient`, reads `TYPESAFE_API_KEY`, `TYPESAFE_BASE_URL` and `TYPESAFE_DEFAULT_MODEL`, defaults to `jev-latest`, and has a default 10 s timeout per attempt with retries on by default.
  - JS: `@typesafe-ai/sdk`.
  Sources: https://pypi.org/pypi/typesafe-sdk/json, https://docs.typesafe.ai/sdk/python.md, https://docs.typesafe.ai/sdk/python/api/constants.md, https://github.com/typesafe-ai/typesafe-sdk-python
- **Not OpenAI-compatible:** there is no chat/completions endpoint. LiteLLM supports it only as a pass-through of the native format and says streaming is "Not offered by the TypeSafe API".
  Source: https://docs.litellm.ai/docs/pass_through/typesafe
- **No streaming and no async batch API.** "Batching" in their docs means many questions over one state in a single call. Their cookbook reports 13 questions in one call being "12.2x cheaper and 10.0x faster" than 13 separate calls, with no change in answers.
  Source: https://docs.typesafe.ai/cookbooks/parallel_questions.md
- **Other access routes:**
  - OpenRouter serves the same `/v1/systemone` shape at `https://openrouter.ai/api/v1/systemone`. It uses an OpenRouter key, and the SDK works by overriding the base URL.
  - Vercel AI Gateway (`typesafe-ai/jev`).
  - Pydantic AI has a TypeSafe model page.
  Sources: https://openrouter.ai/docs/guides/community/typesafe-sdk, https://community.vercel.com/t/ai-gateway-typesafe-ai-jev-returns-free-tier-429-despite-paid-credits/49935, https://pydantic.dev/docs/ai/models/typesafe/
- **Useful for testing:** the official `system-one-adapter-python` is a "Drop-in TypeSafeClient replacement backed by LLM APIs". It accepts any OpenAI-compatible endpoint through `OpenAIProvider(model, base_url=...)`, so the same question set can run against local vLLM/Qwen for a like-for-like comparison.
  Source: https://github.com/typesafe-ai/system-one-adapter-python
- **Key format:** not documented anywhere official. The SDK tests use the placeholder `ts_live_private`, and a third-party guide shows `ts_...`. Neither confirms or rules out `apikey_<hex>_<hex>`.
  - The unaffiliated reseller jevtypesafeai.com ("Not affiliated with or endorsed by TypeSafe AI", CODEFASHION TECH LTD) issues `jv_live_` keys against its own `/api/v1/decide`, so an `apikey_` key is not from that reseller.
  - Keys are created at console.typesafe.ai/keys or /settings/keys.
  Sources: https://jevtypesafeai.com/pricing, https://apidog.com/blog/jev-api-key/, https://docs.typesafe.ai/introduction/quickstart.md

## 3. Balance and credits

- **There is no documented balance, credit or usage endpoint.** None appears in the API reference, the SDK source or the llms.txt index.
- A third-party probe with a real key reports that `/v1/credits`, `/v1/balance`, `/v1/usage`, `/v1/billing` and `/v1/organization` all return 404.
- The same probe reports that an exhausted account gets **HTTP 402** with `{"detail":{"error_type":"billing_error","message":"Your organization has no available TypeSafe API credits..."}}`.
- Billing is managed only in the console at `console.typesafe.ai/settings/billing`.
  Source: https://github.com/kunchenguid/quota-axi/issues/291
- To track spend yourself: each response's `usage.input_tokens` times $0.042/Mtok (output is free). OpenRouter's variant also returns `cost` in usage.
  Source: https://openrouter.ai/docs/guides/community/typesafe-sdk
- **Credits and signup:**
  - Purchased credits "expire on the earlier of the end of the Term and the date that is 12 months after the purchase date", and unused prepaid amounts are not refunded.
  - A $5 free credit (about 120M tokens) was offered at launch on 2026-09-20/21. Signups were paused on 2026-09-22 and reopened on 2026-09-27 with free credit suspended for new users.
  Sources: https://typesafe.ai/legal/mca, https://aifront-page.com/typesafe-ai-reopens-jev-sign-ups-free-credit-suspended/

## 4. Pricing, limits, latency, models

- **Model:** `jev-1.13.0` is the only one. The aliases `jev-latest` and `jev-preview` both point to it. Aliases move on release, so pin the versioned id if you tune thresholds.
  Source: https://docs.typesafe.ai/models.md
- **Price:** $42 per billion input tokens ($0.042/Mtok). Output tokens are free.
  Source: https://docs.typesafe.ai/models.md
- **Rate limits (official):** 100K tokens/s and 40 requests/s, "adjusting dynamically" and able to change without notice. Third-party pages quote 250K tok/s and 1,200 rpm; those numbers do not match the official docs.
  Sources: https://docs.typesafe.ai/models.md, https://apidog.com/blog/jev-api-key/
- **Context:** 64k tokens per request (state plus all questions). 32k for the state plus the single longest question. Choice allows up to 255 options; Score up to 10 levels.
  Sources: https://docs.typesafe.ai/models.md, https://docs.typesafe.ai/api.md
- **Input:** text or JSON only. English is best, and other languages are weaker.
  Source: https://docs.typesafe.ai/models.md
- **Latency claims:** "End-to-end response time is 70ms-500ms" and "Most queries complete in about 100 ms". One vendor-run test measured a 140 ms server-side median, but only 1.7-3.9x faster than LLMs end to end once network time is included.
  Sources: https://typesafe.ai/blog/introducing-system-one-models-and-jev, https://docs.typesafe.ai/concepts/how-to-build-with-system-one.md, https://aimlapi.com/blog/what-is-jev
- **Customization:** no fine-tuning or LoRA. You steer it only through `state`, `instructions` and `criteria`.
  Source: https://docs.typesafe.ai/models.md

## 5. Data handling

- **Training:** "We will not train or fine tune any artificial intelligence or machine learning models on your prompts or other Input" (Privacy Policy). The MCA says they will not train on Customer Data "without Customer's prior consent". The models page says "Jev is not trained on customer requests or responses."
  Sources: https://typesafe.ai/legal/privacy-policy, https://typesafe.ai/legal/mca, https://docs.typesafe.ai/models.md
- **Retention: no concrete period is given.**
  - The Privacy Policy keeps data "as long as reasonably necessary...".
  - The DPA says "as long as necessary taking into account the purpose".
  - The MCA says they have "no obligation to store or retain Customer Data and may delete [it] at any time".
  - Zero data retention (ZDR) exists for **enterprise customers only**, through sales@typesafe.ai.
  Sources: https://typesafe.ai/legal/data-processing, https://docs.typesafe.ai/legal.md
- **Subprocessors:** listed at https://trust.typesafe.ai/subprocessors, which is rendered client-side and could not be read. Processing location is not stated.
- **Age:** the Privacy Policy says they do not knowingly collect personal data from children under 18.
- **Prompt injection:** the jaggedness page says state "is data, and jev-1.13 does not treat it as hostile by default... an injected instruction... can move the answer".
  Source: https://docs.typesafe.ai/model-jaggedness/jev-1.13.md

## 6. Benchmarks and accuracy claims

- **Vendor WorkflowEvals.** The labels are the average of GPT-6 Astra and Claude Fable 5.1 at high thinking, so the score is agreement with frontier LLMs, not ground truth. Jev's results by workflow:

  | Workflow | Jev agreement | Jev cost/case | Jev time/case | Comparison |
  | - | - | - | - | - |
  | Security incidents | 61.7% | $0.0001 | 0.3 s | Opus 5: 66.2%, $0.0574, 15.1 s |
  | Agent-trace | 71.6% | not captured | not captured | Opus 5: 75.2% |
  | Invoice processing | 61.8% | not captured | not captured | Sol: 79.1%, Opus 5: 78.4% |
  | Customer service | 76.0% | not captured | not captured | Sol: 78.3%, Opus 5: 72.4% |

  Headline claims: "193.6x faster, 444.6x cheaper", and "40x-200x faster for the same levels of frontier intelligence". Wikipedia notes that the comparisons were made by TypeSafe's own team, with "possible bias".
  Sources: https://evals.typesafe.ai/, https://github.com/typesafe-ai/WorkflowEvals, https://typesafe.ai, https://en.wikipedia.org/wiki/Jev_(AI_model)
- **Vendor-adjacent test by AI/ML API (they host it), 300 examples per task:**
  - Banking77 intent routing (77 classes): Jev 78.3% vs Opus 5.5 85.7%.
  - TweetEval moderation: Jev had the best F1, 0.696.
  - HelpSteer2 quality rating: Jev was weakest, Spearman 0.394.
  - At confidence >= 0.9, accuracy was 94-96%, but 12 of 197 routing answers at >= 0.9 were wrong.
  Source: https://aimlapi.com/blog/what-is-jev
- **Independent paper:** crash-narrative coding (27-question schema, about 500K narratives). Jev reached F1 0.908 against human labels. One frontier LLM was 0.059 F1 better, and the other was indistinguishable. Recalibration cut calibration error 3.3x, which means raw calibration was not perfect.
  Source: https://arxiv.org/abs/2609.24052
- **Calibration evidence:** there is no public paper, reliability curve or ECE figure, and Hacker News commenters asked for one.
  Source: https://agentconn.com/blog/jev-typesafe-new-agent-layer-if-calibration-holds/ (summarized in search results)
- **Vendor's own function-calling cookbook:** natural-language requests mapped to function names plus closed-set arguments, with per-call confidences of 0.53-1.00. There is no aggregate accuracy figure.
  Source: https://docs.typesafe.ai/cookbooks/function_calling.md
- **Known weaknesses (vendor's "jaggedness" page):**
  - Literal reading, so negations and implied conditions are taken at face value.
  - Counting, numbers and date comparison.
  - Multi-hop indirection.
  - Accuracy drops with irrelevant state ("context rot").
  - Adversarial content.
  - A Noul's P(yes) and 1 - P(not) do not add up (0.72 + 0.47 = 1.19 in their example).
  - "not trained to generate text".
  Source: https://docs.typesafe.ai/model-jaggedness/jev-1.13.md

## 7. Fit for daydream's surfaces

**Policy flag first.** CLAUDE.md's generation policy says the live game makes "NO calls to any cloud LLM", and the prod unit has loopback-only IP egress. Jev at runtime would be a hosted third-party model call, so it is a policy change and not just an integration. An offline, dev-only evaluation is a separate question for the operator. CLAUDE.md also says "no API key anywhere (including dev tooling and tests)".

- **(a) Command parser: good shape fit.**
  - Model it as several questions over one state in one call:
    - Choice over the closed verb set plus `none`.
    - Choice over the in-scope ids plus `none`. Option keys are sent to the model, so use readable keys or put the name in the description.
    - Choice for triage `kind`.
    - Noul for "is this a question about the game".
  - Costs about $0.00002 per 500-token call.
  - Weak spots:
    - It cannot echo "the target as typed" or split a command chain, because there is no string output.
    - It reads literally.
    - Banking77-style routing is about 7 points behind frontier LLMs.
    - Network latency is added on top of the claimed ~100 ms server time.
    - Chained commands would each need their own Choices.
- **(b) Promise judge: good fit.** Use one Noul per draft in a single request (fan-out), with criteria for true and false. The threshold has to be tuned on a labeled set, and a Noul threshold should not be reused on a Choice. Watch the literal-reading and adversarial-state caveats, since player text could argue for its own classification.
- **(c) NPC dialogue: misfit for the "say" text**, because Jev cannot write one or two sentences. It could pick `gesture` and the `advance` enum, or pick among authored or pre-drafted lines. That matches the "select, don't write" stance, but the local model is still needed for improvised replies.
- **(d) Sentence validation and rewriting:** validation fits (Noul or Score, e.g. "breaks canon?", "second person?", "names someone not in context?"). Rewriting is a misfit: no text generation.

## Unknowns (not found)

- The official API key format; nothing confirms `apikey_<hex>_<hex>`.
- A balance or credits endpoint (none found; 402 `billing_error` reportedly signals exhaustion).
- Whether `GET /v1/models` or failed or 422 calls are billed.
- A concrete retention period for request content, any logging of state or questions for non-enterprise accounts, processing region, and the subprocessor list (the trust page did not render).
- Per-account rate limits for a small or new account (the official limits are "dynamic").
- Public calibration metrics (ECE or reliability curves).
- Parameter count and architecture.
- Accuracy on text-adventure-style parsing or grounding. No game or IF benchmark exists beyond the Minecraft demo claim.
- Whether option order inside a Choice affects answers, and determinism across repeated calls. The parallel-questions cookbook reports std dev 0.0 for some questions and small noise for others.
- Minimum purchase or top-up amounts.

## Assessment: how best to test it (5 lines)

1. Probe auth with `GET /v1/models` (lists aliases, no questions sent); read the balance only in the console, and treat a 402 `billing_error` as "out of credit".
2. Run offline in dev only, on synthetic or held-out eval strings (the existing `triage`/`promise` model-eval suites), not friends' text, since retention is unspecified and ZDR is enterprise-only.
3. Parser: one request per line, with Choice(verb+none), Choice(in-scope ids+none), Choice(kind) and Noul(question); score through the runtime's reader against Qwen's held-out numbers, logging latency including network.
4. Promise judge: one Noul per draft in a single call; build a reliability table (confidence bucket vs correctness) to test the calibration claim rather than trusting it.
5. For a like-for-like comparison, run the same question schema through `system-one-adapter` pointed at local vLLM; skip dialogue text and rewriting, which Jev cannot do. Any runtime adoption is a generation-policy change for the operator.
