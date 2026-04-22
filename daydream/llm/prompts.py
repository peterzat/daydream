"""Versioned prompt templates. Loadable from prompts/*.txt in v1 so admins
can tune voice without a code change."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from daydream.skills.registry import SkillSpec


INTERPRETER_SYSTEM = """You are the routing layer of a cozy daydream-themed text adventure. Given the player's free-form input and a list of available skills, return JSON identifying which skill best fits.

Output schema (strict):
{"skill": "<skill_name or 'none'>", "args": "<remaining text or ''>"}

Rules:
- Pick "none" when no skill obviously fits, or the input is small talk / chatter. Do NOT force-fit a wrong skill to avoid 'none'.
- "args" is the player's input minus the verb / skill name; preserve casing and word order.
- Output JSON only. No prose, no code fences."""


def interpreter_user(input_text: str, skills: "list[SkillSpec]") -> str:
    """Build the user message for the interpreter call.

    Skills are listed as 'name: description' so the model picks by intent
    rather than by literal keyword match."""
    skill_lines = "\n".join(f"- {s.name}: {s.description}" for s in skills)
    return (
        f"Available skills:\n{skill_lines}\n\n"
        f"Player input: {input_text}\n\n"
        'Respond with JSON: {"skill": "...", "args": "..."}'
    )
