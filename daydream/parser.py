"""Grounded natural-language command parser — deterministic fast-path first,
the local LLM as the fallback for free phrasings.

Maps a player's line to grounded commands `{verb, dobj_id, iobj_id, args}`:
verbs come from the closed engine registry plus the world's declared verbs,
and objects resolve to in-scope IDS — "grounded resolution", which plays to
a 7B model's strict-JSON strength. The deterministic engine, not the model,
mutates state.

The deterministic surface (platform turn, SPEC 2026-07-02 criterion 9), all with
ZERO LLM calls:

- exit directions incl. abbreviations (n/ne/u/d, in/out, world directions)
- bare verbs, "verb <name>", multi-word verb aliases ("turn on", "blow out")
  by longest-prefix match, engine + world verbs + their aliases
- verb–preposition–object forms via each verb's authored `preps`
  ("put X in Y", "turn X with Y", "attack X with Y")
- TAKE/DROP/PUT **ALL**, AND-lists, and EXCEPT — expanded against scope into
  per-item commands
- **IT** (per-actor referent), **AGAIN**/G (re-run last input), **THEN** /
  period chaining (segments parse and execute in order)
- GWIM slot defaults: a verb's authored dobj_default/iobj_default filter
  fills an omitted slot iff exactly one in-scope thing matches ("light
  match" finds the matchbook)
- ambiguous names (two in-scope "lantern"s) return a CLARIFY question; the
  next typed reply (or a click) resolves it

Then one grounded LLM call for everything else ("smash the villain with my
sword"), and the fail-safe: unknown verb / out-of-scope target → verb
`none`, no mutation; LLM outage → `error` (the caller narrates "foggy" —
deterministic play continues without the model)."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from daydream import objects, pronouns, rooms, verbs, worldverbs
from daydream.llm import client
from daydream.skills import registry

logger = logging.getLogger(__name__)

_LEADING_ARTICLES = ("the ", "a ", "an ", "my ")


def _strip_article(text: str) -> str:
    t = text.strip()
    low = t.lower()
    for art in _LEADING_ARTICLES:
        if low.startswith(art):
            return t[len(art):].strip()
    return t


@dataclass(frozen=True)
class Parse:
    """A resolved command. `verb` is a closed verb, a data-skill name, or
    'none' (chatter / ungroundable). `error` is set only when the LLM was
    unreachable (the caller narrates 'foggy')."""

    verb: str
    dobj_id: str | None = None
    iobj_id: str | None = None
    args: str = ""
    error: str | None = None
    # The name the player typed for a target that could not be grounded to an
    # in-scope id ("take the moon"). Carried so the executor can say "you don't
    # see the <name> here", distinct from the no-target "Take what?".
    dobj_name: str | None = None


@dataclass(frozen=True)
class Clarify:
    """An ambiguity question: which of `options` did you mean? Carries the
    whole pending command so the answer (typed or clicked) completes it."""

    verb: str
    slot: str  # "dobj" | "iobj"
    name: str  # the ambiguous word as typed
    options: tuple[tuple[str, str], ...]  # (object_id, display name)
    args: str = ""
    dobj_id: str | None = None  # already-grounded other slot
    iobj_id: str | None = None

    @property
    def prompt(self) -> str:
        names = ", ".join(n for _, n in self.options[:-1])
        last = self.options[-1][1]
        return f"Which {self.name} do you mean: {names} or {last}?"


@dataclass(frozen=True)
class LineParse:
    """One input line, parsed: zero or more commands to execute in order,
    OR a clarify question, OR a message to narrate (e.g. 'take all' with
    nothing here), OR an LLM-outage error."""

    commands: tuple[Parse, ...] = ()
    clarify: Clarify | None = None
    message: str | None = None
    error: str | None = None


NONE = Parse("none")

# Verbs whose direct object accepts ALL / AND-lists / EXCEPT.
_MULTI_VERBS = frozenset({"take", "drop", "put"})

_AND_SPLIT = re.compile(r"\s*,\s*|\s+and\s+", re.IGNORECASE)
_THEN_SPLIT = re.compile(r"\s+then\s+|\s*\.\s*", re.IGNORECASE)


SYSTEM = (
    "You translate a player's free text into ONE structured command for a "
    "text adventure. Return STRICT JSON only:\n"
    '{"verb": <one verb name from the list>, "dobj_id": <an object id from '
    'scope or null>, "iobj_id": <id or null>, "args": <leftover text such as '
    'what to say, else "">}.\n'
    "Pick the verb whose meaning best fits the input. Resolve a target to an "
    "object id from the Scope list by matching its name or aliases; use null "
    "when the verb takes no target. Use the verb \"none\" when nothing fits or "
    "the input is idle chatter. Output JSON only, no prose."
)


# ---- public entry points -------------------------------------------------


async def parse(actor_id: str, text: str) -> Parse:
    """Single-command view of `parse_line` (compat surface: the first
    command, or NONE). New callers use parse_line."""
    lp = await parse_line(actor_id, text)
    if lp.error:
        return Parse("none", error=lp.error)
    if lp.commands:
        return lp.commands[0]
    return NONE


async def parse_line(
    actor_id: str, text: str, pending: Clarify | None = None
) -> LineParse:
    """Resolve one input line to executable commands. Handles AGAIN, THEN
    chaining, multi-object expansion, clarify resolution (`pending` is a
    prior Clarify this line may be answering), and the LLM fallback per
    segment. Deterministic segments make zero LLM calls."""
    text = text.strip()
    if not text:
        return LineParse()
    actor = objects.get(actor_id)
    if actor is None:
        return LineParse()

    # A pending clarify: does this line answer it?
    if pending is not None:
        answered = _resolve_clarify(actor_id, pending, text)
        if answered is not None:
            _remember(actor_id, [answered])
            return LineParse(commands=(answered,))
        # Not an answer: fall through and parse as a fresh line.

    # AGAIN / G re-runs the last remembered input verbatim.
    if text.lower() in ("again", "g"):
        last = pronouns.last_input(actor_id)
        if not last:
            return LineParse(message="You haven't done anything to repeat yet.")
        text = last
    else:
        pronouns.remember_input(actor_id, text)

    room = rooms.get_room(actor.location_id) if actor.location_id else None
    commands: list[Parse] = []
    segments = _segments(actor_id, text, room)
    for segment in segments:
        seg = await _parse_segment(actor_id, segment.strip(), room)
        if isinstance(seg, Clarify):
            # Ask; anything already parsed before the ambiguity still runs.
            _remember(actor_id, commands)
            return LineParse(commands=tuple(commands), clarify=seg)
        if isinstance(seg, LineParse):  # message or error bubble
            if seg.error:
                return LineParse(commands=tuple(commands), error=seg.error)
            return LineParse(commands=tuple(commands), message=seg.message)
        commands.extend(seg)
    _remember(actor_id, commands)
    return LineParse(commands=tuple(commands))


def _starts_like_a_command(actor_id: str, segment: str, room) -> bool:
    words = segment.strip().split()
    if not words:
        return False
    world_id = objects.get(actor_id).world_id if objects.get(actor_id) else None
    first = words[0].lower().strip(",;:!?")
    two = " ".join(w.lower() for w in words[:2])
    if len(first) == 1 and len(words) > 1 and first not in verbs.DIRECTION_WORDS:
        return False
    return (first in verbs.DIRECTION_WORDS
            or (room is not None and first in room.exits)
            or first in ("again", "g")
            or _verb_by_word(world_id, two) is not None
            or _verb_by_word(world_id, first) is not None)


def _segments(actor_id: str, text: str, room) -> list[str]:
    """THEN / period chaining ("take lamp. north") splits a line only when
    it is a chain of commands: every piece opens with a verb or a direction,
    and the first is not speech. Anything else is one utterance and stays
    whole (playtest 2026-09-26: "say Hi Oona! I'm Juniper. I'm going up."
    lost its second sentence, and a talk's tail was parsed as a command)."""
    pieces = [p for p in _THEN_SPLIT.split(text) if p and p.strip()]
    if len(pieces) <= 1:
        return pieces
    world_id = objects.get(actor_id).world_id if objects.get(actor_id) else None
    first = pieces[0].strip().split()
    two = " ".join(w.lower() for w in first[:2])
    head = _verb_by_word(world_id, two) or _verb_by_word(world_id, first[0].lower())
    if head is not None and (head.free_text or head.name == "ask"):
        return [text]
    if all(_starts_like_a_command(actor_id, piece, room) for piece in pieces):
        return pieces
    return [text]


def _remember(actor_id: str, commands: list[Parse]) -> None:
    """IT tracks the last grounded direct object of the line."""
    for cmd in reversed(commands):
        if cmd.dobj_id:
            pronouns.remember_it(actor_id, cmd.dobj_id)
            break


# ---- clarify resolution ------------------------------------------------------


def _resolve_clarify(actor_id: str, pending: Clarify, text: str) -> Parse | None:
    """Match a typed reply against the pending options by token overlap:
    'the broken one' scores 1 against 'broken lantern' and 0 against
    'lantern', so the unique best match wins. A tie (typing the ambiguous
    word again) or zero overlap ('north') is not an answer — the caller
    parses the line fresh."""
    needle_tokens = {t for t in _strip_article(text).lower().split() if t}
    if not needle_tokens:
        return None
    scores: list[tuple[int, str]] = []
    for oid, name in pending.options:
        obj = objects.get(oid)
        option_tokens = set(name.lower().split())
        if obj is not None:
            for a in obj.aliases:
                option_tokens.update(str(a).lower().split())
        scores.append((len(needle_tokens & option_tokens), oid))
    best = max(s for s, _ in scores)
    if best < 1:
        return None
    winners = [oid for s, oid in scores if s == best]
    if len(winners) != 1:
        return None
    chosen = winners[0]
    if pending.slot == "dobj":
        return Parse(pending.verb, dobj_id=chosen, iobj_id=pending.iobj_id,
                     args=pending.args)
    return Parse(pending.verb, dobj_id=pending.dobj_id, iobj_id=chosen,
                 args=pending.args)


# ---- segment parsing -----------------------------------------------------------


async def _parse_segment(
    actor_id: str, text: str, room: rooms.Room | None
):
    """One THEN-segment → list[Parse] (possibly expanded), Clarify, or a
    LineParse carrying a message/error. Fast-path first; LLM fallback."""
    fp = _fast_path(actor_id, text, room)
    if fp is not None:
        return fp
    llm = await _llm_parse(actor_id, text, room)
    if llm.error:
        return LineParse(error=llm.error)
    return [llm]


def _fast_path(actor_id: str, text: str, room: rooms.Room | None):
    """Deterministic resolution. Returns list[Parse] / Clarify / LineParse
    (message) — or None to defer to the LLM."""
    low = text.strip().lower()
    actor = objects.get(actor_id)
    world_id = actor.world_id if actor is not None else None

    # Exit directions, including abbreviations: any known direction word is a
    # go — an absent exit refuses in-world (and ticks the clock), it is not
    # idle chatter for the LLM.
    if low in verbs.DIRECTION_WORDS:
        return [Parse("go", args=verbs.canonical_direction(low))]
    if room is not None and low in room.exits:
        return [Parse("go", args=low)]

    words = text.split()
    # Longest-prefix verb-word match: two-word heads ("turn on", "blow out")
    # beat one-word heads ("turn"). Engine names/aliases + world vocabulary.
    spec = None
    rest = ""
    if len(words) >= 2:
        two = " ".join(w.lower() for w in words[:2])
        spec = _verb_by_word(world_id, two)
        if spec is not None:
            rest = " ".join(words[2:]).strip()
    if spec is None and not (len(words[0]) == 1 and len(words) > 1):
        # A one-letter alias (i, l, x) is a command only on its own: "I keep
        # bees back home" is a sentence, not an inventory (playtest 2026-09-26).
        spec = _verb_by_word(world_id, words[0].lower())
        if spec is not None:
            rest = " ".join(words[1:]).strip()

    # "look at <name>" -> examine the named in-scope object. A bare `look`
    # describes the room and ignores any target, so the targeted form is routed
    # explicitly to examine rather than a room look (SPEC 2026-06-30).
    if spec is not None and spec.name == "look" and rest.lower().startswith("at "):
        target = _strip_article(rest[3:].strip())
        matches = _ground(actor_id, target)
        if len(matches) == 1 and "examine" in objects.verbs_for(matches[0]):
            return [Parse("examine", dobj_id=matches[0].id)]
        if len(matches) > 1:
            return _clarify("examine", "dobj", target, matches)
        return None  # "look at <unresolved>" -> hand to the LLM to ground

    if spec is None:
        # Legacy first-word data-skill name (`rook hi`, `forge a ring`), gated on
        # the skill being available in the current room.
        room_id = room.id if room is not None else ""
        head0 = words[0].lower()
        if head0 in _room_data_skill_names(room_id):
            return [Parse(head0, args=" ".join(words[1:]).strip())]
        return None

    verb = spec.name
    if verb == "ask":
        return _ask_fast_path(actor_id, rest)
    if rest and verb == "say":
        return _say_fast_path(actor_id, rest)
    if rest and verb == "talk":
        talked = _talk_fast_path(actor_id, rest)
        if talked is not None:
            return talked
    # Other free-text verbs (plant) with args may need the model's reading;
    # hand those to the LLM rather than claim them here.
    if rest and spec.free_text:
        return None
    # "take X from Y" is taking X; "drop X in/into Y" is putting it there.
    if verb == "take" and " from " in f" {rest.lower()} ":
        rest = rest[:rest.lower().find(" from ")].strip() or rest
    if verb == "drop" and re.search(r"\s(in|into|inside)\s", rest.lower()):
        put = _verb_by_word(world_id, "put")
        if put is not None:
            spec, verb = put, put.name

    if not spec.needs_dobj:
        return [Parse(verb, args=rest)]

    # ---- needs a direct object ----
    if not rest:
        filled = _gwim_fill(actor_id, spec.dobj_default, exclude=None)
        if filled is not None:
            parses = [Parse(verb, dobj_id=filled.id)]
            return _fill_iobj_default(actor_id, spec, parses)
        return [Parse(verb)]  # executor narrates "Verb what?"

    # Preposition split ("put X in Y", "turn X with Y") — authored per verb.
    dobj_part, iobj_part = _split_prep(spec, rest)
    iobj_id: str | None = None
    if iobj_part is not None:
        iobj_name = _strip_article(iobj_part)
        iobj_matches = _ground(actor_id, iobj_name)
        if len(iobj_matches) == 0:
            return None  # let the LLM try a fuzzier grounding
        if len(iobj_matches) > 1:
            return _clarify(verb, "iobj", iobj_name, iobj_matches,
                            dobj_hint=(actor_id, dobj_part))
        iobj_id = iobj_matches[0].id

    # ALL / AND-lists / EXCEPT for take/drop/put.
    if verb in _MULTI_VERBS:
        multi = _expand_multi(actor_id, verb, dobj_part, iobj_id)
        if multi is not None:
            return multi

    name = _strip_article(dobj_part)
    matches = _ground(actor_id, name)
    if len(matches) == 0:
        # Named but not in scope ("take the moon"): pass the name through so
        # the executor reads "you don't see the <name> here". If an iobj
        # half was present but this name missed, or the "name" is a whole
        # phrase (four words or more, a sentence rather than a noun), defer
        # to the LLM instead.
        if iobj_part is not None or len(name.split()) >= 4:
            return None
        return [Parse(verb, dobj_name=name)]
    if len(matches) > 1:
        return _clarify(verb, "dobj", name, matches, iobj_id=iobj_id)
    dobj = matches[0]
    if verb not in objects.verbs_for(dobj):
        if iobj_part is not None:
            return None
        # Let world/room/world rules still see it? No rule can apply if the
        # verb doesn't offer on the object; refuse like the executor would.
        return [Parse(verb, dobj_id=dobj.id)]
    parses = [Parse(verb, dobj_id=dobj.id, iobj_id=iobj_id)]
    if iobj_id is None:
        return _fill_iobj_default(actor_id, spec, parses)
    return parses


_LEAD_PUNCT = re.compile(r"^[\s,:;.!?-]+")


def _toon_prefix(actor_id: str, words: list[str]):
    """The longest leading run of `words` naming exactly one toon in scope:
    (toon, words consumed), (None, 0) when none does, or a Clarify list."""
    for k in range(min(len(words), 4), 0, -1):
        name = _strip_article(" ".join(words[:k]).strip(",:;.!?"))
        if not name:
            continue
        matches = [o for o in _ground(actor_id, name) if o.kind == "toon" and o.id != actor_id]
        if len(matches) == 1:
            return matches[0], k
        if len(matches) > 1:
            return matches, k
    return None, 0


def _say_fast_path(actor_id: str, rest: str):
    """`say <words>` is speech to the room, whole and deterministic
    (playtest 2026-09-26: the model read "say I'm off to see the loft" as a
    move). `say to <someone>: <words>` and `say <words> to <someone>` (a
    toon here) are talking to them."""
    words = rest.split()
    if words and words[0].lower() == "to":
        who, k = _toon_prefix(actor_id, words[1:])
        if isinstance(who, list):
            return _clarify("talk", "dobj", " ".join(words[1:1 + k]), who)
        if who is not None:
            text = _LEAD_PUNCT.sub("", " ".join(words[1 + k:]))
            return [Parse("talk", dobj_id=who.id, args=text)]
    low = rest.lower()
    idx = low.rfind(" to ")
    if idx > 0:
        tail = rest[idx + 4:].strip().rstrip(".!?")
        who, k = _toon_prefix(actor_id, tail.split())
        if who is not None and not isinstance(who, list) and k == len(tail.split()):
            return [Parse("talk", dobj_id=who.id, args=rest[:idx].strip())]
    return [Parse("say", args=rest)]


def _talk_fast_path(actor_id: str, rest: str):
    """`talk to|with <someone>[:,] <words>` / `talk to <someone> about <x>`:
    the someone grounds deterministically and every word after is theirs
    to hear, so a multi-sentence line reaches them whole (no parser call).
    None when no toon here is named (the LLM reads it)."""
    words = rest.split()
    if words and words[0].lower() in ("to", "with"):
        words = words[1:]
    who, k = _toon_prefix(actor_id, words)
    if who is None:
        return None
    if isinstance(who, list):
        return _clarify("talk", "dobj", " ".join(words[:k]), who)
    text = _LEAD_PUNCT.sub("", " ".join(words[k:]))
    if text.lower().startswith("about "):
        text = text[6:].strip()
    return [Parse("talk", dobj_id=who.id, args=text or "hello")]


def _ask_fast_path(actor_id: str, rest: str):
    """`ask|tell <someone> about <topic>` (SPEC 2026-09-26 criterion 6):
    the topic is text, not an object, so it never grounds; the someone
    does. With no someone named ("ask about the lanterns"), the one other
    toon here is assumed; a bare "ask <someone>" lists what they could tell you.
    Anything else defers to the LLM."""
    low = rest.lower()
    if low.startswith("about "):
        who, topic = "", rest[6:]
    else:
        idx = low.find(" about ")
        who, topic = (rest[:idx], rest[idx + 7:]) if idx >= 0 else (rest, "")
    who = _strip_article(who)
    if not who:
        others = [o for o in objects.in_scope(actor_id)
                  if o.kind == "toon" and o.id != actor_id]
        if len(others) != 1:
            return [Parse("ask")] if not topic else None
        return [Parse("ask", dobj_id=others[0].id, args=topic.strip())]
    matches = [o for o in _ground(actor_id, who) if o.kind == "toon"]
    if len(matches) == 1:
        return [Parse("ask", dobj_id=matches[0].id, args=topic.strip())]
    if len(matches) > 1:
        return _clarify("ask", "dobj", who, matches)
    return None


def _verb_by_word(world_id: str | None, word: str) -> verbs.VerbSpec | None:
    """Engine verb by name/alias (multi-word aliases included), then world
    verb by name/alias."""
    spec = verbs.VERBS.get(word)
    if spec is not None:
        return spec
    for v in verbs.VERBS.values():
        if word in v.aliases:
            return v
    if world_id:
        return worldverbs.get(world_id, word)
    return None


def _ground(actor_id: str, name: str) -> list[objects.Object]:
    """All in-scope matches for a typed name, with IT resolved to the
    remembered referent (when it is still in scope)."""
    needle = _strip_article(name).strip()
    if not needle:
        return []
    if needle.lower() == "it":
        ref = pronouns.it_referent(actor_id)
        if ref:
            for o in objects.in_scope(actor_id):
                if o.id == ref:
                    return [o]
        return []
    return objects.find_all_in_scope_by_name(actor_id, needle)


def _clarify(verb, slot, name, matches, iobj_id=None, dobj_hint=None):
    options = tuple((o.id, o.name) for o in matches[:6])
    dobj_id = None
    if dobj_hint is not None:
        actor_id, dobj_part = dobj_hint
        dobj_matches = _ground(actor_id, _strip_article(dobj_part))
        if len(dobj_matches) == 1:
            dobj_id = dobj_matches[0].id
    return Clarify(verb=verb, slot=slot, name=_strip_article(name).lower(),
                   options=options, dobj_id=dobj_id, iobj_id=iobj_id)


def _split_prep(spec: verbs.VerbSpec, rest: str) -> tuple[str, str | None]:
    """Split 'X <prep> Y' on the verb's authored prepositions (longest first
    so 'inside' wins over 'in'). Returns (dobj_part, iobj_part|None)."""
    low = rest.lower()
    for prep in sorted(spec.preps, key=len, reverse=True):
        idx = low.find(f" {prep} ")
        if idx >= 0:
            return rest[:idx].strip(), rest[idx + len(prep) + 2:].strip()
    return rest, None


def _gwim_fill(actor_id: str, default_filter, exclude) -> objects.Object | None:
    """GWIM: fill an omitted slot iff EXACTLY ONE in-scope thing matches the
    verb's authored filter {"key": K, "eq": V} ('light match' finds the one
    matchbook). Zero or several = don't guess."""
    if not isinstance(default_filter, dict):
        return None
    key = default_filter.get("key")
    if not isinstance(key, str):
        return None
    want = default_filter.get("eq", True)
    matches = [
        o for o in objects.in_scope(actor_id)
        if o.kind == "thing" and o.properties.get(key) == want
        and (exclude is None or o.id != exclude)
    ]
    return matches[0] if len(matches) == 1 else None


def _fill_iobj_default(actor_id, spec, parses: list[Parse]) -> list[Parse]:
    if not parses or parses[0].iobj_id is not None:
        return parses
    filled = _gwim_fill(actor_id, spec.iobj_default, exclude=parses[0].dobj_id)
    if filled is None:
        return parses
    p = parses[0]
    return [Parse(p.verb, dobj_id=p.dobj_id, iobj_id=filled.id, args=p.args)] \
        + parses[1:]


# ---- ALL / AND / EXCEPT ---------------------------------------------------------


def _expand_multi(
    actor_id: str, verb: str, dobj_part: str, iobj_id: str | None
):
    """Expand 'all', 'all except X and Y', and 'X and Y' noun lists into
    per-item commands. None = not a multi form (single-name path handles it).
    Missing names in a list become dobj_name commands ('you don't see X');
    a name matching several things takes the first (lists stay simple —
    single-target commands get the clarify treatment instead)."""
    part = dobj_part.strip()
    low = part.lower()
    is_all = low == "all" or low.startswith("all ") or low == "everything"
    listy = _AND_SPLIT.search(part) is not None
    if not is_all and not listy:
        return None

    if is_all:
        excepts: list[str] = []
        m = re.match(r"^(?:all|everything)(?:\s+(?:except|but)\s+(.*))?$",
                     low, re.IGNORECASE)
        if m is None:
            return None
        if m.group(1):
            excepts = [_strip_article(n).lower()
                       for n in _AND_SPLIT.split(m.group(1)) if n.strip()]
        candidates = _all_candidates(actor_id, verb, iobj_id)
        kept = []
        for o in candidates:
            names = [o.name.lower()] + [str(a).lower() for a in o.aliases]
            if any(e in names for e in excepts):
                continue
            kept.append(o)
        if not kept:
            msgs = {
                # "carry off" over "take": a room full of furniture and
                # fixtures should read as "nothing portable", not "nothing
                # here" (playtest 2026-07-02).
                "take": "There's nothing here you can carry off.",
                "drop": "You're carrying nothing.",
                "put": "You're carrying nothing.",
            }
            return LineParse(message=msgs.get(verb, "Nothing to do."))
        return [Parse(verb, dobj_id=o.id, iobj_id=iobj_id) for o in kept]

    # AND-list of names. A list is only a list if something in it is here
    # (playtest 2026-09-26: "drop a pebble into the well and listen" read back
    # "you don't see the listen here"); otherwise the single-name path decides.
    out: list[Parse] = []
    grounded = 0
    for raw_name in _AND_SPLIT.split(part):
        name = _strip_article(raw_name)
        if not name:
            continue
        matches = _ground(actor_id, name)
        if not matches:
            out.append(Parse(verb, dobj_name=name, iobj_id=iobj_id))
        else:
            grounded += 1
            out.append(Parse(verb, dobj_id=matches[0].id, iobj_id=iobj_id))
    return out if out and grounded else None


def _all_candidates(
    actor_id: str, verb: str, iobj_id: str | None
) -> list[objects.Object]:
    """What ALL means per verb: take = the room's takeable things (container
    contents excluded, like the original); drop/put = everything carried
    (minus the destination container)."""
    actor = objects.get(actor_id)
    if actor is None:
        return []
    if verb == "take":
        room_id = actor.location_id
        if room_id is None:
            return []
        pool: list[objects.Object] = []
        for o in objects.contents(room_id, kind="thing"):
            pool.append(o)
            # ALL reaches one level into see-through room containers and
            # surfaces (the sack on the kitchen table), matching the
            # original's behavior; it never empties a container it is
            # about to take.
            pool.extend(objects.visible_contents(o))
        return [o for o in pool if "take" in objects.verbs_for(o)]
    carried = objects.contents(actor_id, kind="thing")
    if verb == "put" and iobj_id is not None:
        carried = [o for o in carried if o.id != iobj_id]
    return carried


# ---- the LLM fallback --------------------------------------------------------


async def _llm_parse(actor_id: str, text: str, room: rooms.Room | None) -> Parse:
    actor = objects.get(actor_id)
    world_id = actor.world_id if actor is not None else ""
    vocab = _verb_vocabulary(actor_id, room.id if room else "", world_id)
    scope = _scope_entries(actor_id)
    try:
        result = await client.acompletion_json(
            system=SYSTEM, user=_user_prompt(text, vocab, scope),
            purpose="parser",
        )
    except client.LLMUnavailable as e:
        return Parse("none", error=str(e))

    if not isinstance(result, dict):
        return NONE
    verb = str(result.get("verb", "none")).strip().lower()
    if verb == "none" or verb not in {v["name"] for v in vocab}:
        return NONE
    args = result.get("args", "")
    args = args.strip() if isinstance(args, str) else ""
    scope_ids = {e["id"] for e in scope}
    raw_dobj = result.get("dobj_id")
    raw_iobj = result.get("iobj_id")
    dobj_id = raw_dobj if isinstance(raw_dobj, str) and raw_dobj in scope_ids else None
    iobj_id = raw_iobj if isinstance(raw_iobj, str) and raw_iobj in scope_ids else None
    # Fail safe: the model named a target that isn't in scope (hallucinated or
    # ambiguous) -> no command, a gentle "don't understand" (not a wrong action).
    if isinstance(raw_dobj, str) and raw_dobj and dobj_id is None:
        return NONE
    if isinstance(raw_iobj, str) and raw_iobj and iobj_id is None:
        return NONE
    return Parse(verb, dobj_id=dobj_id, iobj_id=iobj_id, args=args)


# ---- vocabulary + scope for the LLM call -------------------------------


def _room_data_skill_names(room_id: str) -> set[str]:
    """Data-skill names available in this room (core skills excluded)."""
    if not room_id:
        return set()
    return {
        s.name for s in registry.list_available_for_room(room_id) if s.kind == "data"
    }


def _is_npc_bound(skill_name: str) -> bool:
    """A data skill is NPC-bound (reached via `talk`, not as its own verb) when
    a toon object exists under the `t-<name>` convention."""
    obj = objects.get(f"t-{skill_name}")
    return obj is not None and obj.kind == "toon"


def _verb_vocabulary(actor_id: str, room_id: str, world_id: str) -> list[dict]:
    """The verbs the model may choose from: the closed engine verbs, the
    world's declared verbs (criterion 9: world vocabulary joins the grounding
    prompt), plus any in-scope room-affordance (non-NPC) data skills."""
    vocab = [
        {"name": v.name, "description": v.description}
        for v in verbs.VERBS.values()
    ]
    if world_id:
        for spec in worldverbs.all_specs(world_id):
            vocab.append({"name": spec.name, "description": spec.description})
    for name in sorted(_room_data_skill_names(room_id)):
        if not _is_npc_bound(name):
            spec = registry.find(name)
            desc = spec.description if spec else f"the {name} affordance"
            vocab.append({"name": name, "description": desc})
    return vocab


def _scope_entries(actor_id: str) -> list[dict]:
    """In-scope objects (excluding the actor + prototypes) as grounding rows."""
    out: list[dict] = []
    for o in objects.in_scope(actor_id):
        if o.id == actor_id or o.kind == "prototype":
            continue
        out.append(
            {"id": o.id, "name": o.name, "aliases": o.aliases, "kind": o.kind,
             "verbs": objects.verbs_for(o)}
        )
    return out


def _user_prompt(text: str, vocab: list[dict], scope: list[dict]) -> str:
    verb_lines = "\n".join(f"- {v['name']}: {v['description']}" for v in vocab)
    if scope:
        scope_lines = "\n".join(
            f"- {e['id']}: {e['name']} ({e['kind']})"
            + (f" [aliases: {', '.join(e['aliases'])}]" if e["aliases"] else "")
            for e in scope
        )
    else:
        scope_lines = "(nothing of note nearby)"
    return (
        f"Verbs:\n{verb_lines}\n\n"
        f"Scope (objects you can refer to):\n{scope_lines}\n\n"
        f"Player input: {text}\n\n"
        'Respond with JSON: {"verb": "...", "dobj_id": ..., "iobj_id": ..., "args": "..."}'
    )
