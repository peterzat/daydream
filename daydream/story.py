"""The story layer: arcs, beats, endings, per-player state, NPC topics, and
the chronicle (SPEC 2026-09-26 criteria 2, 6, 8, 15; docs/PIVOT-BUILD.md).

Authored shape (worldstate `def:arcs`, validated by the format-2 loader):

    {"<arc>": {"title", "kind": "guest"|"keeper"|"village", "summary",
               "guest"?: <toon id>, "opens"?: "start"|"arrival"|"rule",
               "arrival"?: {"room", "text", "if"?, "earliest_day"?, "weight"?,
                            "first"?, "after_arcs"?},
               "beats": {"<beat>": {"npc"?, "topic"?, "topic_aliases"?,
                                    "hint"?, "if"?, "after"?, "text"?,
                                    "variants"?, "do"?, "per_player"?}},
               "endings": {"<ending>": {"text"?, "do"?, "ledger"?,
                                        "after_days"?, "room"?}}}}

Runtime state lives in worldstate, one row per arc (`arc:<id>`), plus the
per-player keys below. Transitions happen only through the rule-effect
kinds (`open_arc`, `advance_beat`, `close_arc`), which re-check every
precondition at commit: a stale beat, a closed arc, or an unknown id changes
nothing (the effect returns no event).

Per-player state (worldstate KV, no migration; world flags, counters, and
score are untouched):

    rel:<npc>:<toon>      relationship (int, default 0)
    pq:<toon>:<name>      per-player flag / counter / value
    talk:<npc>:<toon>     the last few exchanges between them

Nothing here is world-specific: every name, line, and rule is authored data.
"""

from __future__ import annotations

import logging
import re
from datetime import timedelta

from daydream import events, objects, variants, worldclock, worldstate

logger = logging.getLogger(__name__)

ARC_PREFIX = "arc:"
REL_PREFIX = "rel:"
PQ_PREFIX = "pq:"
TALK_PREFIX = "talk:"
CHRONICLE_KEY = "chronicle"
TALK_MEMORY = 6


# ---- authored definitions -------------------------------------------------


def arcs_def(world_id: str) -> dict:
    d = worldstate.get(world_id, "def:arcs")
    return d if isinstance(d, dict) else {}


def arc_def(world_id: str, arc_id: str) -> dict | None:
    d = arcs_def(world_id).get(arc_id)
    return d if isinstance(d, dict) else None


def beat_def(world_id: str, arc_id: str, beat_id: str) -> dict | None:
    arc = arc_def(world_id, arc_id)
    beats = arc.get("beats") if arc else None
    b = beats.get(beat_id) if isinstance(beats, dict) else None
    return b if isinstance(b, dict) else None


# ---- arc state ------------------------------------------------------------


def arc_state(world_id: str, arc_id: str) -> dict:
    st = worldstate.get(world_id, ARC_PREFIX + arc_id)
    if not isinstance(st, dict):
        return {"status": "dormant", "beats": {}, "helpers": []}
    st.setdefault("status", "dormant")
    st.setdefault("beats", {})
    st.setdefault("helpers", [])
    return st


def _save(world_id: str, arc_id: str, st: dict) -> None:
    worldstate.set(world_id, ARC_PREFIX + arc_id, st)


def arc_status(world_id: str, arc_id: str) -> str:
    return arc_state(world_id, arc_id)["status"]


def all_states(world_id: str) -> dict[str, dict]:
    return {a: arc_state(world_id, a) for a in arcs_def(world_id)}


def beat_done(world_id: str, arc_id: str, beat_id: str, by: str | None = None) -> bool:
    """World-level: someone completed the beat. With `by`, that toon did
    (per-player beats record per toon; world beats record their doer)."""
    if by is not None:
        if pget(world_id, by, f"beat:{arc_id}/{beat_id}") is not None:
            return True
        rec = arc_state(world_id, arc_id)["beats"].get(beat_id)
        return isinstance(rec, dict) and rec.get("by") == by
    return beat_id in arc_state(world_id, arc_id)["beats"]


def ending_of(world_id: str, arc_id: str) -> str | None:
    st = arc_state(world_id, arc_id)
    return st.get("ending") if st["status"] == "closed" else None


# ---- per-player state -----------------------------------------------------


def rel(world_id: str, npc_id: str, toon_id: str) -> int:
    v = worldstate.get(world_id, f"{REL_PREFIX}{npc_id}:{toon_id}", 0)
    return v if isinstance(v, int) else 0


def adjust_rel(world_id: str, npc_id: str, toon_id: str, delta: int) -> int:
    v = rel(world_id, npc_id, toon_id) + int(delta)
    worldstate.set(world_id, f"{REL_PREFIX}{npc_id}:{toon_id}", v)
    return v


def pget(world_id: str, toon_id: str, name: str, default=None):
    return worldstate.get(world_id, f"{PQ_PREFIX}{toon_id}:{name}", default)


def pset(world_id: str, toon_id: str, name: str, value) -> None:
    worldstate.set(world_id, f"{PQ_PREFIX}{toon_id}:{name}", value)


def pflag(world_id: str, toon_id: str, name: str) -> bool:
    return bool(pget(world_id, toon_id, f"flag:{name}", False))


def pcounter(world_id: str, toon_id: str, name: str) -> int:
    v = pget(world_id, toon_id, f"counter:{name}", 0)
    return v if isinstance(v, int) else 0


def relationship_label(world_id: str, npc_id: str, toon_id: str) -> str:
    """The authored tier for a relationship value (config.relationship_tiers:
    [{min, label}], highest qualifying min wins)."""
    cfg = worldstate.get(world_id, "config")
    tiers = cfg.get("relationship_tiers") if isinstance(cfg, dict) else None
    value = rel(world_id, npc_id, toon_id)
    best = None
    for t in tiers if isinstance(tiers, list) else []:
        if isinstance(t, dict) and isinstance(t.get("min"), int) \
                and isinstance(t.get("label"), str) and t["min"] <= value:
            if best is None or t["min"] > best[0]:
                best = (t["min"], t["label"])
    return best[1] if best else ("a stranger" if value <= 0 else "an acquaintance")


def note_conversation(world_id: str, npc_id: str, toon_id: str) -> None:
    """The first conversation of a local day between an NPC and a player
    warms the relationship by one (a coffee-break return is noticed)."""
    from daydream import village

    today = village.local_date(world_id)
    key = f"relday:{npc_id}:{toon_id}"
    if worldstate.get(world_id, key) != today:
        worldstate.set(world_id, key, today)
        adjust_rel(world_id, npc_id, toon_id, 1)


def remember_exchange(world_id: str, npc_id: str, toon_id: str,
                      said: str, reply: str) -> None:
    key = f"{TALK_PREFIX}{npc_id}:{toon_id}"
    log = worldstate.get(world_id, key)
    log = log if isinstance(log, list) else []
    log.append({"at": worldclock.iso(), "said": said[:300], "reply": reply[:400]})
    worldstate.set(world_id, key, log[-TALK_MEMORY:])


def recent_exchanges(world_id: str, npc_id: str, toon_id: str) -> list[dict]:
    log = worldstate.get(world_id, f"{TALK_PREFIX}{npc_id}:{toon_id}")
    return [e for e in log if isinstance(e, dict)] if isinstance(log, list) else []


# ---- conditions ctx + effects plumbing -------------------------------------


def _ctx(world_id: str, actor_id: str | None, room_id: str | None,
         holder: objects.Object | None, purpose: str) -> dict:
    from daydream import rules

    actor = objects.get(actor_id) if actor_id else None
    if actor is None:
        return rules.world_ctx(world_id, room_id, purpose)
    return rules._build_ctx(actor, None, None, room_id or actor.location_id or "",
                            holder, purpose)


def _conds(conds, ctx: dict) -> bool:
    from daydream import rules

    return rules.conditions_hold(conds, ctx)


def _run_effects(effs, ctx: dict, world_id: str, actor_id: str | None,
                 room_id: str | None) -> None:
    from daydream import rules
    from daydream.skills import effects

    if not isinstance(effs, list) or not effs:
        return
    effects.dispatch_effects(
        rules.resolve_sigils(effs, ctx), actor_id=actor_id or "",
        room_id=room_id or "", world_id=world_id, allowed=effects.RULE_KINDS,
    )


def _tell(world_id: str, key: str, spec: dict, room_id: str | None,
          recipient: str | None = None, actor_id: str | None = None,
          npc: objects.Object | None = None) -> events.Event | None:
    """Narrate an authored `text` / `variants` block (no verbatim repeat
    within the recent tellings in that room). A line opening "You ..." goes
    to the acting player alone, and the block's `others` line (if any) to
    everyone else there (effects.second_person_recipient / tell_others)."""
    from daydream.skills import effects
    options = []
    if isinstance(spec.get("variants"), list):
        options = [v for v in spec["variants"] if isinstance(v, str) and v.strip()]
    if not options and isinstance(spec.get("text"), str) and spec["text"].strip():
        options = [spec["text"]]
    if not options:
        return None
    line = variants.pick(world_id, key, options, room_id)
    from daydream import trace

    line = trace.expand_placeholders(line, world_id)
    if recipient is None and spec.get("to") != "everyone":
        recipient = effects.second_person_recipient(line, actor_id)
    ev = events.append("system", None, "narrate", {"text": line},
                       room_id=room_id, recipient_id=recipient)
    if recipient is not None and recipient == actor_id:
        if spec.get("others"):
            effects.tell_others(spec.get("others"), actor_id, room_id)
        elif npc is not None:
            bystander_note(world_id, npc, actor_id, room_id)
    return ev


_BYSTANDER_LINES = [
    "{npc} and {actor} talk quietly for a while.",
    "{npc} leans in to say something to {actor}.",
    "{actor} and {npc} fall into a low conversation.",
]
BYSTANDER_WINDOW = timedelta(minutes=10)


def bystander_note(world_id: str, npc: objects.Object | None, actor_id: str | None,
                   room_id: str | None) -> events.Event | None:
    """What everyone else in the room sees of a conversation that is not
    theirs (playtest 2026-09-26: answers meant for one dreamer reached all
    four, unaddressed): one short line, at most once per pair every ten
    minutes, never to the pair themselves."""
    actor = objects.get(actor_id) if actor_id else None
    if npc is None or actor is None or not actor.is_player or not room_id:
        return None
    key = f"bystander:{npc.id}:{actor.id}"
    last = worldstate.get(world_id, key)
    now = worldclock.now()
    if isinstance(last, str):
        try:
            if now - worldclock.parse(last) < BYSTANDER_WINDOW:
                return None
        except ValueError:
            pass
    worldstate.set(world_id, key, worldclock.iso(now))
    line = variants.pick(world_id, "bystander", _BYSTANDER_LINES, room_id)
    return events.append("system", None, "narrate",
                         {"text": line.format(npc=npc.name, actor=actor.name),
                          "except": actor.id},
                         room_id=room_id)


def _is_player(toon_id: str | None) -> bool:
    t = objects.get(toon_id) if toon_id else None
    return t is not None and t.kind == "toon" and t.is_human_controlled


def place_toon(toon_id: str, room_id: str | None, *, arrive_text: str | None = None,
               leave_text: str | None = None) -> events.Event | None:
    """Move a toon (a guest arriving, a keeper walking to their evening spot)
    with optional authored lines in the rooms it leaves and enters. `room_id`
    None sends it offstage. Emits `object_moved` so co-located players'
    panels refresh."""
    toon = objects.get(toon_id)
    if toon is None or toon.kind != "toon":
        return None
    if room_id is not None:
        dest = objects.get(room_id)
        if dest is None or dest.kind != "room":
            return None
    frm = toon.location_id
    if frm == room_id:
        return None
    if leave_text and frm:
        events.append("system", None, "narrate",
                      {"text": leave_text.replace("{name}", toon.name)}, room_id=frm)
    objects.move(toon_id, room_id)
    ev = events.append("system", None, "object_moved",
                       {"object_id": toon_id, "dest_id": room_id, "from": frm},
                       room_id=frm)
    if room_id is not None:
        # The arrival room refreshes too (a second event keyed to it).
        events.append("system", None, "object_moved",
                      {"object_id": toon_id, "dest_id": room_id, "from": frm},
                      room_id=room_id)
        if arrive_text:
            events.append("system", None, "narrate",
                          {"text": arrive_text.replace("{name}", toon.name)},
                          room_id=room_id)
    return ev


# ---- transitions ------------------------------------------------------------


def open_arc(world_id: str, arc_id: str, actor_id: str | None = None,
             room_id: str | None = None) -> events.Event | None:
    """Dormant -> open. Places the guest (if any) at the arrival room with
    the authored arrival text. Opening an open/closed arc changes nothing."""
    from daydream import village

    arc = arc_def(world_id, arc_id)
    st = arc_state(world_id, arc_id)
    if arc is None or st["status"] != "dormant":
        return None
    st.update(status="open", opened_at=worldclock.iso(),
              opened_day=village.day(world_id))
    _save(world_id, arc_id, st)
    arrival = arc.get("arrival") if isinstance(arc.get("arrival"), dict) else {}
    guest = arc.get("guest")
    where = arrival.get("room") or room_id
    if isinstance(guest, str) and where:
        place_toon(guest, where)
    if where and (arrival.get("text") or arrival.get("variants")):
        _tell(world_id, f"arrive:{arc_id}", arrival, where)
    return events.append("system", None, "arc_opened",
                         {"arc": arc_id, "title": arc.get("title")},
                         room_id=where)


def open_beats_for(world_id: str, npc_id: str, actor_id: str) -> list[tuple[str, str, dict]]:
    """Beats this NPC can advance for this player right now: authored with
    `npc` = this NPC, on an open arc, not yet done (per player for per-player
    beats), prerequisites done, and conditions holding for the player."""
    out: list[tuple[str, str, dict]] = []
    npc = objects.get(npc_id)
    for arc_id, arc in arcs_def(world_id).items():
        if not isinstance(arc, dict) or arc_status(world_id, arc_id) != "open":
            continue
        for beat_id, beat in (arc.get("beats") or {}).items():
            if not isinstance(beat, dict) or beat.get("npc") != npc_id:
                continue
            if _beat_ready(world_id, arc_id, beat_id, beat, actor_id, npc):
                out.append((arc_id, beat_id, beat))
    return out


def _beat_ready(world_id: str, arc_id: str, beat_id: str, beat: dict,
                actor_id: str | None, holder: objects.Object | None = None) -> bool:
    if arc_status(world_id, arc_id) != "open":
        return False
    if beat.get("per_player"):
        if actor_id is None or beat_done(world_id, arc_id, beat_id, by=actor_id):
            return False
    elif beat_done(world_id, arc_id, beat_id):
        return False
    for pre in beat.get("after") or []:
        if not isinstance(pre, str):
            return False
        if "/" in pre:
            pa, pb = pre.split("/", 1)
        else:
            pa, pb = arc_id, pre
        prebeat = beat_def(world_id, pa, pb) or {}
        if prebeat.get("per_player"):
            if actor_id is None or not beat_done(world_id, pa, pb, by=actor_id):
                return False
        elif not beat_done(world_id, pa, pb):
            return False
    ctx = _ctx(world_id, actor_id, None, holder, f"beat:{arc_id}/{beat_id}")
    return _conds(beat.get("if"), ctx)


def advance_beat(world_id: str, arc_id: str, beat_id: str,
                 actor_id: str | None, room_id: str | None,
                 *, tell: bool = True) -> events.Event | None:
    """Complete one beat: re-check readiness at commit (a stale or
    already-done beat changes nothing), record it, credit the player as a
    helper, run its authored effects, and tell its authored line."""
    beat = beat_def(world_id, arc_id, beat_id)
    if beat is None:
        return None
    npc = objects.get(beat["npc"]) if isinstance(beat.get("npc"), str) else None
    if not _beat_ready(world_id, arc_id, beat_id, beat, actor_id, npc):
        return None
    st = arc_state(world_id, arc_id)
    stamp = {"at": worldclock.iso(), "by": actor_id}
    if beat.get("per_player"):
        pset(world_id, actor_id, f"beat:{arc_id}/{beat_id}", stamp["at"])
        st["beats"].setdefault(beat_id, stamp)
    else:
        st["beats"][beat_id] = stamp
    # Who helped: the players who moved the arc for everyone. A per-player
    # beat (a story told to each) earns no helper's credit unless it says
    # so, and any beat may say `credit: false` (reading the repair ledger is
    # not mending the clock; beta rehearsal 2026-09-28: "co-credit for a
    # spectator", twice in one ledger).
    credit = beat.get("credit", not beat.get("per_player"))
    if _is_player(actor_id) and actor_id not in st["helpers"] and credit:
        st["helpers"].append(actor_id)
    _save(world_id, arc_id, st)
    if actor_id and npc is not None and _is_player(actor_id):
        adjust_rel(world_id, npc.id, actor_id, int(beat.get("rel", 1)))
    here = room_id or (objects.get(actor_id).location_id if actor_id and objects.get(actor_id) else None)
    ev = events.append("system", None, "beat_advanced",
                       {"arc": arc_id, "beat": beat_id}, room_id=here)
    if tell:
        # A per-player beat is a story told to this player: theirs alone,
        # with the bystander note for the room (beta rehearsal 2026-09-28: a
        # resident's answer to one dreamer's question reached the other
        # verbatim, who had just heard it themself).
        mine = (beat.get("per_player") and _is_player(actor_id)
                and beat.get("to") != "everyone")
        _tell(world_id, f"beat:{arc_id}/{beat_id}", beat, here,
              recipient=actor_id if mine else None, actor_id=actor_id, npc=npc)
    ctx = _ctx(world_id, actor_id, here, npc, f"beat:{arc_id}/{beat_id}")
    _run_effects(beat.get("do"), ctx, world_id, actor_id, here)
    return ev


def close_arc(world_id: str, arc_id: str, ending_id: str,
              actor_id: str | None = None, room_id: str | None = None) -> events.Event | None:
    """Open -> closed with an authored ending: record it (and who helped),
    run the ending's effects, tell its line, and write the chronicle entry.
    Closing a non-open arc or naming an unknown ending changes nothing."""
    from daydream import village

    arc = arc_def(world_id, arc_id)
    st = arc_state(world_id, arc_id)
    endings = arc.get("endings") if arc else None
    ending = endings.get(ending_id) if isinstance(endings, dict) else None
    if not isinstance(ending, dict) or st["status"] != "open":
        return None
    if _is_player(actor_id) and actor_id not in st["helpers"]:
        st["helpers"].append(actor_id)
    st.update(status="closed", ending=ending_id, closed_at=worldclock.iso(),
              closed_day=village.day(world_id))
    _save(world_id, arc_id, st)
    here = ending.get("room") or room_id
    if not here:
        guest = arc.get("guest")
        g = objects.get(guest) if isinstance(guest, str) else None
        here = g.location_id if g is not None else None
    names = [objects.get(h).name for h in st["helpers"] if objects.get(h) is not None]
    _chronicle_append(world_id, arc_id, arc, ending_id, ending, names)
    ev = events.append("system", None, "arc_closed",
                       {"arc": arc_id, "ending": ending_id,
                        "title": arc.get("title"), "helpers": names},
                       room_id=here)
    _tell(world_id, f"ending:{arc_id}/{ending_id}", ending, here, actor_id=actor_id)
    ctx = _ctx(world_id, actor_id, here, None, f"ending:{arc_id}/{ending_id}")
    _run_effects(ending.get("do"), ctx, world_id, actor_id, here)
    return ev


def timed_endings_due(world_id: str, today: int) -> list[tuple[str, str]]:
    """Open arcs whose timed ending (`after_days`) has come due by village
    day `today`: [(arc, ending)]."""
    due: list[tuple[str, str]] = []
    for arc_id, arc in arcs_def(world_id).items():
        if not isinstance(arc, dict):
            continue
        st = arc_state(world_id, arc_id)
        if st["status"] != "open" or not isinstance(st.get("opened_day"), int):
            continue
        for ending_id, ending in (arc.get("endings") or {}).items():
            n = ending.get("after_days") if isinstance(ending, dict) else None
            if isinstance(n, int) and today - st["opened_day"] >= n:
                due.append((arc_id, ending_id))
                break
    return due


# ---- topics (the deterministic producer for talk beats) --------------------

_ARTICLES = ("the ", "a ", "an ", "about ", "your ", "my ")


def normalize_topic(text: str) -> str:
    t = re.sub(r"[^a-z0-9' ]+", " ", (text or "").lower())
    t = " ".join(t.split())
    changed = True
    while changed:
        changed = False
        for art in _ARTICLES:
            if t.startswith(art):
                t = t[len(art):]
                changed = True
    return t.strip()


def available_topics(npc: objects.Object, actor_id: str) -> list[dict]:
    """What a player can ask this NPC about right now: the NPC's open beats
    (each authored with a topic) first, then its plain authored topics whose
    conditions hold. Each entry: {label, aliases, kind, arc?, beat?, index?}."""
    world_id = npc.world_id
    out: list[dict] = []
    for arc_id, beat_id, beat in open_beats_for(world_id, npc.id, actor_id):
        if isinstance(beat.get("topic"), str) and beat["topic"].strip():
            out.append({"label": beat["topic"].strip(),
                        "aliases": [a for a in beat.get("topic_aliases") or []
                                    if isinstance(a, str)],
                        "open": beat.get("topic_open") is True,
                        "kind": "beat", "arc": arc_id, "beat": beat_id})
    topics = npc.properties.get("topics")
    ctx = _ctx(world_id, actor_id, None, npc, f"topics:{npc.id}")
    for idx, t in enumerate(topics if isinstance(topics, list) else []):
        if not isinstance(t, dict) or not isinstance(t.get("label"), str):
            continue
        if not _conds(t.get("if"), ctx):
            continue
        if any(o["label"].lower() == t["label"].strip().lower() for o in out):
            continue
        out.append({"label": t["label"].strip(),
                    "aliases": [a for a in t.get("aliases") or [] if isinstance(a, str)],
                    "open": t.get("open") is True,
                    "kind": "topic", "index": idx})
    return out


def offered_topics(npc: objects.Object, actor_id: str) -> list[dict]:
    """The ask-about chips: the available topics whose subject this player
    has come across (`daydream.heard`), or that are authored `open`. Typing
    reaches every available topic; only the chips wait for the fiction to
    name them (playtest 2026-09-29)."""
    from daydream import heard

    known = heard.known_keys(npc.world_id, actor_id)
    return [t for t in available_topics(npc, actor_id) if heard.knows(t, known)]


def match_topic(npc: objects.Object, actor_id: str, text: str) -> dict | None:
    """Resolve typed topic text to one available topic: exact (normalized)
    label/alias first, then containment either way (min 4 chars). Beats win
    ties. Deterministic, no LLM."""
    want = normalize_topic(text)
    if not want:
        return None
    topics = available_topics(npc, actor_id)
    for t in topics:
        if want in {normalize_topic(x) for x in [t["label"], *t["aliases"]]}:
            return t
    stem = " ".join(_stems(text))
    for t in topics:
        if stem in {" ".join(_stems(x)) for x in [t["label"], *t["aliases"]]}:
            return t
    if len(want) >= 4:
        for t in topics:
            for x in [t["label"], *t["aliases"]]:
                nx = normalize_topic(x)
                if len(nx) >= 4 and (nx in want or want in nx):
                    return t
    return None


def _stems(text: str) -> list[str]:
    """Normalized words with a plural "s" dropped ("lullaby clocks" meets
    "a lullaby clock")."""
    return [w[:-1] if len(w) > 4 and w.endswith("s") and not w.endswith("ss") else w
            for w in normalize_topic(text).split()]


def topic_text(npc: objects.Object, topic: dict) -> str | None:
    """The authored words behind a matched topic: its text, or its first
    variant (grounding for the model when a longer line only mentions the
    topic). None for a beat: its text is the payoff, told only when the
    beat advances, and a line naming an open beat always selects it
    (codereview 2026-09-29)."""
    if topic.get("kind") == "beat":
        return None
    topics = npc.properties.get("topics") or []
    idx = topic.get("index")
    spec = topics[idx] if isinstance(idx, int) and idx < len(topics) else None
    if not isinstance(spec, dict):
        return None
    if isinstance(spec.get("text"), str) and spec["text"].strip():
        return spec["text"].strip()
    vs = [v for v in spec.get("variants") or [] if isinstance(v, str) and v.strip()]
    return vs[0].strip() if vs else None


def match_in_talk(npc: objects.Object, actor_id: str, text: str) -> dict | None:
    """Select, don't write (docs/REFLEXES.md): a free-form line to an NPC
    that names one of its available topics or open beats, as whole words,
    gets that authored answer instead of an improvised one (playtest
    2026-09-26: "can I have the hush?" drew an invented, thread-closing
    answer).
    Beats win; then the longest name. Names under four letters never match
    on their own. Deterministic, no LLM."""
    words = _stems(text)
    if not words:
        return None
    joined = f" {' '.join(words)} "
    best, best_len = None, 0
    for t in available_topics(npc, actor_id):
        for name in [t["label"], *t["aliases"]]:
            sw = _stems(name)
            if not sw or len(" ".join(sw)) < 4:
                continue
            if f" {' '.join(sw)} " in joined:
                n = len(" ".join(sw)) + (1000 if t["kind"] == "beat" else 0)
                if n > best_len:
                    best, best_len = t, n
    return best


_NUMBER_WORDS = ("none", "one", "two", "three", "four", "five", "six", "seven", "eight",
                 "nine", "ten")


def threads_for(actor_id: str) -> list[str]:
    """What this player is in the middle of: the authored `threads` whose
    conditions hold for them, in authored order, "{count}" filled with how
    many of the thread's `count` conditions hold (in words up to ten). The
    satchel lists them and "what now" reads them (playtest 2026-09-28b:
    nothing told a returning friend what they had been doing)."""
    actor = objects.get(actor_id)
    if actor is None:
        return []
    defs = worldstate.get(actor.world_id, "def:threads")
    ctx = _ctx(actor.world_id, actor.id, actor.location_id, None, "threads")
    out: list[str] = []
    for t in defs if isinstance(defs, list) else []:
        if not isinstance(t, dict) or not isinstance(t.get("text"), str):
            continue
        if not _conds(t.get("if"), ctx):
            continue
        text = t["text"].strip()
        if "{count}" in text:
            n = sum(1 for c in t.get("count") or [] if _conds([c], ctx))
            text = text.replace("{count}", _NUMBER_WORDS[n] if n < len(_NUMBER_WORDS) else str(n))
        if text and text not in out:
            out.append(text)
    from daydream import post

    # Post waiting for this player (beta rehearsal 2026-09-28).
    out.extend(line for line in post.thread_lines(actor.id) if line not in out)
    return out


def asked_topics(world_id: str, npc_id: str, toon_id: str) -> list[str]:
    """The topic labels this player has asked this NPC about (normalized), so
    the page can show them as asked (playtest 2026-09-28b: a long list gave
    no sign of what you had already heard)."""
    got = pget(world_id, toon_id, f"asked:{npc_id}", [])
    return [x for x in got if isinstance(x, str)] if isinstance(got, list) else []


def mark_asked(world_id: str, npc_id: str, toon_id: str, label: str) -> None:
    got = asked_topics(world_id, npc_id, toon_id)
    key = normalize_topic(label)
    if key and key not in got:
        pset(world_id, toon_id, f"asked:{npc_id}", (got + [key])[-200:])
    # Asked once, known from then on, of anyone (a typed guess included).
    from daydream import heard

    heard.add(world_id, toon_id, [heard.key_of(label)])


def ask(actor: objects.Object, npc: objects.Object, topic: dict, room_id: str) -> None:
    """Answer one matched topic. A beat topic advances the beat (its
    authored line is the NPC's answer); a plain topic tells its authored
    answer (varied, never verbatim-repeated) and runs its effects."""
    world_id = npc.world_id
    note_conversation(world_id, npc.id, actor.id)
    if actor.is_player:
        mark_asked(world_id, npc.id, actor.id, topic["label"])
    if topic["kind"] == "beat":
        advance_beat(world_id, topic["arc"], topic["beat"], actor.id, room_id)
        return
    topics = npc.properties.get("topics") or []
    spec = topics[topic["index"]] if topic["index"] < len(topics) else {}
    # A topic answer is the asker's (playtest 2026-09-26: in a busy room the
    # answers to four dreamers' questions reached everyone, unaddressed).
    private = actor.is_player and spec.get("to") != "everyone"
    _tell(world_id, f"topic:{npc.id}:{normalize_topic(topic['label'])}", spec, room_id,
          recipient=actor.id if private else None, actor_id=actor.id, npc=npc)
    ctx = _ctx(world_id, actor.id, room_id, npc, f"topic:{npc.id}")
    _run_effects(spec.get("do"), ctx, world_id, actor.id, room_id)


# ---- the chronicle (the in-world ledger of closed arcs) ---------------------


def _chronicle_append(world_id: str, arc_id: str, arc: dict, ending_id: str,
                      ending: dict, helper_names: list[str]) -> None:
    from daydream import village

    template = ending.get("ledger")
    if not isinstance(template, str) or not template.strip():
        template = f"{arc.get('title') or arc_id}: {ending_id}."
    who = _join_names(helper_names)
    line = template.replace("{helpers}", who or "no one in particular")
    log = worldstate.get(world_id, CHRONICLE_KEY)
    log = log if isinstance(log, list) else []
    log.append({"arc": arc_id, "ending": ending_id, "day": village.day(world_id),
                "at": worldclock.iso(), "helpers": helper_names, "text": line.strip()})
    worldstate.set(world_id, CHRONICLE_KEY, log)


def _join_names(names: list[str]) -> str:
    names = [n for n in names if n]
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " and " + names[-1]


def chronicle(world_id: str) -> list[dict]:
    log = worldstate.get(world_id, CHRONICLE_KEY)
    return [e for e in log if isinstance(e, dict)] if isinstance(log, list) else []


def chronicle_text(world_id: str, holder: objects.Object) -> str:
    """The readable text of a chronicle book: its authored header, then one
    line per closed arc in the order they closed (day + the authored ledger
    line naming who helped), or its authored empty text."""
    header = holder.properties.get("chronicle_header")
    empty = holder.properties.get("chronicle_empty")
    entries = chronicle(world_id)
    parts = [header.strip()] if isinstance(header, str) and header.strip() else []
    if not entries:
        if isinstance(empty, str) and empty.strip():
            parts.append(empty.strip())
        return " ".join(parts) or "The pages are blank."
    for e in entries:
        day = e.get("day")
        prefix = f"Day {day}: " if isinstance(day, int) and day > 0 else ""
        parts.append(prefix + str(e.get("text", "")).strip())
    return "\n".join(parts)
