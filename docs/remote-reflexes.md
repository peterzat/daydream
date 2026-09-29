# Remote reflexes: generation off this box (a seam, not a feature)

Status: **seam only (SPEC 2026-09-27 criterion 23). The shipped runtime is
local-only.** Nothing here is turned on. Turning it on is a
generation-policy change (see "What turning it on takes"), made
deliberately and recorded in CLAUDE.md, never a config flip in passing.

## Why it exists

The GPU box is often lent to other GPU work. Today that means the
village sleeps. A remote "reflex" backend would let it stay awake on
someone else's GPU for the few things the runtime generates:

- the parser's grounding
- off-script dialogue
- journals
- grown-room composition
- portraits and grown-room art

Everything that carries story is authored in advance and needs no model at
all (docs/REFLEXES.md). Cloudflare Workers AI is the natural candidate:
the instance's domain already lives there, and it serves open-weight models (Qwen,
Llama, Flux, SDXL) behind one account.

## What the code already allows

**LLM** (`daydream/llm/client.py`, `daydream/config.py`):

- The endpoint is configuration: `DAYDREAM_LLM_BASE_URL`, `DAYDREAM_LLM_MODEL`
  and `DAYDREAM_LLM_API_KEY`, through litellm's OpenAI-compatible client.
- `config.llm_is_local()` decides the gate. A loopback or tailnet endpoint
  takes the GPU arbiter's slots, as today. Any other endpoint gets its own
  semaphore (`DAYDREAM_REMOTE_LLM_CONCURRENCY`, default 3), because the
  arbiter gates only this box's card.

**Images** (`daydream/images/client.py`):

- `DAYDREAM_IMAGE_BACKEND` (default `comfyui`) picks a backend from
  `IMAGE_BACKENDS`, a registry of coroutines taking `RenderParams`
  (prompt, negative, width, height, seed, steps) and returning image bytes.
  `render_params(workflow)` reads those from the ComfyUI workflow, so every
  backend sees the same request.
- `render_slot()` is what a render holds: the arbiter's exclusive slot for the
  local backend, nothing for a remote one.
- A non-default backend's identity (`DAYDREAM_IMAGE_BACKEND` plus
  `DAYDREAM_IMAGE_BACKEND_MODEL`) folds into the image cache key, so remote
  art never overwrites or masquerades as the graded local art. The default's
  keys are byte-identical to before (tests/test_backend_seam.py).
- No remote backend is registered. `DAYDREAM_IMAGE_BACKEND=workers-ai` today
  fails cleanly ("not available in this build").

## The Workers AI calls (for the day it is built)

Account: the one that owns the instance's domain. Auth: an API token with only the
Workers AI permission (`Account > Workers AI > Read`, which covers running
models).

**Text, OpenAI-compatible:**

```
DAYDREAM_LLM_BASE_URL=https://api.cloudflare.com/client/v4/accounts/<ACCOUNT_ID>/ai/v1
DAYDREAM_LLM_MODEL=openai/@cf/qwen/<a Qwen instruct model from the catalog>
DAYDREAM_LLM_API_KEY=<the Workers AI token>
```

Things to verify with `bin/game model-eval run --label workers-ai` before
trusting it:

- **Structured output.** The parser and dialogue send
  `response_format: json_schema` (vLLM guided decoding). Support varies by
  Workers AI model; a model that ignores it will fail the parser's
  grounding. The canon suite and the parser corpus catch it.
- **Thinking.** Qwen3.x "thinks" by default. Here that is switched off
  server-side (`--default-chat-template-kwargs`); Workers AI has no such
  flag, so pick a non-thinking model or check that its output carries no
  reasoning.
- **Latency and timeouts.** The client timeouts (10-20 s) are tuned for the
  local model.

**Images, a backend of about 20 lines:**

```python
async def workers_ai_flux(p: RenderParams) -> bytes:
    url = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT}/ai/run/@cf/black-forest-labs/flux-1-schnell"
    async with httpx.AsyncClient(timeout=60) as http:
        r = await http.post(url, headers={"Authorization": f"Bearer {TOKEN}"},
                            json={"prompt": p.prompt, "seed": p.seed, "steps": 4})
        r.raise_for_status()
        return base64.b64decode(r.json()["result"]["image"])   # JPEG
IMAGE_BACKENDS["workers-ai"] = workers_ai_flux
```

- Flux 1 schnell takes a prompt, a seed and at most 8 steps; there is no
  negative prompt, and the size is fixed per call.
- `@cf/stabilityai/stable-diffusion-xl-base-1.0` takes a prompt, a negative
  prompt, a width and height, steps and a seed, and returns PNG bytes. The
  room banners' 1024x384 is not a native size for either; crop or letterbox.
- Neither can load our watercolor LoRA. The look will differ, so the art
  needs its own WHIMSY grading (image-test + anchors) before any friend sees
  it.

**Cost.** Workers AI bills in "neurons". The free allowance is 10,000 a day;
beyond it, about $0.011 per 1,000. A few dozen text calls or a couple of
hundred Flux images a day fit in the free allowance, and calls hard-stop at
the limit on a free account.

## What turning it on takes (the policy amendment)

1. **CLAUDE.md.** Amend "Generation policy: local at runtime". Remote reflexes
   are permitted as an operator-selected fallback while the local GPU is
   unavailable. They use open-weight models on Workers AI only, never a
   frontier model and never an Anthropic or OpenAI key. The reflexes framing
   is unchanged: nothing remote writes story.
2. **`tests/test_no_cloud_keys.py`.** It pins the default endpoint to
   localhost; keep that pin for the default, and allow the remote endpoint
   only through the explicit fallback config.
3. **The prod sandbox.** `daydream-prod.service` has `IPAddressDeny=any`: the
   kernel forbids exactly this. Loosening it is the most visible part of the
   decision; allow only what Workers AI needs, and write down why.
4. **A secret in prod.** The Workers AI token would be the prod service's
   first secret (today it holds none). It belongs in a root-only
   `EnvironmentFile`, with the smallest scope Cloudflare offers.
5. **Provenance.** Tag remote narration `src: "remote"`, as local lines are
   tagged `src: "local"`, so the dream digest can tell them apart.
6. **Switching.** Make it a `bin/game prod` verb (for example
   `sleep --remote-reflexes`) rather than a hand-edited env file, so the
   village's state is always legible from `prod status`.

Until those are done, the seam is just an honest place to put the code.
