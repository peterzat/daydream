"""Per-actor parser memory: the IT referent and the AGAIN last-input (the original game
turn, SPEC 2026-07-02 criterion 9). Tiny, dependency-free, in-process —
pronoun state is conversational, not world state, so it lives and dies with
the server process (a reconnecting player just names the thing once)."""

from __future__ import annotations

_it: dict[str, str] = {}
_it_name: dict[str, str] = {}
_person: dict[str, str] = {}
_last_input: dict[str, str] = {}


def remember_it(actor_id: str, object_id: str) -> None:
    _it[actor_id] = object_id
    _it_name.pop(actor_id, None)


def remember_it_name(actor_id: str, name: str) -> None:
    """IT for a thing the prose names that is no object (a glimpse): its name
    (spec 2026-09-29 criterion 11)."""
    _it_name[actor_id] = name
    _it.pop(actor_id, None)


def it_referent(actor_id: str) -> str | None:
    return _it.get(actor_id)


def it_name(actor_id: str) -> str | None:
    return _it_name.get(actor_id)


def remember_person(actor_id: str, toon_id: str) -> None:
    """HIM / HER / THEM: the last person this actor spoke to, asked, gave to
    or gestured at."""
    _person[actor_id] = toon_id


def person_referent(actor_id: str) -> str | None:
    return _person.get(actor_id)


def remember_input(actor_id: str, text: str) -> None:
    _last_input[actor_id] = text


def last_input(actor_id: str) -> str | None:
    return _last_input.get(actor_id)


def reset() -> None:
    """Test helper."""
    _it.clear()
    _it_name.clear()
    _person.clear()
    _last_input.clear()
