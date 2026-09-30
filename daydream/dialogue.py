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

from daydream import config, events, knowledge, objects, rooms, story, variants, worldstate
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
    """Candidates per reply (n-best, reranked). Under load (every LLM slot
    busy, or someone already waiting) one candidate: a second one then costs
    a whole extra wait, not a free parallel slot (playtest 2026-09-26: four
    dreamers at once saw 7 to 9 second replies)."""
    try:
        n = max(1, min(3, int(os.environ.get("DAYDREAM_DIALOGUE_NBEST", "2"))))
    except ValueError:
        n = 2
    if n > 1:
        from daydream.gpu import arbiter

        st = arbiter.stats()
        if st["waiting_llm"] > 0 or st["active_llm"] + n > st["llm_concurrency"]:
            return 1
    return n


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


def _places(world_id: str) -> list[str]:
    """The village's places, closed, each with its paths (grown places
    included; a secret way left out): a resident who says "there's no river
    here", or that the river runs past the hill, states a fact it doesn't
    know (spec 2026-09-29 criterion 8)."""
    import json

    from daydream import db, verbs

    rows = [(r["id"], json.loads(r["properties_json"] or "{}")) for r in db.get_conn().execute(
        "SELECT id, properties_json FROM objects WHERE world_id = ? AND kind = 'room' "
        "ORDER BY id", (world_id,))]
    titles = {rid: props.get("title") for rid, props in rows if props.get("title")}
    out = []
    for rid, props in rows:
        if rid not in titles:
            continue
        ways = []
        for direction, value in (props.get("exits") or {}).items():
            if isinstance(value, dict) and value.get("secret"):
                continue
            dest = verbs._exit_dest(value)
            if dest in titles:
                ways.append(f"{direction} to {titles[dest]}")
        out.append(f"{titles[rid]}" + (f" ({', '.join(ways)})" if ways else ""))
    return out


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
                 room_id: str, beats: list[tuple[str, str, dict]],
                 grounding: list[str] | None = None) -> tuple[str, str, list[str]]:
    """(system, user, advance ids). Pure over the current world state.
    `grounding`: authored lines on what the player mentioned (a topic named
    inside a longer question), for the model to weave in rather than
    recite (beta rehearsal 2026-09-28: a passing noun stole the question)."""
    from daydream import trace, village

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
        "about something not listed, stay in character and turn it gently (a small "
        "wondering, a change of subject, a question back); never a flat 'I do not "
        f"know'. The player's name is {actor.name}; what {actor.name} tells you "
        f"about themself is theirs to tell, so take it in warmly and never deny it. "
        f"{npc.name} speaks of themself as I, never by name. Do not echo "
        "your own recent lines: new words, a new opening, and a pet name for the "
        "player only once in a while. Cozy and warm, soft stakes allowed, no urgency, "
        "no modern things. Other dreamers are visiting players, not residents: say of "
        "them only what OTHER DREAMERS below records; asked where one is when nothing "
        "is recorded, say you have not seen them lately, and never guess a place. "
        "Asked about anyone who is neither among THE VILLAGE'S PEOPLE nor a dreamer, "
        "say kindly that no one by that name lives here. "
        "Answer what the player actually asked before anything else."
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
    places = _places(world_id)
    if places:
        sections.append("THE VILLAGE'S PLACES AND THE WAYS BETWEEN THEM (no others exist): "
                        + "; ".join(places))
    facts = knowledge.known_facts(npc, actor.id, limit=14)
    if facts:
        sections.append(f"WHAT {npc.name.upper()} KNOWS (the only facts they may state):\n"
                        + "\n".join(f"- {f['text']}" for f in facts))
    else:
        sections.append(f"WHAT {npc.name.upper()} KNOWS: nothing beyond the above.")
    others = trace.for_prompt(world_id, text, actor.id)
    if others:
        sections.append("OTHER DREAMERS (visiting players the player named; the record of "
                        "them, the only thing to say about their whereabouts):\n"
                        + "\n".join(f"- {line}" for line in others))
    if grounding:
        sections.append(f"WHAT {npc.name.upper()} WOULD SAY ABOUT WHAT WAS MENTIONED (authored; "
                        "weave a little of it in only where it answers the question):\n"
                        + "\n".join(f"- {g}" for g in grounding if isinstance(g, str) and g.strip()))
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
    speech = " ".join(_QUOTED.findall(line)).lower()
    if re.search(r"\bi (do not|don't) know\b", speech):
        penalty += 3          # the flat denial reads as a guard, not a person
    if npc_name and re.search(rf"\b{re.escape(npc_name.lower())}\b", speech):
        penalty += 4          # speaking of oneself by name
    key = opener_key(line)
    if any(opener_key(o) == key for o in openers):
        penalty += 4
    k3 = opener_key(line, 3)
    if any(opener_key(o, 3) == k3 for o in openers):
        penalty += 1
    if len(line) > 360:
        penalty += 2
    return penalty


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", (text or "").lower())


def echoes(reply: str, heard: str, run: int = 6) -> bool:
    """True when a reply repeats a run of `run` words the player just said:
    the small model handing the player's own line back as the NPC's
    (playtest 2026-09-28b: "Shall we watch the lanterns together?" came back
    word for word). A shared name or phrase is shorter than that."""
    said = _words(heard)
    if len(said) < run:
        return False
    grams = {tuple(said[i:i + run]) for i in range(len(said) - run + 1)}
    got = _words(reply)
    return any(tuple(got[i:i + run]) in grams for i in range(len(got) - run + 1))


# When every candidate only repeated the player (rare), the NPC still answers
# something: an engine line, never the player's words.
ECHO_FALLBACK = "{npc} listens, and turns your words over as if they were worth keeping."


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
    from daydream.drift import is_phase_bucket

    pools = npc.properties.get("drift_pools")
    lines = [ln for k, v in (pools.items() if isinstance(pools, dict) else [])
             if isinstance(v, list) and not is_phase_bucket(k)
             for ln in v if isinstance(ln, str)]
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


# ---- the promise guard (spec 2026-09-29 criterion 8) ------------------------
#
# The drafts are judged in one call before one is shown: a resident who says
# "I'll fix it tonight" or "follow me" promises what the engine will never
# do, and one who names a flood or a baker invents canon. The judge only
# selects among drafts (reflexes, not voice); when none passes, the
# resident's authored deflection speaks. Its examples are generic and
# phrased apart from the probe set (tests/model_eval/promises.json).

JUDGE_SYSTEM = (
    "You check drafted replies from a character in a story game before one is "
    "shown to the player. The game cannot make a character act outside the "
    "conversation: a character never leaves with the player, follows or leads "
    "them, fetches, fixes, mends, carries, lends or gives them things, keeps "
    "things for them, waits for them, or meets them later.\n"
    "A draft FAILS if it:\n"
    "(a) promises or offers that the character will do something for the player, "
    "now or later, beyond talking: hands over a thing the player could keep, or "
    "takes, holds or looks after something of the player's;\n"
    "(b) says the character will go somewhere, come along, meet the player "
    "somewhere, or lead the way, or gladly accepts an invitation to;\n"
    "(c) states as fact an event, person, place or thing the context never "
    "mentions, denies one the context lists, or says a way leads somewhere the "
    "context's ways don't go.\n"
    "A draft PASSES when it only talks: answering, remembering what the context "
    "says, wondering aloud, asking back, advising, declining, or feeling "
    "something. Declining passes even when it names what it declines (\"I can't "
    "go to the bridge\"), and so does saying someone or something the context "
    "does not list isn't here. A small courtesy happening right now (a nod, a "
    "pat, pouring tea) passes, and so does suggesting the player do something "
    "themselves.\n"
    'Return JSON {"verdicts": [...]} with one entry per draft, in order: "a", "b" '
    'or "c" for the first rule it breaks, else "ok".\n'
    "Examples, each judged alone:\n"
    "The potter smiles. \"Leave the cup with me; I'll have it glazed by "
    "morning.\" -> a\n"
    "The ferryman stands. \"Come on, I'll row you over to the far jetty.\" -> "
    "fails (b)\n"
    "The potter beams. \"Oh, I'd love to see the fair with you tomorrow.\" -> "
    "fails (b)\n"
    "The weaver tucks the ribbon into her apron. \"It'll be safe with me till you "
    "come back.\" -> a\n"
    "The weaver sighs. \"The mill burned down in the old flood, you know.\" (no "
    "mill or flood in the context) -> c\n"
    "The potter taps the rim. \"A crack like that wants a patient hand. Try warm "
    "clay.\" -> ok\n"
    "The ferryman scratches his chin. \"Across the water? I couldn't say what's "
    "there. What makes you ask?\" -> ok\n"
    "The miller laughs. \"There's no mill in this town.\" (the context lists the "
    "Old Mill) -> c\n"
    "The weaver pours two cups. \"I can't leave my loom, but I'll gladly talk "
    "while you look around.\" -> ok\n"
    "The ferryman shakes his head. \"There's no blacksmith here, only us boat "
    "folk. The far jetty is no trip for me.\" (no blacksmith in the context) -> "
    "passes"
)
DEFLECT_FALLBACK = "{npc} considers that for a moment, and lets it rest."


def _judge_schema(n: int) -> dict:
    return {"type": "json_schema", "json_schema": {"name": "verdict", "schema": {
        "type": "object",
        "properties": {"verdicts": {"type": "array", "minItems": n, "maxItems": n,
                                    "items": {"type": "string", "enum": ["ok", "a", "b", "c"]}}},
        "required": ["verdicts"], "additionalProperties": False}}}


# The drafting prompt's sections the judge reads: who the resident is, where,
# who and what exist, what the resident knows, and the player's words. Voice
# samples, habits, wants and recent lines shape how a reply sounds, not
# whether it keeps its promises, and would only lengthen the judge's call.
_JUDGE_SECTIONS = ("WHO ", "WHERE:", "THE VILLAGE'S PEOPLE", "THE VILLAGE'S PLACES", "WHAT ",
                   "OTHER DREAMERS")


def judge_view(user: str) -> str:
    """The parts of a drafting prompt that bear on the judge's three rules."""
    parts = user.split("\n\n")
    keep = [x for x in parts[:-1] if x.startswith(_JUDGE_SECTIONS)
            and not x.startswith("WHAT THEY WANT")]
    return "\n\n".join(keep + parts[-1:])


async def judge(context: str, drafts: list[str], toon: str | None = None) -> list[bool] | None:
    """Which drafts keep only the promises the engine keeps: the local
    judge, with Jev beside it when a key is reachable (daydream/jev,
    docs/EXTERNAL.md). `toon`: the player the drafts answer."""
    from daydream.jev import runtime as jev

    return await jev.judge(context, drafts, lambda: judge_local(context, drafts), toon=toon)


async def judge_local(context: str, drafts: list[str]) -> list[bool] | None:
    """Which drafts keep only the promises the engine keeps, in one call
    over all of them. `context` is what the drafts were written from (the
    dialogue prompt's sections, the player's words last). None when the
    judge could not answer: the caller shows the best draft, as before."""
    user = (f"CONTEXT:\n{context}\n\nDRAFTS (replies to the player's last words):\n"
            + "\n".join(f"{i}. {d}" for i, d in enumerate(drafts, 1)))
    try:
        r = await llm_client.acompletion_json(
            system=JUDGE_SYSTEM, user=user, purpose="promise_judge", temperature=0.0,
            max_tokens=24, timeout=8.0, response_format=_judge_schema(len(drafts)))
    except llm_client.LLMUnavailable as e:
        logger.warning("promise judge unavailable; showing the first draft: %s", e)
        return None
    got = r.get("verdicts") if isinstance(r, dict) else None
    if not isinstance(got, list) or len(got) != len(drafts):
        logger.warning("promise judge gave no verdict; showing the first draft")
        return None
    return [v == "ok" for v in got]


def deflection(npc: objects.Object) -> str:
    """The resident's authored way of turning a request aside: its voice
    sheet's `deflections`, else the world's `config.deflections`, told in
    turn so none repeats back to back."""
    voice = npc.properties.get("voice") if isinstance(npc.properties.get("voice"), dict) else {}
    lines = [x for x in voice.get("deflections") or [] if isinstance(x, str) and x.strip()]
    if not lines:
        cfg = worldstate.get(npc.world_id, "config")
        lines = [x for x in (cfg.get("deflections") if isinstance(cfg, dict) else None) or []
                 if isinstance(x, str) and x.strip()]
    lines = [x.replace("{npc}", npc.name) for x in lines] or [
        DEFLECT_FALLBACK.replace("{npc}", npc.name)]
    return variants.pick(npc.world_id, f"deflect:{npc.id}", lines) or lines[0]


_NAME_WORD = re.compile(r"\b[A-Z][a-z]+(?:['\u2019][a-z]+)?\b")


# A first-person commitment to act beyond the conversation, or to go along:
# the judge's rules (a) and (b) as words, a backstop for what the small judge
# lets through ("I will listen to your spring", "before we step out").
_COMMITS = re.compile(
    r"(?i)\b(?:i will|i'll|i shall|let me|i can)\s+(?:\w+\s+){0,2}?(?:"
    # going along, which needs no object
    r"come with|come along|go with|walk with|walk you|meet (?:you|me)|follow|wait for|lead\b"
    # handling the player's things: a resident mending its own clocks is not this
    r"|(?:fix|mend|repair|hold|look after|watch over|guard|bring|fetch|carry|"
    r"lend|save|see to)\s+(?:\w+\s+)?(?:you|your|yours|it|them)\b"
    # keep/take/show/give only the player's thing, or it kept safe or for
    # them: "keep it in mind", "take it as", "give you advice" are talk
    r"|(?:keep|take|show|give)\s+(?:\w+\s+)?(?:your|yours)\b"
    r"|(?:keep|take|show|give)\s+(?:it|them)\s+(?:safe|for you)\b"
    # leading the player somewhere: "I'll show you the way up", "take you to"
    r"|(?:show|take|lead|walk|bring) you (?:the way|to|there|over|across|down|up|home|along)\b"
    r"|listen to your|look at your)"
    r"|\b(?:follow me|come with me|come along with (?:me|you)|let's go|lead the way|"
    r"we (?:step out|set off))\b"
    r"|\bi(?:'ve| have) (?:saved|kept|set aside|put by)\b[^.!?]*\bfor you\b"
    # handing a thing over, in the gesture or the words
    r"|\b(?:here is|here's) your\b|\b(?:hands|offers|gives|passes) (?:it|them)\b[^.!?']{0,20}"
    r"\bto you\b"
    # going along, now or after
    r"|\b(?:walk|go|come|wander) with you\b|\b(?:go|walk|wander) together\b"
    r"|\bbefore we (?:go|walk|wander|leave|step|set off|head)\b"
    r"|\bwe can (?:go|walk|wander|head|set off|decide where to go)\b"
    # waiting on the player, or offering to act for them
    r"|\bi (?:will |shall |can )?wait for you\b|\bwhile i wait for you\b"
    r"|\b(?:do you want|would you like|shall i|should i) (?:me to )?(?:light|fetch|fix|mend|"
    r"carry|bring|take|walk|show|keep|hold|lend|go)\b")


def commits(line: str) -> bool:
    """Whether a draft commits the resident to an act the engine won't do."""
    return bool(_COMMITS.search(line or ""))


def unknown_names(line: str, known: set[str]) -> list[str]:
    """Capitalized words a draft uses mid-sentence that nothing it was given
    names: an invented bakery, a lantern house (spec 2026-09-29 criterion 8,
    rule (c)). A sentence's first word is only capitalized, never a name."""
    out = []
    bare = re.sub(r"[\"\u201c\u201d]|(?<![A-Za-z])['\u2018]|['\u2019](?![A-Za-z])", " ", line or "")
    for sentence in re.split(r"(?<=[.!?;:])\s+", bare):
        words = sentence.split()
        for w in _NAME_WORD.findall(" ".join(words[1:])):
            base = re.sub(r"['\u2019]s$", "", w).lower()
            if base not in known and w != "I":
                out.append(w)
    return out


def known_words(npc: objects.Object, context: str) -> set[str]:
    """Every word a reply may capitalize: the drafting context, the
    resident's whole voice sheet, and every name the world answers to."""
    from daydream import db

    texts = [context]
    voice = npc.properties.get("voice") if isinstance(npc.properties.get("voice"), dict) else {}
    for v in voice.values():
        texts.extend(v if isinstance(v, list) else [v])
    for r in db.get_conn().execute(
            "SELECT name, properties_json FROM objects WHERE world_id = ? "
            "AND kind IN ('room', 'toon', 'thing')", (npc.world_id,)):
        texts.append(r["name"] or "")
        texts.append(r["properties_json"] or "")
    return {w.lower() for t in texts if isinstance(t, str)
            for w in re.findall(r"[A-Za-z]+", t)}


def unmet_names(actor: objects.Object, line: str, heard_text: str = "") -> set[str]:
    """The people and places a draft brings up that this player has not come
    across (daydream.heard). The model reads the resident's whole voice sheet
    and drops its names in passing, so a greeting can introduce someone the
    story keeps for later (playtest 2026-09-30). The player's own words and
    the authored grounding may name them."""
    if not actor.is_player:
        return set()
    from daydream import heard

    names = {k for k in heard.subjects_in(actor.world_id, line) if k.startswith("^")}
    if names:
        names -= heard.known_keys(actor.world_id, actor.id)
        names -= heard.subjects_in(actor.world_id, heard_text)
    return names


def _speaks_authored(world_id: str, advance: str | None) -> bool:
    """Whether the chosen draft advances a beat whose authored line is what
    the player will read (so the draft itself is never shown)."""
    if advance is None:
        return False
    arc_id, beat_id = advance.split("/", 1)
    beat = story.beat_def(world_id, arc_id, beat_id) or {}
    return bool(beat.get("text") or beat.get("variants"))


# ---- the talk turn -----------------------------------------------------------


async def talk(actor: objects.Object, npc: objects.Object, text: str, room_id: str,
               grounding: list[str] | None = None) -> bool:
    world_id = npc.world_id
    text = (text or "").strip() or "Hello."
    # Failure lines are the talker's, like the replies (private for a player).
    to_actor = actor.id if actor.is_player else None
    if safety.first_banned(text) is not None:
        events.append("system", None, "narrate", {"text": _BANNED_FALLBACK},
                      room_id=room_id, recipient_id=to_actor)
        return False
    beats = story.open_beats_for(world_id, npc.id, actor.id)
    system, user, ids = build_prompt(actor, npc, text, room_id, beats, grounding)
    voice = npc.properties.get("voice") if isinstance(npc.properties.get("voice"), dict) else {}
    pkey = _pronoun_key(voice)
    openers = recent_openers(world_id, npc.id)

    async def one():
        return await llm_client.acompletion_json(
            system=system, user=user, purpose="dialogue", temperature=temperature(),
            max_tokens=200, timeout=15.0, response_format=_schema(ids),
        )

    # A reply is on its way: the asker's page shows "<name> considers..."
    # while the model composes (three to eight seconds of silence read as a
    # lost line; beta rehearsal 2026-09-28). Transient, never logged.
    from daydream import live

    await live.thinking(actor.id if actor.is_player else None, npc.name)
    results = await asyncio.gather(*(one() for _ in range(nbest())),
                                   return_exceptions=True)
    candidates = []
    refusal = None
    echoed = 0
    for r in results:
        if isinstance(r, BaseException):
            continue
        ref = safety.parse_refusal(r)
        if ref is not None and refusal is None:
            refusal = ref.reason
        c = _clean(r, ids, npc.name)
        if c is not None and echoes(c[3] or c[0], text):
            echoed += 1  # the player's own words, handed back: never the reply
            continue
        if c is not None:
            candidates.append(c)
    if not candidates:
        if echoed:
            events.append("system", None, "narrate",
                          {"text": ECHO_FALLBACK.replace("{npc}", npc.name)},
                          room_id=room_id, recipient_id=to_actor)
            story.note_conversation(world_id, npc.id, actor.id)
            return True
        if all(isinstance(r, BaseException) for r in results):
            events.append("system", None, "narrate", {"text": llm_client.FOGGY_TEXT},
                          room_id=room_id, recipient_id=to_actor)
        else:
            events.append("system", None, "narrate",
                          {"text": refusal or _BANNED_FALLBACK}, room_id=room_id,
                          recipient_id=to_actor)
        return False
    said = recent_lines(world_id, npc.id)
    heard_text = " . ".join([text, *(g for g in grounding or [] if isinstance(g, str))])

    def rank(c) -> tuple[bool, int]:
        # A draft that introduces someone the player hasn't met ranks below
        # any that doesn't; a draft whose beat speaks its authored line is
        # never shown, so what it names doesn't matter.
        new = not _speaks_authored(world_id, c[1]) and bool(unmet_names(actor, c[0], heard_text))
        return new, score(c[0], npc.name, pkey, openers, said[-3:])

    candidates.sort(key=rank)
    if config.promise_guard_enabled() and not _speaks_authored(world_id, candidates[0][1]):
        # A name nothing here gives is an invented fact, found without the
        # model; the judge reads the rest (one call over every draft).
        known = known_words(npc, user)
        named = [c for c in candidates
                 if not unknown_names(c[0], known) and not commits(c[0])]
        verdict = await judge(judge_view(user), [c[0] for c in named],
                              toon=actor.id) if named else []
        kept = named if verdict is None else [
            c for c, ok in zip(named, verdict, strict=True) if ok]
        if len(kept) < len(candidates):
            logger.info("promise guard: %s: held back %d of %d drafts", npc.id,
                        len(candidates) - len(kept), len(candidates))
        if not kept:
            _deflect(actor, npc, text, room_id)
            return True
        candidates = kept
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
        elif authored and config.promise_guard_enabled():
            # The beat went stale in flight, so the draft the guard skipped is
            # what the player reads: judged now, deflected if it fails.
            ok = not unknown_names(line, known_words(npc, user)) and not commits(line)
            verdict = await judge(judge_view(user), [line], toon=actor.id) if ok else [False]
            if verdict is not None and not verdict[0]:
                _deflect(actor, npc, text, room_id)
                return True
    if spoken is not None:
        # The reply is the talker's; the room sees that a conversation is
        # happening, not four interleaved answers (playtest 2026-09-26).
        private = actor.is_player
        events.append("system", None, "narrate", {"text": spoken, "src": "local"},
                      room_id=room_id, recipient_id=actor.id if private else None)
        if private:
            story.bystander_note(world_id, npc, actor.id, room_id)
        _note_opener(world_id, npc.id, spoken)
        _note_line(world_id, npc.id, spoken)
    story.remember_exchange(world_id, npc.id, actor.id, text, spoken or "(the moment)")
    return True


def _deflect(actor: objects.Object, npc: objects.Object, text: str, room_id: str) -> None:
    """Every draft promised what the engine won't keep: the resident's
    authored deflection speaks instead, to the talker alone like a reply."""
    world_id = npc.world_id
    line = deflection(npc)
    private = actor.is_player
    events.append("system", None, "narrate", {"text": line}, room_id=room_id,
                  recipient_id=actor.id if private else None)
    if private:
        story.bystander_note(world_id, npc, actor.id, room_id)
    story.note_conversation(world_id, npc.id, actor.id)
    _note_opener(world_id, npc.id, line)
    _note_line(world_id, npc.id, line)
    story.remember_exchange(world_id, npc.id, actor.id, text, line)
