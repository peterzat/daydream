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


class LLMUnavailable(Exception):
    """Raised when the LLM backend is unreachable, times out, returns no
    message, or returns content that is not parseable JSON. Callers handle
    this by narrating a 'foggy' fallback via the event log (SPEC criterion 7)."""


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
    try:
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

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise LLMUnavailable(f"LLM returned non-JSON: {text[:200]}") from e
