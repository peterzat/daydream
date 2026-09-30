"""What each player has come across: the subjects the page may offer.

The page is the player's memory, not the world's index (DESIGN.md "What the
page offers"; playtest 2026-09-29: on first meeting the clockmaker, the
ask-about chips named people and a night the player had never heard of). A
resident's topic becomes a chip only once its subject has reached this
player in the fiction:

- its name appeared in something told to them (a line, an answer, a card,
  the room they stood in, a thing or person they saw there) that an author
  wrote: a line the local model wrote (`src: "local"`) introduces nothing,
  because the model reads whole voice sheets and drops their names in
  passing (playtest 2026-09-30: an improvised greeting named the
  clockmaker's late teacher, and the teacher became a chip that no authored
  line had introduced);
- they asked about it (a typed guess counts: it is answered, and from then
  on it is a chip);
- or the topic is authored `open`: fair to ask at first meeting, like a
  clockmaker's own trade.

Typing still reaches every available topic; only the chips wait.

A subject is a topic's label as `story.normalize_topic` keys it, and any
authored `mentions` (other ways the fiction names it) lead to the same key.
A label that is a proper noun ("Ada", "the Old Mill") matches only
when capitalized in the text, so a common word ("a bell over the door") never
stands in for a person. Knowledge is per player, kept with the rest of their
story state (`pq:<toon>:met`), and never shrinks.
"""
from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass

from daydream import db, events, objects

logger = logging.getLogger("daydream.heard")

MET_CAP = 800
_ARTICLES = ("the", "a", "an")
_WORD = re.compile(r"[A-Za-z0-9]+(?:['’][A-Za-z]+)?")
TEXT_KINDS = ("narrate", "say", "echo")


@dataclass(frozen=True)
class Form:
    key: str  # the subject key: the topic label, normalized
    stems: tuple[str, ...]
    proper: bool


def _stem(word: str) -> str:
    """A light stem, the same on both sides of a match: a possessive dropped
    ("Ada's" is Ada), "-ing" dropped ("turning" meets "turn", "sitting" meets
    "sit"), a final "s" dropped ("clocks", "sits")."""
    w = re.sub(r"['’]s$", "", word).lower().replace("’", "'")
    if len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us", "is")):
        w = w[:-1]
    if len(w) > 5 and w.endswith("ing"):
        w = w[:-3]
        if len(w) > 2 and w[-1] == w[-2] and w[-1] not in "aeiouls":
            w = w[:-1]
    return w


def _tokens(text: str) -> list[tuple[str, str]]:
    """(the word as written, its stem) for each word but the articles, so
    "turning clocks back" meets "turning the clocks back"."""
    out = []
    for m in _WORD.finditer(text or ""):
        stem = _stem(m.group(0))
        if stem not in _ARTICLES:
            out.append((m.group(0), stem))
    return out


def form_of(key: str, text: str) -> Form | None:
    toks = _tokens(text)
    if not toks or len(" ".join(s for _, s in toks)) < 3:
        return None
    return Form(key, tuple(s for _, s in toks), toks[0][0][:1].isupper())


def key_of(label: str) -> str:
    """A subject's key: the label as `story.normalize_topic` keys it, marked
    when it is a name, so "the rose" (a flower) and Rose (a person)
    are different subjects."""
    from daydream import story

    toks = _tokens(label)
    k = story.normalize_topic(label)
    return f"^{k}" if toks and toks[0][0][:1].isupper() else k


def _topic_forms(key: str, label: str, mentions) -> list[Form]:
    out = [form_of(key, label)]
    for m in mentions if isinstance(mentions, list) else []:
        if isinstance(m, str):
            out.append(form_of(key, m))
    return [f for f in out if f is not None]


_cache: dict[tuple[str, int], dict[str, list[Form]]] = {}


def vocabulary(world_id: str) -> dict[str, list[Form]]:
    """Every askable subject in the world, indexed by its first stem: the
    residents' topics and the talk beats' topics. Cached per world and live
    connection generation (`db.generation()`, bumped whenever the live
    connection opens or closes), so a swap, a restart or a new test database
    starts afresh. A change to topics over the same connection is not seen
    until then (`clear_cache` forgets at once)."""
    from daydream import story

    ck = (world_id, db.generation())
    got = _cache.get(ck)
    if got is not None:
        return got
    forms: list[Form] = []
    for t in objects.all_of_kind(world_id, "toon"):
        for tp in t.properties.get("topics") or []:
            if isinstance(tp, dict) and isinstance(tp.get("label"), str):
                forms += _topic_forms(key_of(tp["label"]), tp["label"], tp.get("mentions"))
    for arc in story.arcs_def(world_id).values():
        for beat in (arc.get("beats") or {}).values() if isinstance(arc, dict) else []:
            if isinstance(beat, dict) and isinstance(beat.get("topic"), str):
                forms += _topic_forms(key_of(beat["topic"]), beat["topic"],
                                      beat.get("topic_mentions"))
    index: dict[str, list[Form]] = {}
    for f in dict.fromkeys(forms):
        index.setdefault(f.stems[0], []).append(f)
    if len(_cache) > 16:
        _cache.clear()
    _cache[ck] = index
    return index


def clear_cache() -> None:
    _cache.clear()


def names(text: str, forms: Iterable[Form]) -> bool:
    """Does this text name any of these forms? (Pure: the world's own
    tests check an envelope with it before any database exists.)"""
    toks = _tokens(text)
    stems = [s for _, s in toks]
    for f in forms:
        n = len(f.stems)
        for i, (orig, stem) in enumerate(toks):
            if stem == f.stems[0] and tuple(stems[i:i + n]) == f.stems \
                    and (not f.proper or orig[:1].isupper()):
                return True
    return False


def subjects_in(world_id: str, text: str) -> set[str]:
    """The subject keys a text names."""
    toks = _tokens(text)
    if not toks:
        return set()
    index = vocabulary(world_id)
    stems = [s for _, s in toks]
    found: set[str] = set()
    for i, (orig, stem) in enumerate(toks):
        for f in index.get(stem, ()):
            n = len(f.stems)
            if tuple(stems[i:i + n]) == f.stems and (not f.proper or orig[:1].isupper()):
                found.add(f.key)
    return found


def met(world_id: str, toon_id: str) -> set[str]:
    from daydream import story

    got = story.pget(world_id, toon_id, "met", [])
    return {x for x in got if isinstance(x, str)} if isinstance(got, list) else set()


def add(world_id: str, toon_id: str, keys: Iterable[str]) -> None:
    from daydream import story

    have = story.pget(world_id, toon_id, "met", [])
    have = [x for x in have if isinstance(x, str)] if isinstance(have, list) else []
    new = [k for k in dict.fromkeys(keys) if k and k not in have]
    if new:
        story.pset(world_id, toon_id, "met", (have + new)[-MET_CAP:])


def note(world_id: str, toon_ids: Iterable[str], text: str) -> None:
    """Everything this text names is now known to these players."""
    ids = [t for t in toon_ids if t]
    if not ids or not text:
        return
    keys = subjects_in(world_id, text)
    if keys:
        for toon_id in ids:
            add(world_id, toon_id, keys)


def _event_text(payload: dict) -> str:
    parts = [payload.get("text")]
    card = payload.get("card")
    if isinstance(card, dict):
        parts += [card.get("name"), card.get("body")]
    return " . ".join(p for p in parts if isinstance(p, str) and p)


def on_event(event) -> None:
    """The events.append hook: a line told to players is heard by them (the
    one it is for, or the players standing in its room, less `except`).
    Only authored and engine lines: what the local model wrote introduces
    no subject."""
    if event.kind not in TEXT_KINDS or not isinstance(event.payload, dict):
        return
    if event.payload.get("src") == "local":
        return
    text = _event_text(event.payload)
    if not text:
        return
    if event.recipient_id:
        who = objects.get(event.recipient_id)
        if who is None or not who.is_player:
            return
        note(who.world_id, [who.id], text)
        return
    if not event.room_id:
        return
    room = objects.get(event.room_id)
    if room is None:
        return
    # Only those dreaming now: a rested player keeps their place but is not
    # there to hear it.
    hearers = [t.id for t in objects.contents(room.id, kind="toon")
               if t.is_human_controlled and not events.excepted(event.payload, t.id)]
    note(room.world_id, hearers, text)


def present(actor_id: str) -> set[str]:
    """Subjects in front of the player now: the room they stand in (its name
    and description) and every thing and person in scope."""
    from daydream import lighting

    actor = objects.get(actor_id)
    if actor is None:
        return set()
    if actor.location_id and not lighting.room_lit(actor.location_id):
        return set()  # a dark room shows nothing, so names nothing
    from daydream import story

    # The satchel's threads are read too: "Ask about the first winding."
    parts: list[str] = list(story.threads_for(actor_id))
    for o in objects.in_scope(actor_id):
        if o.id == actor_id or o.kind == "prototype":
            continue
        if not objects.visible_to(o, actor_id):
            continue
        parts.append(o.name)
        if o.kind == "room":
            parts.append(o.properties.get("title") or "")
            parts.append(o.properties.get("description_cached") or "")
    return subjects_in(actor.world_id, " . ".join(p for p in parts if isinstance(p, str)))


def knows(topic: dict, known: set[str]) -> bool:
    """A topic (as `story.available_topics` gives it) may be a chip."""
    return bool(topic.get("open")) or key_of(topic["label"]) in known


def known_keys(world_id: str, actor_id: str) -> set[str]:
    """What this player has come across, and what is in front of them now
    (kept, so leaving the room does not forget it)."""
    here = present(actor_id)
    have = met(world_id, actor_id)
    if here - have:
        add(world_id, actor_id, here - have)
    return have | here
