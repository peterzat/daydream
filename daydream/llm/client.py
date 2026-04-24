"""LLM client wrapper.

All LLM calls flow through here so the v1 GPU arbiter (port from
~/src/qwen-2.5-localreview/gpu_lock.py) can wrap the single call site
without touching gameplay code. Uses litellm as a Python library, not as
a proxy process; the same signature works against vLLM today and against
Cloudflare Workers AI / OpenAI / Anthropic later by swapping the model
name in config."""

import json

import litellm

from daydream import config
from daydream.gpu import arbiter


class LLMUnavailable(Exception):
    """Raised when the LLM backend is unreachable, times out, returns no
    message, or returns content that is not parseable JSON. Callers handle
    this by narrating a 'foggy' fallback via the event log (SPEC criterion 7)."""


# Optional side channel for observability tools that need token-usage
# metrics from the last call (e.g. voice-samples harness). Module-global
# because acompletion_json is awaited from various layers and threading
# the usage through every caller would leak implementation detail
# through the whole skill pipeline. Cleared at the TOP of each call;
# populated only on successful response. Not thread-safe by design —
# the consumer reads this synchronously after awaiting a single
# acompletion_json call. See SPEC 2026-04-24 criterion 2.
_last_usage: dict | None = None


def reset_last_usage() -> None:
    """Clear the last-usage side channel. Callers that care about their
    own call's usage should call this, then acompletion_json, then
    get_last_usage() to read a clean record."""
    global _last_usage
    _last_usage = None


def get_last_usage() -> dict | None:
    """Return {prompt_tokens, completion_tokens} from the most recent
    acompletion_json response, or None if the last call was never made,
    failed before response, or the backend omitted a usage field."""
    return _last_usage


async def acompletion_json(
    system: str,
    user: str,
    *,
    model: str | None = None,
    temperature: float = 0.0,
    max_tokens: int = 256,
    timeout: float = 10.0,
) -> dict:
    """Call the LLM and parse a JSON object from the response.

    Raises LLMUnavailable on any backend failure or unparseable output. The
    caller decides how to recover (typically by narrating 'the dream is foggy')."""
    # Clear any stale usage from a prior call before the side channel
    # could leak into a failed call's observability.
    global _last_usage
    _last_usage = None
    # Hold the GPU arbiter for the duration of the LLM call so vLLM and
    # any in-flight image-gen on ComfyUI never run simultaneously on the
    # 20 GB GPU. The lock is in-process; see daydream/gpu/arbiter.py.
    try:
        async with arbiter.acquire():
            response = await litellm.acompletion(
                model=model or config.llm_model(),
                api_base=config.llm_base_url(),
                api_key=config.llm_api_key(),
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
                response_format={"type": "json_object"},
            )
    except Exception as e:
        raise LLMUnavailable(f"LLM call failed: {e}") from e

    try:
        text = response.choices[0].message.content or ""
    except (AttributeError, IndexError) as e:
        raise LLMUnavailable(f"LLM returned no message: {e}") from e

    # Capture usage after a successful response, BEFORE JSON parsing,
    # so even a malformed-JSON LLMUnavailable raise still leaves
    # diagnostic metrics behind for a caller to read.
    usage_obj = getattr(response, "usage", None)
    if usage_obj is not None:
        _last_usage = {
            "prompt_tokens": getattr(usage_obj, "prompt_tokens", None),
            "completion_tokens": getattr(usage_obj, "completion_tokens", None),
        }

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise LLMUnavailable(f"LLM returned non-JSON: {text[:200]}") from e
