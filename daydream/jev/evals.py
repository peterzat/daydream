"""`bin/game jev eval [parser|triage|judge|topics|all]`: the local path and
Jev on the same labeled cases, scored the same way.

Every arm is read through the runtime's own reading (parser.interpret for
the parser and triage, the judge's pass/fail, the topic label the talk path
would answer with), so a score is what the game would have done. The
local arms need vLLM up; Jev needs a funded key. Results land in
~/data/daydream/jev-eval/<time>-<label>/ (results.json, report.md).

Per suite the report gives each arm's accuracy (dev and held-out apart),
their agreement, the discordant pairs with an exact McNemar p-value, Jev's
calibration (accuracy by confidence band), and the hybrid "Jev when its
confidence reaches t, else local" at several t, with Jev's coverage. With
--repeat N, Jev answers each case N times and the report counts cases
whose answer changed (determinism).

The topics suite has a third arm: the local model answering the same typed
question Jev answers (a JSON enum), so a gain over the word match can be
told apart from a gain that any model would bring."""

from __future__ import annotations

import asyncio
import json
import math
import statistics
import tempfile
import time
from pathlib import Path

from daydream import config
from daydream.jev import client as jev_client
from daydream.jev import surfaces

ROOT = Path(__file__).resolve().parent.parent.parent
DATA = ROOT / "tests" / "model_eval"
THRESHOLDS = (0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99)
JEV_CONCURRENCY = 8


# ---- statistics ------------------------------------------------------------

def mcnemar_p(b: int, c: int) -> float:
    """Exact two-sided McNemar: b = local right/Jev wrong, c = the reverse."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def summarize(cases: list[dict]) -> dict:
    """Cases carry local_ok, jev_ok (bool or None when silent), jev_conf, set."""
    out: dict = {}
    for part in ("all", "dev", "held", "held2", "adv"):
        cs = [c for c in cases if part == "all" or c.get("set", "dev") == part]
        if not cs:
            continue
        n = len(cs)
        lo = sum(bool(c["local_ok"]) for c in cs)
        jv = sum(bool(c["jev_ok"]) for c in cs)
        silent = sum(c["jev_ok"] is None for c in cs)
        b = sum(1 for c in cs if c["local_ok"] and not c["jev_ok"])
        cc = sum(1 for c in cs if c["jev_ok"] and not c["local_ok"])
        row = {"n": n, "local": lo, "jev": jv, "jev_silent": silent,
               "local_acc": round(lo / n, 3), "jev_acc": round(jv / n, 3),
               "agree": sum(1 for c in cs if c.get("agree")),
               "local_only_right": b, "jev_only_right": cc,
               "mcnemar_p": round(mcnemar_p(b, cc), 4),
               "either_right": sum(1 for c in cs if c["local_ok"] or c["jev_ok"])}
        hyb = {}
        for t in THRESHOLDS:
            use = [c for c in cs if c["jev_ok"] is not None and (c.get("jev_conf") or 0) >= t]
            ok = sum(bool(c["jev_ok"]) for c in use) + sum(
                bool(c["local_ok"]) for c in cs if c not in use)
            hyb[str(t)] = {"acc": round(ok / n, 3), "jev_coverage": round(len(use) / n, 3),
                           "jev_acc_when_used": round(sum(bool(c["jev_ok"]) for c in use)
                                                      / len(use), 3) if use else None}
        row["hybrid"] = hyb
        if "local_llm_ok" in cs[0]:
            row["local_llm_acc"] = round(sum(bool(c["local_llm_ok"]) for c in cs) / n, 3)
        out[part] = row
    bands: dict = {}
    for c in cases:
        if c["jev_ok"] is None:
            continue
        band = min(9, int((c.get("jev_conf") or 0) * 10)) / 10
        bands.setdefault(band, [0, 0])
        bands[band][0] += 1
        bands[band][1] += bool(c["jev_ok"])
    out["calibration"] = {f"{b:.1f}": {"n": n, "acc": round(k / n, 3)}
                          for b, (n, k) in sorted(bands.items())}
    changed = [c for c in cases if len(set(map(json.dumps, c.get("jev_all") or []))) > 1]
    out["jev_changed_across_repeats"] = len(changed)
    ms_l = [c["local_ms"] for c in cases if c.get("local_ms") is not None]
    ms_j = [c["jev_ms"] for c in cases if c.get("jev_ms") is not None]
    out["latency_ms"] = {"local_p50": statistics.median(ms_l) if ms_l else None,
                         "jev_p50": statistics.median(ms_j) if ms_j else None}
    return out


# ---- helpers -----------------------------------------------------------------

_jev_gate: asyncio.Semaphore | None = None


async def _jev(state, questions, purpose: str):
    global _jev_gate
    if _jev_gate is None:
        _jev_gate = asyncio.Semaphore(JEV_CONCURRENCY)
    async with _jev_gate:
        return await jev_client.ask(state, questions, purpose=f"eval:{purpose}", timeout=20)


async def _jev_repeat(state, questions, purpose: str, repeat: int):
    rs = await asyncio.gather(*[_jev(state, questions, purpose) for _ in range(repeat)])
    return [r for r in rs if r is not None]


async def _local_json(system: str, user: str, purpose: str, schema: dict | None = None,
                      temperature: float | None = None):
    from daydream.llm import client

    t0 = time.monotonic()
    kw = {"response_format": schema} if schema else {}
    if temperature is not None:
        kw["temperature"] = temperature
    try:
        r = await client.acompletion_json(system=system, user=user, purpose=purpose, **kw)
    except client.LLMUnavailable:
        r = None
    return r, (time.monotonic() - t0) * 1000


# ---- parser and triage -----------------------------------------------------

async def suite_parser(repeat: int) -> dict:
    from daydream import model_eval as me
    from daydream import parser, verbs

    base_vocab = [{"name": v.name, "description": v.description} for v in verbs.VERBS.values()]
    wide_env = json.loads(me.WIDE_WORLD.read_text())
    wide_vocab = base_vocab + [{"name": n, "description": d.get("description", "")}
                               for n, d in wide_env.get("verbs", {}).items()]

    async def one(i, case):
        text, want_verb, want_dobj, want_iobj, scope_name = case
        vocab = wide_vocab if scope_name == "wide" else base_vocab
        scope = me.SCOPES[scope_name]
        names, ids = {v["name"] for v in vocab}, {e["id"] for e in scope}

        def read(result) -> tuple[bool, list]:
            cmd = parser.interpret(result, text, names, ids, "", ground=me._scope_ground(scope),
                                   people=parser.people_in(scope))[0]
            verb, dobj, iobj = cmd.verb, cmd.dobj_id, cmd.iobj_id
            if verb == "meta":
                shows = me._META_SHOWS.get(cmd.args, set())
                verb = next((v for v in want_verb.split("|") if v in shows), f"meta:{cmd.args}")
            if want_verb == "SAFE":
                ok = verb == "none" or (dobj is None and iobj is None)
            else:
                ok = (verb in want_verb.split("|") and dobj == want_dobj
                      and (want_iobj is None or iobj == want_iobj))
            return ok, [verb, dobj, iobj]

        local, lms = await _local_json(parser.system_prompt(),
                                       parser._user_prompt(text, vocab, scope), "parser")
        lok, lgot = read(local) if isinstance(local, dict) else (False, None)
        state, qs = surfaces.parser_questions(text, vocab, scope)
        rs = await _jev_repeat(state, qs, "parser", repeat)
        jok, jgot, conf, detail, all_got = None, None, 0.0, {}, []
        for k, r in enumerate(rs):
            result, c, d = surfaces.parser_result(r, text)
            ok, got = read(result)
            all_got.append(got)
            if k == 0:
                jok, jgot, conf, detail = ok, got, c, d
        return {"input": text, "want": [want_verb, want_dobj, want_iobj], "scope": scope_name,
                "local_ok": lok, "local": lgot, "local_ms": lms, "jev_ok": jok, "jev": jgot,
                "jev_conf": conf, "jev_detail": detail, "jev_all": all_got,
                "jev_ms": rs[0].ms if rs else None, "agree": lgot == jgot, "set": "dev"}

    held = [tuple(c) for c in json.loads((DATA / "parser_heldout.json").read_text())["cases"]]
    rows = [(c, "dev") for c in me.PARSER_CASES] + [(c, "held") for c in held]
    cases = await asyncio.gather(*[one(i, c) for i, (c, _) in enumerate(rows)])
    for case, (_, part) in zip(cases, rows, strict=True):
        case["set"] = part
    return {"cases": list(cases), "summary": summarize(list(cases))}


async def suite_triage(repeat: int, tmp: Path) -> dict:
    from daydream import db, parser, verbs
    from daydream import model_eval as me

    data = json.loads((DATA / "triage.json").read_text())
    scope = me.SCOPES[data["scope"]]
    env = json.loads(me.CANONICAL.read_text())
    off = set((env.get("config") or {}).get("engine_verbs_off") or ())
    vocab = [{"name": v.name, "description": v.description}
             for v in verbs.VERBS.values() if v.name not in off]
    vocab += [{"name": n, "description": d.get("description", "")}
              for n, d in (env.get("verbs") or {}).items()]
    me._fresh_db(tmp, "triage", me.CANONICAL)
    world_id = db.get_conn().execute("SELECT id FROM worlds").fetchone()[0]
    names, ids, ground = {v["name"] for v in vocab}, {e["id"] for e in scope}, \
        me._scope_ground(scope)

    def read(result, text, want_kind, want_target):
        cmd = parser.interpret(result, text, names, ids, world_id, ground=ground,
                               people=parser.people_in(scope))[0]
        does = me._triage_does(cmd)
        name = (cmd.dobj_name or "").lower()
        ok = does in want_kind.split("|") and (want_target is None or want_target in name)
        return ok, [does, cmd.verb, cmd.dobj_id, cmd.dobj_name]

    async def one(row, part):
        text, want_kind, want_target = row
        local, lms = await _local_json(parser.system_prompt(),
                                       parser._user_prompt(text, vocab, scope), "parser")
        lok, lgot = read(local, text, want_kind, want_target) if isinstance(local, dict) \
            else (False, None)
        state, qs = surfaces.parser_questions(text, vocab, scope)
        rs = await _jev_repeat(state, qs, "triage", repeat)
        jok, jgot, conf, all_got = None, None, 0.0, []
        for k, r in enumerate(rs):
            result, c, _ = surfaces.parser_result(r, text)
            ok, got = read(result, text, want_kind, want_target)
            all_got.append(got)
            if k == 0:
                jok, jgot, conf = ok, got, c
        return {"input": text, "want": [want_kind, want_target], "local_ok": lok,
                "local": lgot, "local_ms": lms, "jev_ok": jok, "jev": jgot, "jev_conf": conf,
                "jev_all": all_got, "jev_ms": rs[0].ms if rs else None,
                "agree": (lgot or [None])[0] == (jgot or [None])[0], "set": part}

    rows = [(r, "dev") for r in data["cases"]] + [(r, "held") for r in data.get("held_out") or []]
    cases = [await one(r, p) for r, p in rows]  # sequential: triage shares the parser's slot
    return {"cases": cases, "summary": summarize(cases)}


# ---- the judge -------------------------------------------------------------------

def _context(npc, probe, says: str) -> str:
    from daydream import dialogue, objects, story

    actor = objects.get(probe)
    beats = story.open_beats_for(npc.world_id, npc.id, probe)
    _, user, _ = dialogue.build_prompt(actor, npc, says, npc.location_id, beats)
    return dialogue.judge_view(user)


async def suite_judge(repeat: int, tmp: Path, adversarial: bool = False) -> dict:
    from daydream import dialogue
    from daydream import model_eval as me

    name = "judge_adversarial.json" if adversarial else "judge_labeled.json"
    items = json.loads((DATA / name).read_text())["items"]
    me._fresh_db(tmp, "judge", me.WORLD)
    probes = {}

    async def one(it):
        npc = me._npc(it["npc"])
        probe = probes.setdefault(it["npc"], me._probe_near(npc))
        ctx = _context(npc, probe, it["says"])
        want_pass = it["label"] == "ok"
        t0 = time.monotonic()
        verdict = await dialogue.judge_local(ctx, [it["draft"]])
        lms = (time.monotonic() - t0) * 1000
        lok = None if verdict is None else verdict[0] == want_pass
        state, qs = surfaces.judge_questions(ctx, [it["draft"]])
        rs = await _jev_repeat(state, qs, "judge", repeat)
        jok, jlabel, conf, p_ok, all_got = None, None, 0.0, None, []
        for k, r in enumerate(rs):
            v, c, d = surfaces.judge_verdicts(r, 1)
            if v is None:
                continue
            all_got.append(d["labels"][0])
            if k == 0:
                jok, jlabel, conf, p_ok = v[0] == want_pass, d["labels"][0], c, d["p_ok"][0]
        return {"npc": it["npc"], "input": it["says"], "draft": it["draft"], "want": it["label"],
                "local_ok": bool(lok), "local": None if verdict is None else verdict[0],
                "local_ms": lms, "jev_ok": jok, "jev": jlabel, "jev_conf": conf,
                "jev_p_ok": p_ok, "jev_label_exact": jlabel == it["label"], "jev_all": all_got,
                "jev_ms": rs[0].ms if rs else None,
                "agree": (verdict is not None and jlabel is not None
                          and verdict[0] == (jlabel == "ok")), "set": it["set"]}

    cases = []
    for it in items:  # the local judge is one GPU call per case: in order
        cases.append(await one(it))
    summary = summarize(cases)
    # P(ok) thresholds, the judge's own knob: pass when P(ok) >= t.
    sweep = {}
    for t in (0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8):
        used = [c for c in cases if c["jev_p_ok"] is not None]
        ok = sum(1 for c in used if (c["jev_p_ok"] >= t) == (c["want"] == "ok"))
        fp = sum(1 for c in used if c["jev_p_ok"] >= t and c["want"] != "ok")
        fn = sum(1 for c in used if c["jev_p_ok"] < t and c["want"] == "ok")
        sweep[str(t)] = {"acc": round(ok / len(used), 3) if used else None,
                         "failing_shown": fp, "passing_held_back": fn}
    summary["jev_p_ok_sweep"] = sweep
    for arm in ("local", "jev"):
        summary[f"{arm}_failing_shown"] = sum(
            1 for c in cases if c["want"] != "ok" and (
                c["local"] is True if arm == "local" else c["jev"] == "ok"))
        summary[f"{arm}_passing_held_back"] = sum(
            1 for c in cases if c["want"] == "ok" and (
                c["local"] is False if arm == "local" else c["jev"] not in (None, "ok")))
    return {"cases": cases, "summary": summary}


# ---- topics -------------------------------------------------------------------

async def _local_topic(npc_name: str, text: str, topics: list[dict]):
    """The local model answering Jev's own question: pick one option."""
    state, qs = surfaces.topic_questions(npc_name, text, topics)
    crit = qs["topic"]["criteria"]
    options = "\n".join(f"- {k}: {v or ''}" for k, v in crit.items())
    req = qs["request"]
    system = ("You classify one line a player said to a character in a story game. "
              "Return JSON {\"topic\": <one option>, \"request\": <true|false>}.")
    user = (f"{qs['topic']['instructions']}\n\nplayer_says: {text}\n\nOptions:\n{options}\n\n"
            f"request: {req['instructions']} (true: {req['criteria']['true']}; false: "
            f"{req['criteria']['false']})")
    schema = {"type": "json_schema", "json_schema": {"name": "topic", "schema": {
        "type": "object", "properties": {"topic": {"type": "string", "enum": list(crit)},
                                         "request": {"type": "boolean"}},
        "required": ["topic", "request"], "additionalProperties": False}}}
    r, ms = await _local_json(system, user, "eval_topic", schema=schema, temperature=0.0)
    got = r.get("topic") if isinstance(r, dict) else None
    if isinstance(r, dict) and r.get("request") is True:
        got = None  # the same rule Jev's answer is read by (surfaces.topic_pick)
    return (None if got in (None, "none") else got), ms


async def suite_topics(repeat: int, tmp: Path) -> dict:
    from daydream import model_eval as me
    from daydream import story

    items = json.loads((DATA / "topics_labeled.json").read_text())["items"]
    items += [{**it, "set": "held2"}
              for it in json.loads((DATA / "topics_heldout.json").read_text())["items"]]
    me._fresh_db(tmp, "topics", me.WORLD)
    probes = {}

    async def one(it):
        npc = me._npc(it["npc"])
        probe = probes.setdefault(it["npc"], me._probe_near(npc))
        topics = surfaces.enrich_topics(npc, story.available_topics(npc, probe))
        t0 = time.monotonic()
        hit = story.match_in_talk(npc, probe, it["says"])
        wms = (time.monotonic() - t0) * 1000
        word = hit["label"] if hit else None
        llm, lms = await _local_topic(npc.name, it["says"], topics)
        state, qs = surfaces.topic_questions(npc.name, it["says"], topics)
        rs = await _jev_repeat(state, qs, "topics", repeat)
        jgot, conf, detail, all_got = None, 0.0, {}, []
        for k, r in enumerate(rs):
            got, c, d = surfaces.topic_pick(r)
            all_got.append(got)
            if k == 0:
                jgot, conf, detail = got, c, d
        want = it["topic"]
        return {"npc": it["npc"], "input": it["says"], "want": want, "local": word,
                "local_ok": word == want, "local_ms": wms, "local_llm": llm,
                "local_llm_ok": llm == want, "local_llm_ms": lms, "jev": jgot,
                "jev_ok": (jgot == want) if rs else None, "jev_conf": conf, "jev_detail": detail,
                "jev_all": all_got, "jev_ms": rs[0].ms if rs else None,
                "agree": word == jgot, "set": it["set"]}

    cases = []
    for it in items:
        cases.append(await one(it))
    summary = summarize(cases)
    # What matters at runtime: a wrong authored answer is worse than an
    # improvised one. Count, per arm, lines answered with the wrong topic
    # (including a topic where none was right) and lines left to improvise
    # that had a right topic.
    for arm, key in (("word", "local"), ("local_llm", "local_llm"), ("jev", "jev")):
        summary[f"{arm}_wrong_topic"] = sum(1 for c in cases
                                            if c[key] is not None and c[key] != c["want"])
        summary[f"{arm}_missed_topic"] = sum(1 for c in cases
                                             if c[key] is None and c["want"] is not None)
    return {"cases": cases, "summary": summary}


# ---- runner -----------------------------------------------------------------------

def _report(results: dict, label: str) -> str:
    lines = [f"# Jev eval {label}".rstrip(), ""]
    for name, res in results.items():
        s = res["summary"]
        lines.append(f"## {name}")
        for part in ("all", "dev", "held", "held2", "adv"):
            if part not in s:
                continue
            r = s[part]
            extra = f", local-model choice {r['local_llm_acc']:.3f}" if "local_llm_acc" in r else ""
            lines.append(f"- {part}: n={r['n']} local {r['local_acc']:.3f}, Jev {r['jev_acc']:.3f}"
                         f"{extra}; Jev silent {r['jev_silent']}; local-only right "
                         f"{r['local_only_right']}, Jev-only right {r['jev_only_right']} "
                         f"(McNemar p={r['mcnemar_p']}); either right {r['either_right']}")
        best = s["all"]["hybrid"]
        lines.append("- hybrid (Jev at conf>=t else local): " + "; ".join(
            f"t={t}: {v['acc']:.3f} (Jev on {v['jev_coverage']:.0%})" for t, v in best.items()))
        lines.append("- Jev calibration: " + "; ".join(
            f"{b}: {v['acc']:.2f} of {v['n']}" for b, v in s["calibration"].items()))
        for k, v in s.items():
            if k.endswith(("_wrong_topic", "_missed_topic", "_failing_shown",
                           "_passing_held_back")):
                lines.append(f"- {k}: {v}")
        if "jev_p_ok_sweep" in s:
            lines.append("- Jev P(ok) sweep: " + "; ".join(
                f"t={t}: acc {v['acc']}, failing shown {v['failing_shown']}, "
                f"passing held {v['passing_held_back']}" for t, v in s["jev_p_ok_sweep"].items()))
        lines.append(f"- Jev answers that changed across repeats: "
                     f"{s['jev_changed_across_repeats']}")
        lines.append(f"- latency p50: {s['latency_ms']}")
        lines.append("")
    return "\n".join(lines)


async def run(suites: list[str], repeat: int) -> dict:
    from daydream.jev import settings

    if settings.api_key() is None or settings.egress_url():
        raise SystemExit("jev eval: dev tooling; needs DAYDREAM_JEV_API_KEY in .env (direct)")
    state, detail = await jev_client.funded()
    if state != "funded":
        raise SystemExit(f"jev eval: Jev is {state} ({detail})")
    tmp = Path(tempfile.mkdtemp(prefix="jev-eval-"))
    out = {}
    wanted = ["parser", "triage", "judge", "topics"] if "all" in suites else suites
    for name in wanted:
        t0 = time.monotonic()
        if name == "parser":
            out[name] = await suite_parser(repeat)
        elif name == "triage":
            out[name] = await suite_triage(repeat, tmp)
        elif name == "judge":
            out[name] = await suite_judge(repeat, tmp)
        elif name == "judge_adv":
            out[name] = await suite_judge(repeat, tmp, adversarial=True)
        elif name == "topics":
            out[name] = await suite_topics(repeat, tmp)
        else:
            raise SystemExit(f"jev eval: unknown suite {name!r}")
        out[name]["seconds"] = round(time.monotonic() - t0, 1)
    return out


def main(suites: list[str], label: str = "", repeat: int = 1) -> int:
    import os

    from daydream import worldclock

    os.environ.setdefault("DAYDREAM_VILLAGE_ENABLED", "0")
    os.environ.setdefault("DAYDREAM_DIRECTOR_LLM", "0")
    os.environ.setdefault("DAYDREAM_MEMORY_ENABLED", "0")
    results = asyncio.run(run(suites, max(1, repeat)))
    stamp = worldclock.iso()[:19].replace(":", "")
    out = config.data_dir() / "jev-eval" / (f"{stamp}-{label}" if label else stamp)
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(results, indent=1, default=str) + "\n")
    text = _report(results, label)
    (out / "report.md").write_text(text + "\n")
    print(text)
    print(f"\nwrote {out}")
    return 0
