"""Jev in the running game: two decisions, each the local path with Jev
beside it (daydream/jev/seam.py; the evaluation, docs/JEV-SPIKE.md). The
game's own modules call these in one line each; with Jev off (no key
reachable) each is exactly the local path, and costs nothing more.

- judge(context, drafts, local): the promise guard's verdicts. On, a rule
  over both: a draft passes when Jev is sure it only talks (P(ok) >=
  JUDGE_SURE), or when the local judge passes it and Jev leans that way
  (P(ok) >= JUDGE_LEAN). Measured: no failing draft shown, live or on 114
  labeled drafts, and a third of the local judge's needless deflections
  gone.
- topic(actor, npc, text, local_pick): which authored topic answers a free
  line to a resident, or None (improvise). On, Jev's pick serves at
  confidence >= TOPIC_MIN, else the word match's. Only plain topics: a line
  that names an open story beat is matched deterministically, as before,
  and never reaches here. Measured: 0.925 against the word match's 0.475
  on held-out lines, and every live error below the threshold.
"""

from __future__ import annotations

from daydream.jev import client, seam, settings, surfaces

JUDGE_SURE = 0.8
JUDGE_LEAN = 0.5
TOPIC_MIN = 0.8


def _bools(v):
    return list(v) if isinstance(v, list) else v


async def judge(context: str, drafts: list[str], local, toon: str | None = None
                ) -> list[bool] | None:
    async def remote():
        state, qs = surfaces.judge_questions(context, drafts)
        res = await client.ask(state, qs, purpose="judge")
        if res is None:
            return None
        verdicts, conf, detail = surfaces.judge_verdicts(res, len(drafts))
        return None if verdicts is None else seam.Answer(verdicts, conf, detail)

    def combine(local_value, answer):
        p_ok = answer.detail.get("p_ok") or []
        out = []
        for i in range(len(drafts)):
            p = p_ok[i] if i < len(p_ok) else 0.0
            lv = bool(local_value[i]) if isinstance(local_value, list) and i < len(local_value) \
                else False
            out.append(p >= JUDGE_SURE or (lv and p >= JUDGE_LEAN))
        return out

    return await seam.decide(
        "judge", local=local, remote=remote, agree=lambda a, b: a == b, show=_bools,
        combine=combine, toon=toon,
        about={"context_tail": context.rsplit("\n\n", 1)[-1][:300],
               "drafts": [d[:300] for d in drafts]})


async def topic(actor, npc, text: str, local_pick: dict | None) -> dict | None:
    if not settings.enabled():
        return local_pick
    from daydream import story

    plain = [t for t in story.available_topics(npc, actor.id) if t.get("kind") == "topic"]
    if not plain:
        return local_pick

    async def local():
        return local_pick

    async def remote():
        state, qs = surfaces.topic_questions(npc.name, text, surfaces.enrich_topics(npc, plain))
        res = await client.ask(state, qs, purpose="topics")
        if res is None:
            return None
        label, conf, detail = surfaces.topic_pick(res)
        pick = next((t for t in plain if t["label"] == label), None) if label else None
        return seam.Answer(pick, conf, detail)

    def label(t):
        return t["label"] if isinstance(t, dict) else None

    return await seam.decide(
        "topics", local=local, remote=remote, agree=lambda a, b: label(a) == label(b),
        show=label, min_conf=TOPIC_MIN, toon=actor.id,
        about={"npc": npc.name, "text": text[:300]})
