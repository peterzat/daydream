"""Skill registry: name -> handler + metadata. Core skills live in this
module; data skills are loaded from the `skills` table (see
`daydream.skills.data`) and merged into the registry's read API at
runtime.

The websocket layer asks list_available_for_room() to assemble UI
buttons and to give the LLM interpreter the candidate set. Data skills
extend that view without restarting the server — the registry re-reads
the DB on each call, so `bin/game world skill add` takes effect
immediately on the next snapshot (SPEC criterion 8)."""

from collections.abc import Callable
from dataclasses import dataclass

from daydream import events
from daydream.skills import core

SkillHandler = Callable[[str, str, str], list[events.Event]]


@dataclass(frozen=True)
class SkillSpec:
    name: str
    kind: str  # 'core' or 'data'
    ui_hint: str
    description: str  # one-line summary the interpreter sees as a candidate
    # `handler` is only set for core skills. Data skills dispatch via
    # `daydream.skills.data.execute_by_name` because the execution is
    # async (LLM call) while this dataclass describes both kinds
    # uniformly for list / find purposes.
    handler: SkillHandler | None = None


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
    """Return a SkillSpec by name — core first, then data. Names are
    case-insensitive and whitespace-trimmed; the stored names are
    lowercase."""
    needle = name.strip().lower()
    core_spec = CORE_SKILLS.get(needle)
    if core_spec is not None:
        return core_spec
    # Data skills live in the DB; degrade gracefully if not initialized
    # (tests sometimes exercise the interpreter without a DB).
    from daydream.skills import data
    pair = data.find(needle)
    return pair[0] if pair is not None else None


def list_available_for_room(room_id: str) -> list[SkillSpec]:
    """Return skills available in this room context: every core skill
    plus every enabled data skill whose context predicate matches.

    The registry degrades gracefully when the DB is not initialized
    (returns core only), so test paths that exercise the interpreter
    without a fresh_db fixture keep working."""
    specs: list[SkillSpec] = list(CORE_SKILLS.values())
    from daydream.skills import data
    specs.extend(spec for spec, _ in data.available_for_room(room_id))
    return specs


def execute(name: str, actor_id: str, room_id: str, args: str) -> list[events.Event] | None:
    """Dispatch a CORE skill by name. Returns None if no such core skill;
    raises if called on a data skill — data skills must be dispatched
    via `await data.execute_by_name(...)` from the async WS handler."""
    spec = CORE_SKILLS.get(name.strip().lower())
    if spec is None:
        return None
    if spec.handler is None:  # defensive: only data has None handler
        raise RuntimeError(f"skill {name!r} has no sync handler")
    return spec.handler(actor_id, room_id, args)
