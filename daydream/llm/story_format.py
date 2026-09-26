"""Format-2 story sections: validation (SPEC 2026-09-26).

The story layer's authored data rides the format-2 envelope as top-level
sections, validated here with the loader's contract: named errors, closed
vocabularies, full cross-reference closure, ZERO writes on any failure.

    "time":            {tz, start_flag, phases, catch_up_days?, labels?}
    "player_flags":    [names]     per-player flags (pflag / set_pflag)
    "player_counters": [names]     per-player counters
    "arcs":            {id: arc}   see daydream/story.py
    "facts":           {id: {text, known_by, if?}}
    "storylets":       [storylet]  see daydream/director.py
    "collectibles":    [{id, name, text, page}]
    "pages":           {id: {title, reward?: {text?, do?}}}

and per toon: `voice` (the voice sheet), `schedule`, `schedule_text`,
`topics`; `room: "offstage"` for a guest who has not arrived yet.
`config.templates` (named spawn field sets), `config.collect`,
`config.director`, and `config.relationship_tiers` are checked for shape.

A dream patch (daydream/dream.py) validates its additions through the same
functions against the merged world, so a patch is held to exactly the bar
the world was.
"""

from __future__ import annotations

import re
from zoneinfo import ZoneInfo

from daydream import rules

PHASES = ("dawn", "day", "dusk", "night")
_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
ARC_KINDS = ("guest", "keeper", "village")


def _walk_add_fact_ids(node, out: set[str]) -> None:
    if isinstance(node, dict):
        if node.get("kind") == "add_fact" and isinstance(node.get("id"), str):
            out.add(node["id"])
        for v in node.values():
            _walk_add_fact_ids(v, out)
    elif isinstance(node, list):
        for v in node:
            _walk_add_fact_ids(v, out)


def known_story(env: dict) -> dict:
    """The story reference universe of an envelope (or a merged world):
    arcs, 'arc/beat' and 'arc/ending' refs, fact ids (authored + every
    add_fact id anywhere), per-player flag/counter names, pages,
    collectibles, and templates."""
    arcs = env.get("arcs") if isinstance(env.get("arcs"), dict) else {}
    beats, endings = set(), set()
    for aid, arc in arcs.items():
        if not isinstance(arc, dict):
            continue
        for b in (arc.get("beats") or {}) if isinstance(arc.get("beats"), dict) else {}:
            beats.add(f"{aid}/{b}")
        for e in (arc.get("endings") or {}) if isinstance(arc.get("endings"), dict) else {}:
            endings.add(f"{aid}/{e}")
    facts = set(env.get("facts") or {}) if isinstance(env.get("facts"), dict) else set()
    _walk_add_fact_ids(env, facts)
    cfg = env.get("config") if isinstance(env.get("config"), dict) else {}
    templates = cfg.get("templates") if isinstance(cfg.get("templates"), dict) else {}
    cols = env.get("collectibles") if isinstance(env.get("collectibles"), list) else []
    return {
        "arcs": set(arcs),
        "beats": beats,
        "endings": endings,
        "facts": facts,
        "pflags": set(env.get("player_flags") or []),
        "pcounters": set(env.get("player_counters") or []),
        "pages": set(env.get("pages") or {}) if isinstance(env.get("pages"), dict) else set(),
        "collectibles": {c["id"] for c in cols if isinstance(c, dict)
                         and isinstance(c.get("id"), str)},
        "templates": set(templates),
    }


def _text_or_variants(d: dict, where: str, errors: list[str], required: bool) -> None:
    has_text = isinstance(d.get("text"), str) and d["text"].strip()
    vs = d.get("variants")
    if vs is not None and not (isinstance(vs, list) and vs
                               and all(isinstance(v, str) and v.strip() for v in vs)):
        errors.append(f"{where}.variants must be a non-empty list of strings")
    if "text" in d and not isinstance(d["text"], str):
        errors.append(f"{where}.text must be a string")
    if required and not has_text and not (isinstance(vs, list) and vs):
        errors.append(f"{where}: needs 'text' or 'variants'")


def validate_story(env: dict, *, known: dict, ks: dict, room_ids: set[str],
                   toon_ids: set[str]) -> list[str]:
    """Named errors for every story section of `env`. `known` is the
    loader's rule-validation kwargs (flags, ids, fuses, daemons)."""
    errors: list[str] = []
    all_ids = known["known_ids"]

    def conds(c, where):
        errors.extend(rules.validate_condition_list(
            c, where, known_flags=known["known_flags"], known_ids=all_ids,
            known_story=ks))

    def effs(e, where, nonempty=False):
        errors.extend(rules.validate_effect_list(
            e, where, require_nonempty=nonempty, known_story=ks, **known))

    for sect, kind in (("player_flags", list), ("player_counters", list)):
        v = env.get(sect, [])
        if not isinstance(v, kind) or not all(isinstance(x, str) and x.strip() for x in v):
            errors.append(f"{sect} must be a list of non-empty strings")

    # time
    t = env.get("time")
    if t is not None:
        if not isinstance(t, dict):
            errors.append("time must be an object")
        else:
            try:
                ZoneInfo(t.get("tz") or "")
            except Exception:
                errors.append("time.tz must be an IANA zone name")
            sf = t.get("start_flag")
            if not isinstance(sf, str) or sf not in known["known_flags"]:
                errors.append("time.start_flag must name a declared flag")
            ph = t.get("phases")
            if not isinstance(ph, dict) or set(ph) != set(PHASES):
                errors.append(f"time.phases must set exactly {list(PHASES)}")
            else:
                for k, v in ph.items():
                    if not isinstance(v, str) or not _HHMM.match(v):
                        errors.append(f"time.phases.{k} must be HH:MM")
            if "catch_up_days" in t and not (isinstance(t["catch_up_days"], int)
                                             and 1 <= t["catch_up_days"] <= 30):
                errors.append("time.catch_up_days must be an int 1..30")
            if "labels" in t and not isinstance(t["labels"], dict):
                errors.append("time.labels must be an object")

    # facts
    facts = env.get("facts", {})
    if not isinstance(facts, dict):
        errors.append("facts must be an object")
        facts = {}
    for fid, f in facts.items():
        where = f"facts.{fid}"
        if not isinstance(f, dict) or not isinstance(f.get("text"), str) \
                or not f["text"].strip():
            errors.append(f"{where}: needs non-empty 'text'")
            continue
        kb = f.get("known_by")
        if kb != "all" and not (isinstance(kb, list) and all(k in toon_ids for k in kb)):
            errors.append(f"{where}.known_by must be 'all' or a list of toon ids")
        conds(f.get("if"), f"{where}.if")
        extra = set(f) - {"text", "known_by", "if"}
        if extra:
            errors.append(f"{where}: unknown field(s) {sorted(extra)}")

    # arcs
    arcs = env.get("arcs", {})
    if not isinstance(arcs, dict):
        errors.append("arcs must be an object")
        arcs = {}
    for aid, arc in arcs.items():
        where = f"arcs.{aid}"
        if not isinstance(arc, dict):
            errors.append(f"{where}: must be an object")
            continue
        if not isinstance(arc.get("title"), str) or not arc["title"].strip():
            errors.append(f"{where}.title must be a non-empty string")
        if arc.get("kind") not in ARC_KINDS:
            errors.append(f"{where}.kind must be one of {list(ARC_KINDS)}")
        if "guest" in arc and arc["guest"] not in toon_ids:
            errors.append(f"{where}.guest must name a declared toon")
        arr = arc.get("arrival")
        if arr is not None:
            aw = f"{where}.arrival"
            if not isinstance(arr, dict):
                errors.append(f"{aw}: must be an object")
            else:
                if arr.get("room") not in room_ids:
                    errors.append(f"{aw}.room must name a declared room")
                _text_or_variants(arr, aw, errors, required=False)
                conds(arr.get("if"), f"{aw}.if")
                for k, typ in (("earliest_day", int), ("first", bool)):
                    if k in arr and not isinstance(arr[k], typ):
                        errors.append(f"{aw}.{k} has the wrong type")
                if "weight" in arr and not isinstance(arr["weight"], (int, float)):
                    errors.append(f"{aw}.weight must be a number")
                for a in arr.get("after_arcs") or []:
                    if a not in arcs:
                        errors.append(f"{aw}.after_arcs: unknown arc {a!r}")
        beats = arc.get("beats")
        if not isinstance(beats, dict) or not beats:
            errors.append(f"{where}.beats must be a non-empty object")
            beats = {}
        for bid, b in beats.items():
            bw = f"{where}.beats.{bid}"
            if not isinstance(b, dict):
                errors.append(f"{bw}: must be an object")
                continue
            if "npc" in b:
                if b["npc"] not in toon_ids:
                    errors.append(f"{bw}.npc must name a declared toon")
                if not isinstance(b.get("topic"), str) or not b["topic"].strip():
                    errors.append(f"{bw}: a talk beat needs a 'topic' (its "
                                  "deterministic producer)")
            _text_or_variants(b, bw, errors, required=False)
            conds(b.get("if"), f"{bw}.if")
            effs(b.get("do", []), f"{bw}.do")
            for pre in b.get("after") or []:
                ref = pre if isinstance(pre, str) and "/" in pre else f"{aid}/{pre}"
                if ref not in ks["beats"]:
                    errors.append(f"{bw}.after: unknown beat {pre!r}")
            for k, typ in (("per_player", bool), ("hint", str), ("rel", int)):
                if k in b and not isinstance(b[k], typ):
                    errors.append(f"{bw}.{k} has the wrong type")
            if "topic_aliases" in b and not (isinstance(b["topic_aliases"], list) and all(
                    isinstance(x, str) for x in b["topic_aliases"])):
                errors.append(f"{bw}.topic_aliases must be a list of strings")
            extra = set(b) - {"npc", "topic", "topic_aliases", "hint", "if", "after",
                              "text", "variants", "do", "per_player", "rel"}
            if extra:
                errors.append(f"{bw}: unknown field(s) {sorted(extra)}")
        ends = arc.get("endings")
        if not isinstance(ends, dict) or len(ends) < 2:
            errors.append(f"{where}.endings must hold at least two endings "
                          "(criterion 2: every arc ends more than one way)")
            ends = ends if isinstance(ends, dict) else {}
        timed = 0
        for eid, e in ends.items():
            ew = f"{where}.endings.{eid}"
            if not isinstance(e, dict):
                errors.append(f"{ew}: must be an object")
                continue
            _text_or_variants(e, ew, errors, required=False)
            effs(e.get("do", []), f"{ew}.do")
            if "after_days" in e:
                timed += 1
                if not isinstance(e["after_days"], int) or e["after_days"] < 1:
                    errors.append(f"{ew}.after_days must be an int >= 1")
                if "@actor" in str(e.get("do", [])):
                    errors.append(f"{ew}: a timed ending has no actor ('@actor' unusable)")
            if "room" in e and e["room"] not in room_ids:
                errors.append(f"{ew}.room must name a declared room")
            if "ledger" in e and not isinstance(e["ledger"], str):
                errors.append(f"{ew}.ledger must be a string")
            for bad in ("kill_actor", "teleport_actor"):
                if bad in str(e.get("do", [])):
                    errors.append(f"{ew}: endings are never fail states ({bad} refused)")
            extra = set(e) - {"text", "variants", "do", "ledger", "after_days", "room",
                              "summary"}
            if extra:
                errors.append(f"{ew}: unknown field(s) {sorted(extra)}")
        if timed > 1:
            errors.append(f"{where}: at most one timed (after_days) ending")
        if "opens" in arc and arc["opens"] not in ("start", "arrival", "rule"):
            errors.append(f"{where}.opens must be 'start', 'arrival', or 'rule'")
        if "cumulative" in arc and not isinstance(arc["cumulative"], bool):
            errors.append(f"{where}.cumulative must be a boolean")
        extra = set(arc) - {"title", "kind", "summary", "guest", "arrival", "beats",
                            "endings", "opens", "cumulative"}
        if extra:
            errors.append(f"{where}: unknown field(s) {sorted(extra)}")

    # storylets
    sls = env.get("storylets", [])
    if not isinstance(sls, list):
        errors.append("storylets must be a list")
        sls = []
    seen: set[str] = set()
    for i, s in enumerate(sls):
        where = f"storylets[{i}]"
        if not isinstance(s, dict) or not isinstance(s.get("id"), str):
            errors.append(f"{where}: needs a string id")
            continue
        where = f"storylets.{s['id']}"
        if s["id"] in seen:
            errors.append(f"{where}: duplicate id")
        seen.add(s["id"])
        at = s.get("at", "any")
        ats = at if isinstance(at, list) else [at]
        for a in ats:
            if a not in (*PHASES, "any"):
                errors.append(f"{where}.at: unknown phase {a!r}")
        if "room" in s and s["room"] not in room_ids:
            errors.append(f"{where}.room must name a declared room")
        if (s.get("text") or s.get("variants")) and "room" not in s:
            errors.append(f"{where}: narration needs a 'room'")
        _text_or_variants(s, where, errors, required=False)
        conds(s.get("if"), f"{where}.if")
        effs(s.get("do", []), f"{where}.do")
        for k, typ in (("always", bool), ("once", bool), ("cooldown_days", int),
                       ("summary", str)):
            if k in s and not isinstance(s[k], typ):
                errors.append(f"{where}.{k} has the wrong type")
        extra = set(s) - {"id", "at", "always", "if", "weight", "once",
                          "cooldown_days", "room", "text", "variants", "do", "summary"}
        if extra:
            errors.append(f"{where}: unknown field(s) {sorted(extra)}")

    # collectibles + pages
    pages = env.get("pages", {})
    if not isinstance(pages, dict):
        errors.append("pages must be an object")
        pages = {}
    for pid, pg in pages.items():
        pw = f"pages.{pid}"
        if not isinstance(pg, dict) or not isinstance(pg.get("title"), str):
            errors.append(f"{pw}: needs a 'title'")
            continue
        rw = pg.get("reward")
        if rw is not None:
            if not isinstance(rw, dict):
                errors.append(f"{pw}.reward must be an object")
            else:
                effs(rw.get("do", []), f"{pw}.reward.do")
    cols = env.get("collectibles", [])
    if not isinstance(cols, list):
        errors.append("collectibles must be a list")
        cols = []
    cseen: set[str] = set()
    for i, c in enumerate(cols):
        cw = f"collectibles[{i}]"
        if not isinstance(c, dict) or not isinstance(c.get("id"), str):
            errors.append(f"{cw}: needs a string id")
            continue
        if c["id"] in cseen:
            errors.append(f"{cw}: duplicate id {c['id']!r}")
        cseen.add(c["id"])
        for k in ("name", "text"):
            if not isinstance(c.get(k), str) or not c[k].strip():
                errors.append(f"{cw}.{k} must be a non-empty string")
        if c.get("page") not in pages:
            errors.append(f"{cw}.page must name a declared page")

    # config shapes
    cfg = env.get("config") if isinstance(env.get("config"), dict) else {}
    tpls = cfg.get("templates", {})
    if not isinstance(tpls, dict):
        errors.append("config.templates must be an object")
    else:
        for name, tpl in tpls.items():
            if not isinstance(tpl, dict) or not isinstance(tpl.get("name"), str):
                errors.append(f"config.templates.{name}: needs a 'name'")
                continue
            g = (tpl.get("properties") or {}).get("growth")
            if g is not None:
                # A template dreamseed's growth block is held to the same
                # fail-loud bar the format-1 loader applied to authored seeds.
                from daydream.llm import bootstrap

                try:
                    bootstrap._validate_growth(g, f"config.templates.{name}.properties.growth")
                except Exception as e:  # noqa: BLE001 - reported as a named error
                    errors.append(str(e))
    col = cfg.get("collect")
    if col is not None:
        if not isinstance(col, dict):
            errors.append("config.collect must be an object")
        else:
            for r in col.get("rooms") or []:
                if r not in room_ids:
                    errors.append(f"config.collect.rooms: unknown room {r!r}")
    tiers = cfg.get("relationship_tiers")
    if tiers is not None and not (isinstance(tiers, list) and all(
            isinstance(x, dict) and isinstance(x.get("min"), int)
            and isinstance(x.get("label"), str) for x in tiers)):
        errors.append("config.relationship_tiers must be [{min, label}]")
    return errors


def validate_toon_story(t: dict, where: str, *, known: dict, ks: dict,
                        room_ids: set[str]) -> list[str]:
    """The per-toon story fields: voice, schedule, schedule_text, topics."""
    errors: list[str] = []
    props = t.get("properties") if isinstance(t.get("properties"), dict) else {}
    voice = props.get("voice")
    if voice is not None:
        vw = f"{where}.properties.voice"
        if not isinstance(voice, dict):
            errors.append(f"{vw} must be an object")
        else:
            for k in ("pronouns", "sheet"):
                if not isinstance(voice.get(k), str) or not voice[k].strip():
                    errors.append(f"{vw}.{k} must be a non-empty string")
            for k in ("samples", "habits", "never", "pet_names"):
                if k in voice and not (isinstance(voice[k], list) and all(
                        isinstance(x, str) for x in voice[k])):
                    errors.append(f"{vw}.{k} must be a list of strings")
            if "silent" in voice and not isinstance(voice["silent"], bool):
                errors.append(f"{vw}.silent must be a boolean")
            if "role" in voice and not isinstance(voice["role"], str):
                errors.append(f"{vw}.role must be a string")
            for i, w in enumerate(voice.get("wants") or []):
                if isinstance(w, str):
                    continue
                if not (isinstance(w, dict) and isinstance(w.get("text"), str)):
                    errors.append(f"{vw}.wants[{i}] must be a string or {{text, if}}")
                    continue
                errors.extend(rules.validate_condition_list(
                    w.get("if"), f"{vw}.wants[{i}].if",
                    known_flags=known["known_flags"], known_ids=known["known_ids"],
                    known_story=ks))
    sched = props.get("schedule")
    if sched is not None:
        if not isinstance(sched, dict):
            errors.append(f"{where}.properties.schedule must be an object")
        else:
            for ph, rid in sched.items():
                if ph not in PHASES:
                    errors.append(f"{where}.properties.schedule: unknown phase {ph!r}")
                if rid not in room_ids:
                    errors.append(f"{where}.properties.schedule.{ph}: unknown room {rid!r}")
    topics = props.get("topics")
    if topics is not None:
        if not isinstance(topics, list):
            errors.append(f"{where}.properties.topics must be a list")
        else:
            for i, tp in enumerate(topics):
                tw = f"{where}.properties.topics[{i}]"
                if not isinstance(tp, dict) or not isinstance(tp.get("label"), str):
                    errors.append(f"{tw}: needs a 'label'")
                    continue
                _text_or_variants(tp, tw, errors, required=True)
                errors.extend(rules.validate_condition_list(
                    tp.get("if"), f"{tw}.if", known_flags=known["known_flags"],
                    known_ids=known["known_ids"], known_story=ks))
                errors.extend(rules.validate_effect_list(
                    tp.get("do", []), f"{tw}.do", known_story=ks, **known))
    return errors


STORY_DEF_KEYS = {
    "arcs": "def:arcs", "facts": "def:facts", "storylets": "def:storylets",
    "collectibles": "def:collectibles", "pages": "def:pages", "time": "def:time",
    "player_flags": "def:player_flags", "player_counters": "def:player_counters",
}
