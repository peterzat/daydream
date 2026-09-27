"""LLM client wrapper.

All LLM calls flow through here so the GPU arbiter can wrap the single
call site without touching gameplay code. Uses litellm as a Python
library, not as a proxy process; the same signature works against vLLM
today and against Cloudflare Workers AI / OpenAI / Anthropic later by
swapping the model name in config.

Observability: every call is tagged with a caller-supplied `purpose`
("parser", "dialogue", "growth", ...) and logged on the dedicated
`daydream.llm.usage` logger — purpose, model, latency, token counts —
so prompt/latency analysis has a durable feed (plan 2026-07-02: prompt
monitoring infra)."""

import asyncio
import contextvars
import json
import logging
import time

import litellm

from daydream import config
from daydream.gpu import arbiter

usage_logger = logging.getLogger("daydream.llm.usage")

# The one canonical LLM-outage line every caller narrates (previously
# hand-copied at three sites). Player-facing; keep in the WHIMSY register.
FOGGY_TEXT = "The dream is foggy right now; that thought slips away."


class LLMUnavailable(Exception):
    """Raised when the LLM backend is unreachable, times out, returns no
    message, or returns content that is not parseable JSON. Callers handle
    this by narrating a 'foggy' fallback via the event log (SPEC criterion 7)."""


# Optional side channel for observability tools that need token-usage
# metrics from the last call (e.g. voice-samples harness). A ContextVar
# (not a module global) so concurrent LLM calls in different tasks —
# allowed since the arbiter's shared-LLM gate — can never smear each
# other's numbers: each task reads the usage of ITS OWN awaited call.
# Cleared at the TOP of each call; populated only on successful response.
_last_usage: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "daydream_llm_last_usage", default=None
)


def reset_last_usage() -> None:
    """Clear the last-usage side channel. Callers that care about their
    own call's usage should call this, then acompletion_json, then
    get_last_usage() to read a clean record."""
    _last_usage.set(None)


def get_last_usage() -> dict | None:
    """Return {prompt_tokens, completion_tokens} from the most recent
    acompletion_json response awaited IN THIS TASK, or None if the last
    call was never made, failed before response, or the backend omitted
    a usage field."""
    return _last_usage.get()


def set_last_usage_for_tests(value: dict | None) -> None:
    """Test seam: poke the side channel the way acompletion_json would."""
    _last_usage.set(value)


_remote_sem: asyncio.Semaphore | None = None


def _llm_slot(gate: str):
    """The GPU arbiter's slot for a local endpoint; for a remote one (the
    remote-reflexes seam, off by default) its own concurrency limit, since
    the arbiter gates only this box's card (SPEC 2026-09-27 criterion 23)."""
    global _remote_sem
    if config.llm_is_local():
        return arbiter.acquire(gate)
    if _remote_sem is None:
        _remote_sem = asyncio.Semaphore(config.remote_llm_concurrency())
    return _remote_sem


async def acompletion_json(
    system: str,
    user: str,
    *,
    model: str | None = None,
    temperature: float = 0.0,
    max_tokens: int = 256,
    timeout: float = 10.0,
    purpose: str = "unlabeled",
    gate: str = "llm",
    response_format: dict | None = None,
) -> dict:
    """Call the LLM and parse a JSON object from the response.

    `purpose` names the calling surface ("parser", "dialogue", "drift",
    "growth", "retell", "examine", ...) for the usage log; it never
    reaches the model.

    `gate` is the arbiter class: "llm" for player-facing text (the default),
    "background" for the story director (never delays a player call).
    `response_format` overrides the default {"type": "json_object"} (e.g. a
    json_schema whose enum constrains a choice to offered ids).

    Raises LLMUnavailable on any backend failure or unparseable output. The
    caller decides how to recover (typically by narrating FOGGY_TEXT)."""
    # Clear any stale usage from a prior call before the side channel
    # could leak into a failed call's observability.
    _last_usage.set(None)
    resolved_model = model or config.llm_model()
    t_enqueue = time.monotonic()
    # Hold a shared "llm" slot for the duration of the call: LLM calls run
    # concurrently with each other (vLLM batches natively, capped at
    # config.llm_concurrency()) but never overlap an exclusive image
    # render. See daydream/gpu/arbiter.py for the admission policy.
    try:
        async with _llm_slot(gate):
            t_start = time.monotonic()
            response = await litellm.acompletion(
                model=resolved_model,
                api_base=config.llm_base_url(),
                api_key=config.llm_api_key(),
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
                response_format=response_format or {"type": "json_object"},
            )
    except Exception as e:
        usage_logger.info(
            "llm purpose=%s model=%s outcome=error error=%s",
            purpose, resolved_model, type(e).__name__,
        )
        raise LLMUnavailable(f"LLM call failed: {e}") from e

    try:
        text = response.choices[0].message.content or ""
    except (AttributeError, IndexError) as e:
        raise LLMUnavailable(f"LLM returned no message: {e}") from e

    # Capture usage after a successful response, BEFORE JSON parsing,
    # so even a malformed-JSON LLMUnavailable raise still leaves
    # diagnostic metrics behind for a caller to read.
    prompt_tokens = completion_tokens = None
    usage_obj = getattr(response, "usage", None)
    if usage_obj is not None:
        prompt_tokens = getattr(usage_obj, "prompt_tokens", None)
        completion_tokens = getattr(usage_obj, "completion_tokens", None)
        _last_usage.set({
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        })
    now = time.monotonic()
    usage_logger.info(
        "llm purpose=%s model=%s wait_ms=%d call_ms=%d prompt_tokens=%s "
        "completion_tokens=%s",
        purpose, resolved_model,
        int((t_start - t_enqueue) * 1000), int((now - t_start) * 1000),
        prompt_tokens, completion_tokens,
    )

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise LLMUnavailable(f"LLM returned non-JSON: {text[:200]}") from e
