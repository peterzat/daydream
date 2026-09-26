"""Grounded NPC dialogue for voice-sheet NPCs (SPEC 2026-09-26 criteria 6,
10, 11).

The old dialogue prompt saw a persona, the player's line, and three
embedding-recalled memories: never the quest state, where things are, what
the player had done, or the NPC's own pronouns, so it invented facts and
villagers and opened most replies the same way (docs/PIVOT.md section 1;
the BEFORE run in docs/model-eval/). This path injects the state instead:

- the NPC's authored voice sheet (`properties.voice`: pronouns, sheet,
  habits, sample lines, what it never does) and current wants;
- where it is, the time of day, who is present, and the closed list of the
  village's people (no one else exists);
- what it KNOWS (`knowledge.known_facts`: deeds by this player first,
  gossip about others, authored facts), and nothing else;
- its relationship with this player (by name) and their recent exchanges;
- its own recent openings, to avoid;
- the open beats it may advance, as a JSON-schema enum on `advance`.

ONE round of calls (n-best in parallel, never a serial chain), warm
sampling, reranked mechanically: pronoun canon, point of view, opener
novelty, length. The engine then applies the chosen beat deterministically
(`story.advance_beat` re-checks it at commit) and speaks the beat's AUTHORED
line; with no beat, the model's line is the reply.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re

from daydream import events, knowledge, objects, rooms, story, worldstate
from daydream.llm import client as llm_client
from daydream.llm import safety

logger = logging.getLogger(__name__)

OPENERS_PREFIX = "openers:"
OPENER_MEMORY = 8
MAX_LINE_CHARS = 420
_BANNED_FALLBACK = "The dream won't hold that thought."
_QUOTED = re.compile(r"[\"“].*?[\"”]|(?<![A-Za-z])['‘].*?['’](?![A-Za-z])", re.S)
_PRONOUN_FORMS = {
    "they": {"they", "them", "their", "theirs", "themself", "themselves"},
    "she": {"she", "her", "hers", "herself"},
    "he": {"he", "him", "his", "himself"},
    "it": {"it", "its", "itself"},
}
_GENDERED = {"he", "him", "his", "himself", "she", "her", "hers", "herself"}


def temperature() -> float:
    try:
        return float(os.environ.get("DAYDREAM_DIALOGUE_TEMPERATURE", "0.7"))
    except ValueError:
        return 0.7


def nbest() -> int:
    try:
        return max(1, min(3, int(os.environ.get("DAYDREAM_DIALOGUE_NBEST", "2"))))
    except ValueError:
        return 2


# ---- context --------------------------------------------------------------


def _pronoun_key(voice: dict) -> str:
    p = str(voice.get("pronouns", "they")).lower()
    for key in ("they", "she", "he", "it"):
        if p.startswith(key):
            return key
    return "they"


def _wants(npc: objects.Object, actor: objects.Object, voice: dict) -> list[str]:
    from daydream import rules

    ctx = rules._build_ctx(actor, None, None, actor.location_id or "", npc, "wants")
    out = []
    for w in voice.get("wants") or []:
        if isinstance(w, str) and w.strip():
            out.append(w.strip())
        elif isinstance(w, dict) and isinstance(w.get("text"), str) \
                and rules.conditions_hold(w.get("if"), ctx):
            out.append(w["text"].strip())
    return out


def _cast(world_id: str, here_ids: set[str]) -> list[str]:
    """The village's people, closed: every resident NPC (a toon with a voice
    sheet and a room) plus any guest standing here. One line each."""
    rows = []
    from daydream import db

    for r in db.get_conn().execute(
        "SELECT * FROM objects WHERE world_id = ? AND kind = 'toon' "
        "AND is_human_controlled = 0 ORDER BY slot", (world_id,)):
        t = objects.Object.from_row(r)
        voice = t.properties.get("voice")
        if not isinstance(voice, dict):
            continue
        if t.location_id is None and t.id not in here_ids:
            continue
        role = voice.get("role") or t.seed
        rows.append(f"{t.name} ({str(role)[:80]})")
    return rows


def recent_openers(world_id: str, npc_id: str) -> list[str]:
    v = worldstate.get(world_id, OPENERS_PREFIX + npc_id)
    return [x for x in v if isinstance(x, str)] if isinstance(v, list) else []


def opener_key(text: str, n: int = 6) -> str:
    return " ".join(re.findall(r"[a-z']+", (text or "").lower())[:n])


def _note_opener(world_id: str, npc_id: str, line: str) -> None:
    log = recent_openers(world_id, npc_id)
    log.append(" ".join((line or "").split()[:8]))
    worldstate.set(world_id, OPENERS_PREFIX + npc_id, log[-OPENER_MEMORY:])


def build_prompt(actor: objects.Object, npc: objects.Object, text: str,
                 room_id: str, beats: list[tuple[str, str, dict]]) -> tuple[str, str, list[str]]:
    """(system, user, advance ids). Pure over the current world state."""
    from daydream import village

    world_id = npc.world_id
    voice = npc.properties.get("voice") if isinstance(npc.properties.get("voice"), dict) else {}
    pkey = _pronoun_key(voice)
    forms = "/".join(sorted(_PRONOUN_FORMS[pkey], key=len)[:3])
    silent = bool(voice.get("silent"))
    speech = (
        f'"say": "" (always empty: {npc.name} never speaks words; the gesture is the '
        "whole reply)"
        if silent else
        f'"say": {npc.name}\'s spoken words only, one or two short sentences, WITHOUT '
        f"quotation marks; it may address {actor.name} as you"
    )
    system = (
        f"You are the voice of {npc.name}, a character in a cozy watercolor story "
        f"village, replying to {actor.name}. Return strict JSON with three fields. "
        f'"gesture": one short third-person action that starts with the name '
        f"{npc.name} (for example: {npc.name} sets down a tool.). {speech}. "
        '"advance": a story-moment id from the list below, or "none". '
        f"{npc.name} uses {voice.get('pronouns', 'they/them')} pronouns: in the "
        f"gesture say {npc.name} or {forms}, never any other pronoun, and never call "
        "the player 'you' in the gesture. Say ONLY what the sections below support: "
        "never invent a person, place, object, animal, or event that is not listed, "
        "and never claim something happened that the sections do not say. Asked "
        "about something not listed, say honestly that you don't know. Do not echo "
        "your own recent lines: new words, a new opening, and a pet name for the "
        "player only once in a while. Cozy and warm, soft stakes allowed, no urgency, "
        "no modern things."
    )
    room = rooms.get_room(room_id)
    here = [t for t in objects.contents(room_id, kind="toon") if t.id != npc.id]
    here_names = ", ".join(t.name for t in here) or "no one else"
    sections: list[str] = []
    sections.append(f"WHO {npc.name.upper()} IS: {voice.get('sheet', npc.seed)}")
    habits = [h for h in voice.get("habits") or [] if isinstance(h, str)]
    if habits:
        sections.append("HOW THEY SPEAK: " + "; ".join(habits))
    samples = [s for s in voice.get("samples") or [] if isinstance(s, str)]
    if samples:
        rng = worldstate.rng_stable(world_id, f"samples:{npc.id}:{len(recent_openers(world_id, npc.id))}")
        pick = rng.sample(samples, min(4, len(samples)))
        sections.append("THEIR VOICE, FOR FLAVOR (never repeat these verbatim):\n"
                        + "\n".join(f"- {s}" for s in pick))
    never = [n for n in voice.get("never") or [] if isinstance(n, str)]
    if never:
        sections.append("NEVER: " + "; ".join(never))
    wants = _wants(npc, actor, voice)
    if wants:
        sections.append("WHAT THEY WANT RIGHT NOW: " + "; ".join(wants))
    ph = village.phase(world_id)
    when = "" if ph == "stopped" else f" It is day {village.day(world_id)}, {ph}."
    if room is not None:
        sections.append(f"WHERE: {room.title}: {room.seed}.{when}")
    sections.append(f"WHO IS HERE: {actor.name} (the player), {here_names}.")
    cast = _cast(world_id, {t.id for t in here})
    if cast:
        sections.append("THE VILLAGE'S PEOPLE (no one else exists): " + "; ".join(cast))
    facts = knowledge.known_facts(npc, actor.id, limit=14)
    if facts:
        sections.append(f"WHAT {npc.name.upper()} KNOWS (the only facts they may state):\n"
                        + "\n".join(f"- {f['text']}" for f in facts))
    else:
        sections.append(f"WHAT {npc.name.upper()} KNOWS: nothing beyond the above.")
    rel = story.relationship_label(world_id, npc.id, actor.id)
    lines = [f"{npc.name} and {actor.name}: {rel}."]
    for ex in story.recent_exchanges(world_id, npc.id, actor.id)[-3:]:
        lines.append(f"- {actor.name} said: \"{ex.get('said', '')}\" / "
                     f"{npc.name} replied: {ex.get('reply', '')}")
    sections.append("\n".join(lines))
    lines_said = recent_lines(world_id, npc.id)
    if lines_said:
        sections.append(f"{npc.name.upper()}'S LAST FEW LINES (never reuse their words, "
                        "openings, or pet names):\n"
                        + "\n".join(f"- {x}" for x in lines_said[-4:]))
    ids: list[str] = []
    if beats:
        blines = []
        for arc_id, beat_id, beat in beats:
            bid = f"{arc_id}/{beat_id}"
            ids.append(bid)
            hint = beat.get("hint") or beat.get("topic") or beat_id
            blines.append(f"- {bid}: when {hint}")
        sections.append(
            "STORY MOMENTS (set advance to one ONLY if the player's words clearly "
            "bring it about; otherwise \"none\"):\n" + "\n".join(blines))
    sections.append(f"{actor.name} says: {safety.wrap_player_input(text)}")
    return system, "\n\n".join(sections), ids


def _schema(ids: list[str]) -> dict:
    return {"type": "json_schema", "json_schema": {"name": "reply", "schema": {
        "type": "object",
        "properties": {"gesture": {"type": "string"}, "say": {"type": "string"},
                       "advance": {"type": "string", "enum": ids + ["none"]}},
        "required": ["gesture", "say", "advance"], "additionalProperties": False}}}


LINES_PREFIX = "lines:"
LINE_MEMORY = 10


def recent_lines(world_id: str, npc_id: str) -> list[str]:
    v = worldstate.get(world_id, LINES_PREFIX + npc_id)
    return [x for x in v if isinstance(x, str)] if isinstance(v, list) else []


def _note_line(world_id: str, npc_id: str, line: str) -> None:
    log = recent_lines(world_id, npc_id)
    log.append(line)
    worldstate.set(world_id, LINES_PREFIX + npc_id, log[-LINE_MEMORY:])


_QUOTE_CHARS = "\"'\u201c\u201d\u2018\u2019"


def compose(npc_name: str, gesture: str, say: str) -> str:
    """The reply as the player reads it: the NPC's gesture (always naming
    them, so the line is attributed) and their words in quotes."""
    g = " ".join((gesture or "").split()).strip()
    words = " ".join((say or "").split()).strip().strip(_QUOTE_CHARS).strip()
    if g and npc_name.lower() not in g.lower():
        g = f"{npc_name} {g[0].lower()}{g[1:]}"
    if g and g[-1] not in ".!?":
        g += "."
    if not words:
        return g
    return f"{g} '{words}'" if g else f"{npc_name} says, '{words}'"


# ---- scoring ----------------------------------------------------------------


def _tail(text: str, n: int = 2) -> str:
    return " ".join(re.findall(r"[a-z']+", (text or "").lower())[-n:])


def score(line: str, npc_name: str, pkey: str, openers: list[str],
          recent: list[str] | None = None) -> int:
    """Lower is better. Mechanical: pronoun canon, point of view, opener
    novelty against this NPC's recent openings, a verbal tic (the same
    closing words as a recent line: the ', friend' on every reply), length."""
    penalty = 0
    for prev in recent or []:
        if _tail(line) and _tail(line) == _tail(prev):
            penalty += 3
            break
    bare = _QUOTED.sub(" ", line)
    words = set(re.findall(r"[a-z]+", bare.lower()))
    wrong = (_GENDERED | _PRONOUN_FORMS["it"]) - _PRONOUN_FORMS[pkey]
    if pkey == "they":
        wrong = _GENDERED
    if words & wrong:
        penalty += 10
    if re.search(r"\byou(r|rs|rself)?\b", bare, re.I):
        penalty += 5
    key = opener_key(line)
    if any(opener_key(o) == key for o in openers):
        penalty += 4
    k3 = opener_key(line, 3)
    if any(opener_key(o, 3) == k3 for o in openers):
        penalty += 1
    if len(line) > 360:
        penalty += 2
    return penalty


def _clean(result, ids: list[str], npc_name: str = "") -> tuple[str, str | None, str, str] | None:
    """(composed line, advance, gesture, say) or None when unusable."""
    if not isinstance(result, dict) or safety.parse_refusal(result) is not None:
        return None
    gesture = result.get("gesture") if isinstance(result.get("gesture"), str) else ""
    say = result.get("say") if isinstance(result.get("say"), str) else ""
    if gesture or say:
        line = compose(npc_name, gesture, say)
    else:
        line = result.get("line")
    if not isinstance(line, str) or not line.strip():
        return None
    line = " ".join(line.split())[:MAX_LINE_CHARS]
    if safety.first_banned(line) is not None:
        return None
    adv = result.get("advance")
    return line, (adv if adv in ids else None), gesture, say


DEFAULT_PET_NAMES = ("little one", "friend", "pet", "lamb", "dear", "love", "my dear")


def _gesture_key(text: str) -> str:
    return opener_key(text, 4)


def _fresh_gesture(npc: objects.Object, gesture: str, recent: list[str]) -> str:
    """A gesture that opens the way a recent line opened (the model's
    favourite: the same lean on the same broom) is swapped for one of the NPC's
    own AUTHORED gestures (its drift pools), never repeated soon (variants)."""
    from daydream import variants

    key = _gesture_key(compose(npc.name, gesture, ""))
    if not key or not any(_gesture_key(r) == key for r in recent):
        return gesture
    pools = npc.properties.get("drift_pools")
    lines = [ln for v in (pools.values() if isinstance(pools, dict) else [])
             if isinstance(v, list) for ln in v if isinstance(ln, str)]
    lines = [ln for ln in lines if not any(_gesture_key(r) == _gesture_key(ln) for r in recent)]
    if not lines:
        return gesture
    return variants.pick(npc.world_id, f"gesture:{npc.id}", lines, None) or gesture


def _dampen_pet_names(npc: objects.Object, say: str, recent: list[str]) -> str:
    """Drop a pet name for the player ("little one", "friend") when this NPC
    already used it in either of its last two lines: warmth, not a tic."""
    voice = npc.properties.get("voice") if isinstance(npc.properties.get("voice"), dict) else {}
    names = [n for n in voice.get("pet_names") or DEFAULT_PET_NAMES if isinstance(n, str)]
    last = " ".join(recent[-2:]).lower()
    out = say
    for n in names:
        if re.search(rf"\b{re.escape(n)}\b", last):
            out = re.sub(rf",\s*{re.escape(n)}\b", "", out, flags=re.I)
            out = re.sub(rf"^\s*{re.escape(n)},\s*", "", out, flags=re.I)
    out = out.strip()
    return out[:1].upper() + out[1:] if out else say


# ---- the talk turn -----------------------------------------------------------


async def talk(actor: objects.Object, npc: objects.Object, text: str, room_id: str) -> bool:
    world_id = npc.world_id
    text = (text or "").strip() or "Hello."
    if safety.first_banned(text) is not None:
        events.append("system", None, "narrate", {"text": _BANNED_FALLBACK}, room_id=room_id)
        return False
    beats = story.open_beats_for(world_id, npc.id, actor.id)
    system, user, ids = build_prompt(actor, npc, text, room_id, beats)
    voice = npc.properties.get("voice") if isinstance(npc.properties.get("voice"), dict) else {}
    pkey = _pronoun_key(voice)
    openers = recent_openers(world_id, npc.id)

    async def one():
        return await llm_client.acompletion_json(
            system=system, user=user, purpose="dialogue", temperature=temperature(),
            max_tokens=200, timeout=15.0, response_format=_schema(ids),
        )

    results = await asyncio.gather(*(one() for _ in range(nbest())),
                                   return_exceptions=True)
    candidates = []
    refusal = None
    for r in results:
        if isinstance(r, BaseException):
            continue
        ref = safety.parse_refusal(r)
        if ref is not None and refusal is None:
            refusal = ref.reason
        c = _clean(r, ids, npc.name)
        if c is not None:
            candidates.append(c)
    if not candidates:
        if all(isinstance(r, BaseException) for r in results):
            events.append("system", None, "narrate", {"text": llm_client.FOGGY_TEXT},
                          room_id=room_id)
        else:
            events.append("system", None, "narrate",
                          {"text": refusal or _BANNED_FALLBACK}, room_id=room_id)
        return False
    said = recent_lines(world_id, npc.id)
    candidates.sort(key=lambda c: score(c[0], npc.name, pkey, openers, said[-3:]))
    line, advance, gesture, say = candidates[0]
    if gesture or say:
        # The gesture look-back is long (eight lines): a model's favourite
        # opening recurs every four or five replies, not back to back.
        g2 = _fresh_gesture(npc, gesture, said[-8:])
        s2 = _dampen_pet_names(npc, say, said)
        if (g2, s2) != (gesture, say):
            line = compose(npc.name, g2, s2)
    story.note_conversation(world_id, npc.id, actor.id)
    spoken = line
    if advance is not None:
        arc_id, beat_id = advance.split("/", 1)
        beat = story.beat_def(world_id, arc_id, beat_id) or {}
        authored = bool(beat.get("text") or beat.get("variants"))
        ev = story.advance_beat(world_id, arc_id, beat_id, actor.id, room_id,
                                tell=authored)
        if ev is not None and authored:
            spoken = None  # the author wrote this moment; it has been told
    if spoken is not None:
        events.append("system", None, "narrate", {"text": spoken}, room_id=room_id)
        _note_opener(world_id, npc.id, spoken)
        _note_line(world_id, npc.id, spoken)
    story.remember_exchange(world_id, npc.id, actor.id, text, spoken or "(the moment)")
    return True
