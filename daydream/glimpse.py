"""Things the prose shows that the hands can't reach (playtest 2026-09-29b).

A room's description or a thing's look can name something that is not an
object: a jar glinting on a shelf too high to reach. Asked for by name ("get
the jar"), it used to read "You don't see the jar here", which was false: the
player had just seen it. The answer now comes in the reflexes-not-voice order
(docs/REFLEXES.md):

1. Authored. Any room or thing may carry `properties.glimpsed`, a list of
   entries `{"names": [...], "text": "...", "verbs"?: {verb: text},
   "if"?: [conditions]}`: what its prose names, why a dreamer can't handle
   it, per verb when looking differs from reaching, and when (story
   conditions, `self` being the holder). Among the entries whose conditions
   hold, the longest matching name wins.
2. Seen but unwritten. When the name is in the scene's own prose (the room's
   description, or the look of a thing here), a look answers with that
   prose, deterministically, and any other verb gets one local-model line
   saying why, drawn only from that sentence: validated, cached per sentence
   in worldstate, tagged `src: "local"` so the dream digest lists it for an
   authored rewrite. A model outage or a line that fails validation reads a
   plain line instead.
3. Named nowhere here: None, and the caller says "You don't see the X here."

A glimpse on a thing may be a **part** of it (`"part": true`; playtest
2026-09-30): a detail its look names, like the one clock painted with
forget-me-nots on a shelf of resting clocks. A part answers a look with its
own words (`text`, or `verbs.examine`), and any verb it names in `verbs`;
every other verb is done to the thing itself, as if the player had named it,
so winding the painted clock keeps the shelf's custom. A detail folded into
its thing as an alias answered with the thing's own look, the sentence the
player had just read, and a refusal naming the thing instead of the detail:
a name that resolves is not yet a name that answers.
"""

from __future__ import annotations

import hashlib
import logging
import re

from daydream import config, growth, lighting, objects, rules, worldstate
from daydream.llm import client, safety
from daydream.skills import effects

logger = logging.getLogger(__name__)

# Verbs that look rather than reach: they answer with what can be seen.
LOOK_VERBS = frozenset({"examine", "look", "read"})

_ARTICLE = re.compile(r"^(?:the|a|an|that|this|those|these|some|one|your|my)\s+")
_SENTENCE = re.compile(r"[^.!?]+[.!?]?")
_STOPWORDS = frozenset({"it", "them", "that", "this", "one", "thing", "things", "up", "there",
                        "here", "all", "some", "and", "or", "but", "the", "of", "to", "in",
                        "on", "at", "for", "with", "from", "by", "as", "is", "are", "was",
                        "be", "not", "no", "so", "if", "then", "its", "his", "her", "their",
                        "you", "your", "me", "my", "we", "our", "out", "off", "down", "over"})


def _norm(text: str) -> str:
    s = re.sub(r"\s+", " ", (text or "").lower()).strip(" .,!?;:'\"")
    prev = None
    while prev != s:
        prev, s = s, _ARTICLE.sub("", s)
    return s


def bare_name(text: str) -> str:
    """A typed name without its article or edge punctuation: "the forget-me-nots"."""
    return _norm(text)


def _singular(word: str) -> str:
    if len(word) > 3 and word.endswith("es") and word[-3] in "sxz":
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _plural(noun: str) -> bool:
    words = noun.split()
    return bool(words) and _singular(words[-1]) != words[-1]


def _phrase_pattern(phrase: str) -> re.Pattern:
    """Whole words, the last one plural-tolerant: "jar" finds "jar" and "jars".
    A typed plural finds only a plural: "hands" is no "looping hand", nor
    "pockets" a pocket watch (codereview 2026-09-29g)."""
    words = phrase.split()
    head = [re.escape(w) for w in words[:-1]]
    last = re.escape(words[-1]) + ("" if _plural(phrase) else r"(?:s|es)?")
    return re.compile(r"\b" + r"\s+".join(head + [last]) + r"\b", re.IGNORECASE)


def _typed_forms(typed: str) -> list[str]:
    """The typed name, and it without a trailing phrase the way the parser
    drops one ("jar on the top shelf" -> "jar")."""
    from daydream.parser import _TRAILING_PHRASE

    head = _norm(_TRAILING_PHRASE.sub("", typed))
    return [typed] + ([head] if head and head != typed else [])


def _same(a: str, b: str) -> bool:
    """Equal, the last word plural-tolerant."""
    aw, bw = a.split(), b.split()
    return len(aw) == len(bw) and aw[:-1] == bw[:-1] and _singular(aw[-1]) == _singular(bw[-1])


def _name_matches(typed: str, name: str) -> bool:
    """A typed name is the authored one (articles aside, a plural tolerated),
    or ends with a name of two words or more ("dusty glinting jar" for
    "glinting jar"). One word must match whole: "little brass clock" is not
    the great clock's "clock"."""
    name = _norm(name)
    if not name or not typed:
        return False
    for form in _typed_forms(typed):
        if _same(form, name):
            return True
        words = form.split()
        n = len(name.split())
        if n >= 2 and len(words) > n and _same(" ".join(words[-n:]), name):
            return True
    return False


def _hosts(actor: objects.Object, room_id: str) -> list[objects.Object]:
    """What can hold a glimpse: the room and the things in scope (no toons).
    An unlit room shows nothing its prose names (codereview 2026-09-29g)."""
    lit = lighting.room_lit(room_id)
    return [o for o in objects.in_scope(actor.id)
            if o.id != actor.id and o.kind in ("room", "thing")
            and (lit or o.kind != "room")]


def _scenery(actor: objects.Object, room_id: str) -> list[dict]:
    """The world's shared scenery shown in this room (`config.scenery`: the
    sky, the walls, the lanterns, defined once for every room that shows
    them; spec 2026-09-29 criterion 9). None in an unlit room."""
    if not lighting.room_lit(room_id):
        return []
    cfg = worldstate.get(actor.world_id, "config")
    entries = cfg.get("scenery") if isinstance(cfg, dict) else None
    return [e for e in entries if isinstance(e, dict) and room_id in (e.get("rooms") or [])] \
        if isinstance(entries, list) else []


def exit_named(actor: objects.Object, name: str, exact: bool = False) -> str | None:
    """The way out of the actor's room that `name` names (`properties.
    exit_names` on the room: {direction: [names]}), if it is a way out now.
    `exact`: the name whole, never a longer phrase that ends with it."""
    room = objects.get(actor.location_id) if actor.location_id else None
    names = room.properties.get("exit_names") if room is not None else None
    if not isinstance(names, dict):
        return None
    typed = _norm(name)
    from daydream import rooms, verbs

    r = rooms.get_room(room.id)
    open_ways = verbs.visible_exits(r, actor) if r is not None else {}
    for direction, words in names.items():
        if direction in open_ways and any(
                _same(typed, _norm(w)) if exact else _name_matches(typed, w)
                for w in words or [] if typed and _norm(w)):
            return direction
    return None


def _way_line(actor: objects.Object, noun: str, direction: str) -> str:
    """"The low door is the way down to the Hour Cellar." """
    from daydream import rooms, verbs

    room = rooms.get_room(actor.location_id)
    dest = verbs.visible_exits(room, actor).get(direction) if room is not None else None
    to = rooms.get_room(dest) if isinstance(dest, str) else None
    be = "are" if _plural(noun) else "is"
    place = ""
    if to is not None:
        title = to.title
        place = " to " + ("the " + title[4:] if title.startswith("The ") else title)
    return f"The {noun} {be} the way {direction}{place}."


def _entry_line(entry: dict, verb: str) -> str | None:
    """An entry's line for `verb`: its own, a look's for any look, else its
    `text`. A part answers only a look and the verbs it names; its thing
    answers the rest (None)."""
    per_verb = entry.get("verbs") if isinstance(entry.get("verbs"), dict) else {}
    text = per_verb.get(verb)
    if not isinstance(text, str) and verb in LOOK_VERBS:
        text = next((per_verb[v] for v in ("examine", "look", "read")
                     if isinstance(per_verb.get(v), str)), None)
    if not isinstance(text, str) and (verb in LOOK_VERBS or not entry.get("part")):
        text = entry.get("text")
    return text.strip() if isinstance(text, str) and text.strip() else None


def _best(actor: objects.Object, room_id: str, name: str,
          verb: str) -> tuple[objects.Object, dict, str | None] | None:
    """(host, entry, its line for `verb`) for the glimpse or scenery that
    names `name` here, the longest matching name winning among the entries
    whose conditions hold for this actor and that answer this verb, a part
    answering by handing the verb to its thing (line None)."""
    typed = _norm(name)
    best: tuple[int, objects.Object, dict, str | None] | None = None
    room = objects.get(room_id)
    sources = [(host, host.properties.get("glimpsed")) for host in _hosts(actor, room_id)]
    sources.append((room, _scenery(actor, room_id)))
    for host, entries in sources:
        if not isinstance(entries, list) or host is None:
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            names = [n for n in entry.get("names") or [] if isinstance(n, str)]
            hit = max((len(_norm(n)) for n in names if _name_matches(typed, n)), default=0)
            if not hit or (best is not None and hit <= best[0]):
                continue
            ctx = rules._build_ctx(actor, None, None, room_id, host, f"glimpse:{host.id}")
            if not rules.conditions_hold(entry.get("if"), ctx):
                continue
            line = _entry_line(entry, verb)
            if line is not None or (entry.get("part") and host.kind == "thing"):
                best = (hit, host, entry, line)
    return best[1:] if best else None


def authored(actor: objects.Object, room_id: str, name: str, verb: str) -> str | None:
    """The authored reason for `verb` on `name`, from a glimpse whose
    conditions hold for this actor, or the world's scenery here; the longest
    matching name wins. None for a part's verb that its thing answers
    (`part_host`)."""
    got = _best(actor, room_id, name, verb)
    return got[2] if got else None


def part_host(actor: objects.Object, room_id: str, name: str,
              verb: str) -> objects.Object | None:
    """The thing here that does `verb` when the player names one of its
    parts: a part answers a look and the verbs it names, and its thing
    answers the rest, as if the player had named it."""
    got = _best(actor, room_id, name, verb)
    return got[0] if got and got[2] is None else None


def part_key(host: objects.Object, entry: dict) -> str | None:
    """A part's key on the page: its thing and its place in the list, the
    same for every name it answers to."""
    entries = host.properties.get("glimpsed")
    for i, e in enumerate(entries if isinstance(entries, list) else []):
        if e is entry:
            return f"{host.id}#{i}"
    return None


def parts_of(obj: objects.Object) -> list[tuple[str, str]]:
    """(name, part key) for each name of a thing's parts, for the page to
    link where prose shows them (every entry, whatever its conditions: a
    part is always there)."""
    entries = obj.properties.get("glimpsed") if obj.kind == "thing" else None
    return [(n, f"{obj.id}#{i}") for i, e in enumerate(entries)
            if isinstance(e, dict) and e.get("part")
            for n in e.get("names") or [] if isinstance(n, str) and n.strip()] \
        if isinstance(entries, list) else []


def _prose(host: objects.Object) -> str:
    """What a player reads of a room (its description) or a thing (its look)."""
    if host.kind == "room":
        text = host.properties.get("description_cached") or host.seed
        return text if isinstance(text, str) else ""
    from daydream import verbs  # the look the examine card shows

    return verbs.detail_with_state(host) or ""


def seen_in(actor: objects.Object, room_id: str, name: str) -> tuple[str, str] | None:
    """(noun, sentence): where the scene's own prose names the whole phrase
    typed (articles aside, a plural tolerated). Never its head noun alone: a
    "button letter" is not any letter. The noun as written outranks a plural,
    a plural outranks a possessive ("the lantern's reach" names the lantern
    less than "the lantern by the stair"), and at the same rank a thing's
    look outranks the room's description."""
    for noun in _typed_forms(_norm(name)):
        if len(noun) < 3 or noun in _STOPWORDS:
            continue
        pattern = _phrase_pattern(noun)
        found: list[tuple[int, str]] = []
        for host in sorted(_hosts(actor, room_id), key=lambda h: h.kind == "room"):
            for sentence in _SENTENCE.findall(_prose(host)):
                ranks = [_match_rank(m, noun) for m in pattern.finditer(sentence)]
                if ranks:
                    found.append((min(ranks), sentence.strip()))
        if found:
            found.sort(key=lambda f: f[0])  # stable: things before the room at a rank
            return noun, found[0][1]
    return None


def _match_rank(m: re.Match, noun: str) -> int:
    if m.string[m.end():m.end() + 2] in ("'s", "’s"):
        return 2
    return 0 if m.group(0).lower() == noun else 1


def _sentence_case(text: str) -> str:
    text = text.strip()
    return text[:1].upper() + text[1:] if text else text


def _terminated(text: str) -> str:
    text = text.strip()
    return text if not text or text[-1] in ".!?" else text + "."


def plain_line(noun: str) -> str:
    """When the model is quiet or its line fails: seen, and out of reach."""
    it = "they aren't" if _plural(noun) else "it isn't"
    return f"You can see the {noun} from where you stand, but {it} within reach just now."


_COMPASS = frozenset({"north", "south", "east", "west",
                      "northeast", "northwest", "southeast", "southwest"})


def _way(actor: objects.Object, room_id: str, noun: str, sentence: str) -> str | None:
    """The one compass exit here that the clause naming `noun` points to ("a
    gate in the south wall"), else None. Up, down, in and out are everyday
    words in prose ("looks down"), so only the compass counts."""
    from daydream import rooms, verbs

    room = rooms.get_room(room_id)
    exits = {d for d, dest in verbs.visible_exits(room, actor).items()
             if dest and d in _COMPASS} if room is not None else set()
    pattern = _phrase_pattern(noun)
    clause = next((c for c in re.split(r"[;,:]", sentence) if pattern.search(c)), "")
    named = [d for d in sorted(exits) if re.search(rf"\b{d}\b", clause, re.IGNORECASE)]
    return named[0] if len(named) == 1 else None


_SYSTEM = (
    "You are the gentle narrator of a cozy watercolor storybook game. The "
    "player tried to do something with a thing the scene describes, but it "
    "can't be handled. In ONE short sentence addressed to the player (\"you\"), "
    "show why, the way a storybook would: borrow a concrete detail from the "
    "scene sentence and let the reason follow from it, softly. Never write "
    "\"cannot be taken\", \"is not possible\" or any game-rule phrasing. Invent "
    "nothing: no names, people, places, objects, or facts the sentence doesn't "
    "give, and no hint about how to reach it. No dialogue, no urgency.\n"
    "Examples (another story, for the shape only):\n"
    "Scene: A tall mast creaks above the deck. Tried: climb the mast. -> "
    "{\"line\": \"The mast leans and creaks with every swell of the deck, far "
    "too restless for climbing just now.\"}\n"
    "Scene: Hay is stacked to the rafters of the barn. Tried: take the hay. -> "
    "{\"line\": \"The hay is packed tight all the way up to the rafters, and "
    "not a wisp comes loose in your hands.\"}\n"
    "Return strict JSON: {\"line\": \"...\"}."
)

# Words a line may open a sentence with, capitalized, though the scene never
# said them: plain English openers, never a name.
_OPENERS = frozenset("""
you your it its the a an this that these those there here up down from only
nothing still even just some no not one for with without in on at by past
beyond too so but and now then though while when where as if yet each every
all both none far high out over under behind between through against above
below near after before perhaps maybe instead whatever somewhere
""".split())

_REFUSAL = re.compile(r"^\s*(?:i\b|as an ai|sorry)|\bi can(?:not|'t)\b", re.IGNORECASE)
_URGENT = re.compile(r"\b(?:hurry|must|quickly|danger)\b", re.IGNORECASE)
_CAPS = re.compile(r"\b[A-Z][a-z]+\b")
_ALL_CAPS = re.compile(r"\b[A-Z]{2,}\b")


def valid_line(line, sentence: str, never_words=()) -> bool:
    """One or two short sentences of narration that name nothing the source
    doesn't: no new names, no dialogue, no urgency, no numbers it never gave,
    none of the world's canon-breakers (`never_words`, as growth reads them)."""
    if not isinstance(line, str):
        return False
    line = line.strip()
    if not 12 <= len(line) <= 220 or len(_SENTENCE.findall(line)) > 2:
        return False
    if any(q in line for q in "\"“”") or effects._QUOTED.search(line):
        return False  # no dialogue, single-quoted included
    if _REFUSAL.search(line) or _URGENT.search(line):
        return False
    if re.search(r"\d", line) and not re.search(r"\d", sentence):
        return False
    source_words = {w.lower() for w in re.findall(r"[A-Za-z]+", sentence)}
    for cap in _CAPS.findall(line):
        if cap.lower() not in source_words and cap.lower() not in _OPENERS:
            return False  # a name the scene never said, even opening a sentence
    if any(w.lower() not in source_words for w in _ALL_CAPS.findall(line)):
        return False  # an all-caps name the scene never said
    if growth._never_word_hit({"never_words": list(never_words or ())}, line):
        return False
    return safety.first_banned(line) is None


def _never_words(world_id: str) -> list:
    """The world's canon-breakers: its dreamseed's growth `never_words`."""
    node = worldstate.get(world_id, "config")
    for key in ("templates", "dreamseed", "properties", "growth", "never_words"):
        node = node.get(key) if isinstance(node, dict) else None
    return node if isinstance(node, list) else []


def _cache_key(room_id: str, noun: str, verb: str, sentence: str) -> str:
    digest = hashlib.sha1(f"{noun}|{verb}|{sentence}".encode()).hexdigest()[:16]
    return f"glimpse:{room_id}:{digest}"


def user_prompt(sentence: str, verb: str, noun: str) -> str:
    return f"Scene: {sentence}\nTried: {verb} the {noun}."


async def compose(sentence: str, verb: str, noun: str,
                  never_words=()) -> tuple[str | None, object]:
    """One local-model call: (the validated line or None, the raw answer).
    model-eval measures this same prompt and validator."""
    try:
        result = await client.acompletion_json(
            system=_SYSTEM, user=user_prompt(sentence, verb, noun),
            purpose="glimpse", temperature=0.4, max_tokens=120,
        )
    except client.LLMUnavailable:
        return None, None
    raw = result.get("line") if isinstance(result, dict) else None
    if not valid_line(raw, sentence, never_words):
        logger.info("glimpse: a line for %r failed validation", noun)
        return None, raw
    return _terminated(raw.strip()), raw


async def _local_line(world_id: str, room_id: str, noun: str, verb: str,
                      sentence: str) -> str | None:
    key = _cache_key(room_id, noun, verb, sentence)
    cached = worldstate.get(world_id, key)
    if isinstance(cached, str) and cached:
        return cached
    line, _ = await compose(sentence, verb, noun, _never_words(world_id))
    if line is not None:
        worldstate.set(world_id, key, line)
    return line


async def answer(actor: objects.Object, room_id: str, name: str, verb: str) -> dict | None:
    """A private narrate effect for `verb` on `name`, or None when the scene
    never named it (the caller says it isn't here)."""
    got = _best(actor, room_id, name, verb)
    if got is not None and got[2] is not None:
        host, entry, text = got
        eff = {"kind": "narrate", "text": text, "to": "@actor"}
        if entry.get("part") and verb in LOOK_VERBS:
            # A part's look is a card like its thing's, keyed so the page
            # never links the part to itself inside it.
            eff["card"] = {"verb": "read" if verb == "read" else "examine",
                           "name": f"the {_norm(name)}", "object_id": host.id,
                           "part": part_key(host, entry), "body": text}
        return eff
    seen = seen_in(actor, room_id, name)
    way_out = exit_named(actor, name)
    if way_out is not None and (seen is None or verb not in LOOK_VERBS):
        return {"kind": "narrate", "text": _way_line(actor, _norm(name), way_out), "to": "@actor"}
    if seen is None:
        return None
    noun, sentence = seen
    if verb in LOOK_VERBS:
        return {"kind": "narrate", "text": _terminated(_sentence_case(sentence)), "to": "@actor"}
    way = _way(actor, room_id, noun, sentence)
    if way is not None:  # "open the gate" at the south exit (codereview 2026-09-29g)
        be = "are" if _plural(noun) else "is"
        return {"kind": "narrate", "text": f"The {noun} {be} the way {way} from here.",
                "to": "@actor"}
    line = None
    if config.glimpse_llm_enabled():
        line = await _local_line(actor.world_id, room_id, noun, verb, sentence)
    if line is None:
        return {"kind": "narrate", "text": plain_line(noun), "to": "@actor"}
    return {"kind": "narrate", "text": line, "to": "@actor", "src": "local"}


def validate_glimpsed(entries, where: str, *, known_flags: set[str], known_ids: set[str],
                      known_story: dict | None = None,
                      known_verbs: set[str] | None = None,
                      host_names: list | None = None) -> list[str]:
    """Named errors for an authored `properties.glimpsed` list (the loader).
    `host_names`: the name and aliases of the thing that holds the list (a
    part belongs to a thing, and a glimpse named like its own thing never
    answers: the thing is grounded first). None for a room or the scenery."""
    if not isinstance(entries, list):
        return [f"{where} must be a list"]
    errors: list[str] = []
    for i, entry in enumerate(entries):
        ew = f"{where}[{i}]"
        if not isinstance(entry, dict):
            errors.append(f"{ew} must be an object")
            continue
        unknown = set(entry) - {"names", "text", "verbs", "if", "part"}
        if unknown:
            errors.append(f"{ew}: unknown key(s) {sorted(unknown)}")
        names = entry.get("names")
        if not (isinstance(names, list) and names
                and all(isinstance(n, str) and _norm(n) for n in names)):
            errors.append(f"{ew}.names must be a non-empty list of names")
        elif any(len(_norm(n).split()) >= 4 for n in names):
            errors.append(f"{ew}.names: a name of four words or more never reaches a "
                          f"glimpse (the parser passes its head); shorten it")
        if not (isinstance(entry.get("text"), str) and entry["text"].strip()):
            errors.append(f"{ew}.text must be a non-empty string")
        verbs = entry.get("verbs")
        if verbs is not None and not (
                isinstance(verbs, dict)
                and all(isinstance(k, str) and isinstance(v, str) and v.strip()
                        for k, v in verbs.items())):
            errors.append(f"{ew}.verbs must map verb names to lines")
        elif isinstance(verbs, dict) and known_verbs is not None:
            errors.extend(f"{ew}.verbs.{k}: unknown verb (it would never answer)"
                          for k in verbs if k not in known_verbs)
        if "part" in entry and not isinstance(entry["part"], bool):
            errors.append(f"{ew}.part must be true or false")
        elif entry.get("part") and host_names is None:
            errors.append(f"{ew}.part: only a thing has parts")
        if host_names is not None and isinstance(names, list):
            own = {_norm(h) for h in host_names if isinstance(h, str)}
            errors.extend(f"{ew}.names: {n!r} is also its thing's name or alias, so the "
                          f"thing answers it first; drop one"
                          for n in names if isinstance(n, str) and _norm(n) in own)
        if "if" in entry:
            errors.extend(rules.validate_condition_list(
                entry["if"], f"{ew}.if", known_flags=known_flags, known_ids=known_ids,
                known_story=known_story))
    return errors
