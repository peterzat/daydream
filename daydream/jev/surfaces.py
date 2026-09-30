"""The decisions Jev can make for daydream, as typed questions.

Each surface is a pair: `*_questions(...)` builds the state and questions
for one decision, and a reader turns Jev's answers back into exactly the
shape the local path returns, so the runtime (and the evals) read both
the same way. Jev writes no text: wherever the local model's reply
carries words (what a player says, the target as typed), the reader takes
them from the player's own line, deterministically.

- parser: the parser's one model call (verb, the thing acted on, a second
  thing, the line's kind, a direction), read back into the reply dict that
  `parser.interpret` reads.
- judge: the promise guard's verdict per draft (ok, or which rule it
  breaks), read back into `dialogue.judge`'s list of bools.
- topics: which of a resident's authored topics a free line is about, or
  none (a new decision: "select, don't write" by meaning, where the
  deterministic match reads only whole words).
"""

from __future__ import annotations

from daydream.jev.client import Result

# ---- parser ---------------------------------------------------------------

KINDS = {
    "act": "the player does something in the world: take, look at, open, go, use, give, sit",
    "say": "the player speaks to someone, including asking a character anything",
    "gesture": "a wave, hug, nod, bow, smile or thanks aimed at someone, without words",
    "sense": "listening, smelling, touching or tasting",
    "time": "asks the GAME (not a character) what time or day it is",
    "where": "asks the GAME where they are",
    "who": "asks the GAME who they are, what they look like or what they carry",
    "ways": "asks the GAME which ways lead out",
    "help": "asks the GAME how to play",
    "next": "asks the GAME what to do next, or what they were doing",
    "other": "none of these",
}
DIRECTIONS = ("north", "south", "east", "west", "northeast", "northwest", "southeast",
              "southwest", "up", "down", "in", "out")
_WORD_VERBS = {"talk", "say", "write", "ask", "tell"}
# Which object is which, per verb (the engine's own convention).
ROLES = ("give, hand, show, offer: FIRST is the thing handed over, SECOND the person who "
         "receives it (give the cup to Ada, hand Ada the cup: first cup, second Ada). "
         "put, place, drop into: FIRST is the thing moved, SECOND where it goes. "
         "use, unlock, open with, pry with: FIRST is the tool in the hand, SECOND what it "
         "is used on (unlock the door with the key: first key, second door). "
         "attack, hit, fight with: FIRST is who or what is attacked, SECOND the weapon. "
         "talk, ask, tell, greet: FIRST is the person spoken to. "
         "Every other verb: FIRST is what it acts on; there is no SECOND.")


def _thing(e: dict) -> str:
    aliases = [a for a in e.get("aliases") or [] if a]
    return (f"{e.get('name')} ({e.get('kind')})"
            + (f"; also called {', '.join(aliases)}" if aliases else ""))


def parser_questions(text: str, vocab: list[dict], scope: list[dict]) -> tuple[dict, dict]:
    things = {e["id"]: _thing(e) for e in scope}
    none_thing = ("the line names nothing listed here, or names something that is not in "
                  "this list even if something similar is")
    q = {
        "verb": {"type": "choice",
                 "instructions": "The player of a text adventure typed `player_typed`. Which "
                                 "one command does it ask for? Pick the verb whose meaning fits "
                                 "best; none when nothing fits or it is idle chatter.",
                 "criteria": {**{v["name"]: v.get("description") or v["name"] for v in vocab},
                              "none": "nothing fits, or idle chatter"}},
        "kind": {"type": "choice",
                 "instructions": "What kind of line is `player_typed`?",
                 "criteria": KINDS},
    }
    if things:
        q["dobj"] = {"type": "choice",
                     "instructions": {
                         "question": "Which thing or person here is the FIRST object of "
                                     "`player_typed`? Match by name or alias.",
                         "roles": ROLES},
                     "criteria": {**things, "none": none_thing}}
        q["iobj"] = {"type": "choice",
                     "instructions": {
                         "question": "Which thing or person here is the SECOND object of "
                                     "`player_typed`, when it has two? Never the same as the "
                                     "first. none for a command with one object or none.",
                         "roles": ROLES},
                     "criteria": {**things, "none": "the command has no second object, or it "
                                                    "is not listed"}}
    if any(v["name"] == "go" for v in vocab):
        q["direction"] = {"type": "choice",
                          "instructions": "If `player_typed` asks to move, which way?",
                          "criteria": {**{d: None for d in DIRECTIONS},
                                       "none": "not a move, or no way named"}}
    return {"player_typed": text}, q


def parser_result(res: Result, text: str) -> tuple[dict, float, dict]:
    """(the reply dict parser.interpret reads, Jev's confidence in it, detail)."""
    verb, v_conf, v_probs = res.choice("verb")
    dobj, d_conf, _ = res.choice("dobj")
    iobj, _, _ = res.choice("iobj")
    kind, k_conf, _ = res.choice("kind")
    way, _, _ = res.choice("direction")
    out: dict = {"verb": verb or "none", "dobj_id": dobj if dobj not in (None, "none") else None}
    if iobj not in (None, "none") and iobj != out["dobj_id"]:
        out["iobj_id"] = iobj
    if kind and kind != "act":
        out["kind"] = kind
    if out["verb"] == "go" and way not in (None, "none"):
        out["args"] = way
    elif out["verb"] in _WORD_VERBS:
        out["args"] = text
    elif out["verb"] == "gesture":
        from daydream import gestures

        out["args"] = gestures.find(text) or ""
    confidence = min(v_conf, d_conf if "dobj" in res.answers else 1.0)
    top = sorted(v_probs.items(), key=lambda kv: -kv[1])[:3]
    return out, confidence, {"verb_top": top, "kind": kind, "kind_conf": round(k_conf, 3)}


# ---- the promise judge -----------------------------------------------------

JUDGE_RULES = {
    "ok": "it only talks: answering, remembering what the context says, wondering aloud, "
          "asking back, advising, declining (even naming what it declines), saying someone "
          "the context does not list isn't here, a small courtesy happening right now, or "
          "suggesting the player do something themselves",
    "promise": "it promises or offers that the character will do something for the player "
               "beyond talking, now or later: hands over a thing the player could keep, or "
               "takes, holds, fixes or looks after something of the player's",
    "goes": "it says the character will go somewhere, come along, meet the player "
            "somewhere or lead the way, or gladly accepts an invitation to",
    "invents": "it states as fact an event, person, place or thing the context never "
               "mentions, denies one the context lists, or says a way leads somewhere the "
               "context's ways don't go",
}
_LOCAL_LABEL = {"ok": "ok", "promise": "a", "goes": "b", "invents": "c"}


def judge_questions(context: str, drafts: list[str]) -> tuple[dict, dict]:
    q = {}
    for i, d in enumerate(drafts):
        q[f"d{i}"] = {
            "type": "choice",
            "instructions": {
                "task": "A character in a story game drafted `draft` as its reply to the "
                        "player's last words in `context`. The game cannot make a character "
                        "act outside the conversation: a character never leaves with the "
                        "player, follows or leads them, fetches, fixes, mends, carries, lends "
                        "or gives them things, keeps things for them, waits for them, or meets "
                        "them later. Which describes the draft?",
                "draft": d},
            "criteria": JUDGE_RULES,
        }
    return {"context": context}, q


def judge_verdicts(res: Result, n: int) -> tuple[list[bool] | None, float, dict]:
    """(one pass/fail per draft, the least confident draft's confidence,
    detail with each draft's label and P(ok))."""
    labels, p_ok, confs = [], [], []
    for i in range(n):
        choice, conf, probs = res.choice(f"d{i}")
        if choice is None:
            return None, 0.0, {}
        labels.append(_LOCAL_LABEL.get(choice, choice))
        p_ok.append(round(float(probs.get("ok", 0.0)), 4))
        confs.append(conf)
    return [x == "ok" for x in labels], min(confs), {"labels": labels, "p_ok": p_ok}


# ---- topics -----------------------------------------------------------------

def enrich_topics(npc, topics: list[dict]) -> list[dict]:
    """Each available topic with its mentions and the start of its authored
    answer, so Jev reads what a topic is about, not only its name."""
    from daydream import story

    authored = npc.properties.get("topics") if isinstance(npc.properties.get("topics"), list) \
        else []
    out = []
    for t in topics:
        src: dict = {}
        if t.get("kind") == "topic" and isinstance(t.get("index"), int) \
                and t["index"] < len(authored) and isinstance(authored[t["index"]], dict):
            src = authored[t["index"]]
        elif t.get("kind") == "beat":
            src = story.beat_def(npc.world_id, t.get("arc"), t.get("beat")) or {}
        out.append({**t, "mentions": src.get("mentions") or src.get("topic_mentions") or [],
                    "text": src.get("text") or next(iter(src.get("variants") or []), "")})
    return out


def topic_questions(npc_name: str, text: str, topics: list[dict]) -> tuple[dict, dict]:
    """`topics`: the resident's available topics (story.available_topics),
    one per label."""
    crit: dict = {}
    for t in topics:
        label = t.get("label")
        if not isinstance(label, str) or label in crit:
            continue
        words = [w for w in [*(t.get("aliases") or []), *(t.get("mentions") or [])]
                 if isinstance(w, str)]
        answer = t.get("text") or next(iter(t.get("variants") or []), "")
        crit[label] = ((f"also: {', '.join(words[:8])}. " if words else "")
                       + (f"The answer begins: {str(answer)[:110]}" if answer else "")) or None
    crit["none"] = ("the line is about none of these: small talk, a greeting, a request, "
                    "something else, or it names a topic only in passing while asking about "
                    "something else")
    return ({"resident": npc_name, "player_says": text},
            {"topic": {"type": "choice",
                       "instructions": f"A player said `player_says` to {npc_name}. Which one "
                                       f"of {npc_name}'s topics is the player asking or talking "
                                       "about?",
                       "criteria": crit},
             "request": {"type": "noul",
                         "instructions": f"Does `player_says` ask {npc_name} to DO something "
                                         "(give, lend, fix, fetch, keep, light, come along, "
                                         "let the player take or borrow something) rather than "
                                         "ask or talk ABOUT something?",
                         "criteria": {"true": "a request for an action or a favour",
                                      "false": "a question or remark about something"}}})


REQUEST_AT = 0.5  # P(request) at or above which no topic answers the line


def topic_pick(res: Result) -> tuple[str | None, float, dict]:
    """(the topic label, or None for none, its confidence, detail). A line
    that asks the resident to do something is answered by no topic, even
    when it names one ("can I borrow your broom?")."""
    choice, conf, probs = res.choice("topic")
    p_req = res.noul("request")
    top = sorted(probs.items(), key=lambda kv: -kv[1])[:3]
    detail = {"top": top, "p_request": p_req}
    if p_req is not None and p_req >= REQUEST_AT:
        return None, max(conf, p_req), detail
    return (None if choice in (None, "none") else choice), conf, detail
