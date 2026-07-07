"""Skill registry: name -> spec for DATA skills (author-written, DB-loaded;
see `daydream.skills.data`). The engine's own verbs live in
`daydream.verbs`, not here — the legacy core-skill handlers and the LLM
skill-router that dispatched them were removed once the closed verb set +
grounded parser replaced that path (v1.0 cleanup).

The websocket layer asks list_available_for_room() to assemble the skill
bar. The registry re-reads the DB on each call, so `bin/game world skill
add` takes effect immediately on the next snapshot (SPEC criterion 8)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SkillSpec:
    name: str
    kind: str  # always 'data' at runtime; kept explicit for the SPA payload
    ui_hint: str
    description: str  # one-line summary shown to authors and the parser
    # Data skills dispatch via `daydream.skills.data.execute_by_name`
    # (async LLM call); the field survives for shape-compatibility with
    # older callers that check it.
    handler: object | None = None


def find(name: str) -> SkillSpec | None:
    """Return a data-skill SkillSpec by name. Names are case-insensitive
    and whitespace-trimmed; the stored names are lowercase. Degrades
    gracefully (None) when the DB is not initialized."""
    from daydream.skills import data

    pair = data.find(name.strip().lower())
    return pair[0] if pair is not None else None


def list_available_for_room(room_id: str) -> list[SkillSpec]:
    """Return every enabled data skill whose context predicate matches
    this room. Degrades gracefully (empty) when the DB is not
    initialized."""
    from daydream.skills import data

    return [spec for spec, _ in data.available_for_room(room_id)]
