"""LLM-driven free-text -> skill routing.

The interpreter sees the player input and the list of skills currently
available in the player's context. It picks one (or 'none' for chatter),
and the caller dispatches via skills.registry.execute(...).

On LLM failure (vLLM down, timeout, parse error) the interpreter degrades
to skill='none' with the error attached, so the caller can narrate a
'foggy' fallback rather than crash. This is the v0 implementation of
SPEC criteria 6 and 7."""

from dataclasses import dataclass

from daydream.llm import client, prompts
from daydream.skills.registry import SkillSpec


@dataclass(frozen=True)
class Interpretation:
    skill: str  # 'none' or a known skill name
    args: str
    error: str | None = None  # set when the LLM was unreachable


async def interpret(input_text: str, available: list[SkillSpec]) -> Interpretation:
    if not input_text.strip():
        return Interpretation(skill="none", args="")

    valid_names = {s.name for s in available}
    try:
        result = await client.acompletion_json(
            system=prompts.INTERPRETER_SYSTEM,
            user=prompts.interpreter_user(input_text, available),
        )
    except client.LLMUnavailable as e:
        return Interpretation(skill="none", args=input_text, error=str(e))

    skill = str(result.get("skill", "none")).strip().lower()
    args = str(result.get("args", "")).strip()

    if skill == "none" or skill not in valid_names:
        return Interpretation(skill="none", args=args or input_text)
    return Interpretation(skill=skill, args=args)
