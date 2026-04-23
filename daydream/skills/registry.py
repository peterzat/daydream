"""Skill registry: name -> handler + metadata. Data skills join in v1.

The registry is the single source of "what can the player do right now."
The websocket layer asks list_available_for_room() to assemble UI buttons
and to give the LLM interpreter the candidate set."""

from collections.abc import Callable
from dataclasses import dataclass

from daydream import events
from daydream.skills import core

SkillHandler = Callable[[str, str, str], list[events.Event]]


@dataclass(frozen=True)
class SkillSpec:
    name: str
    kind: str  # 'core' or 'data'
    handler: SkillHandler
    ui_hint: str
    description: str  # one-line summary the interpreter sees as a candidate


CORE_SKILLS: dict[str, SkillSpec] = {
    "look": SkillSpec(
        name="look",
        kind="core",
        handler=core.look,
        ui_hint="Look",
        description="Describe the current room and the items in it. No args.",
    ),
    "say": SkillSpec(
        name="say",
        kind="core",
        handler=core.say,
        ui_hint="Say",
        description="Speak something out loud. Args: the text to say.",
    ),
    "examine": SkillSpec(
        name="examine",
        kind="core",
        handler=core.examine,
        ui_hint="Examine",
        description="Examine an item present in the current room. Args: the item name.",
    ),
    "go": SkillSpec(
        name="go",
        kind="core",
        handler=core.go,
        ui_hint="Go",
        description="Move through an exit in the current room. Args: a direction name (e.g. 'north', 'down', 'in').",
    ),
}


def find(name: str) -> SkillSpec | None:
    return CORE_SKILLS.get(name.strip().lower())


def list_available_for_room(room_id: str) -> list[SkillSpec]:
    """Return skills available in this room context.

    v0: every core skill is available everywhere. Data-skill predicates land
    in v1 (data-skills-cli backlog entry)."""
    return list(CORE_SKILLS.values())


def execute(name: str, actor_id: str, room_id: str, args: str) -> list[events.Event] | None:
    """Look up a skill by name and run it. Returns None if no such skill."""
    spec = find(name)
    if spec is None:
        return None
    return spec.handler(actor_id, room_id, args)
