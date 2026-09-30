"""The one call to Jev: `ask(state, questions, purpose=...)`.

Never raises. Every failure (off, bad key, an empty account, a rate limit,
a timeout, a malformed answer, the gateway down) returns None and is
recorded, so a caller falls back to its local path. An empty account (HTTP
402) or a refused key (401/403) pauses further calls for a while, so a
surface does not spend a timeout on every line while Jev cannot answer.

Direct (dev) calls carry the key; calls through the egress gateway (prod)
carry none, and the gateway adds it. Each call is one line on the
`daydream.jev` logger (outcome, timing, tokens, cost; never text) and one
row in the ledger's calls.jsonl.

API (docs.typesafe.ai/api): POST /v1/systemone with
`{state, model, questions: {id: {type, instructions, criteria}}}`; the
answer is `{model, answers: {id: {...}}, usage: {input_tokens, ...}}`.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import httpx

from daydream.jev import ledger, settings

logger = logging.getLogger(__name__)

PAUSE_S = {"empty": 600.0, "bad_key": 600.0}
_paused: dict[str, float] = {}  # reason -> monotonic time the pause ends
# Tests put an httpx.MockTransport here; None is the network.
transport: httpx.AsyncBaseTransport | None = None


@dataclass
class Result:
    answers: dict
    model: str = ""
    ms: float = 0.0
    input_tokens: int = 0
    request_id: str = ""
    raw: dict = field(default_factory=dict)

    def choice(self, qid: str) -> tuple[str | None, float, dict]:
        """(the option chosen, its confidence, every option's probability)."""
        a = self.answers.get(qid)
        if not isinstance(a, dict) or a.get("type") != "choice":
            return None, 0.0, {}
        probs = a.get("probabilities") if isinstance(a.get("probabilities"), dict) else {}
        conf = a.get("confidence")
        return (a.get("choice") if isinstance(a.get("choice"), str) else None,
                float(conf) if isinstance(conf, (int, float)) else 0.0, probs)

    def noul(self, qid: str) -> float | None:
        a = self.answers.get(qid)
        v = a.get("noul") if isinstance(a, dict) else None
        return float(v) if isinstance(v, (int, float)) else None


def paused() -> str | None:
    """Why calls are paused now (`empty`, `bad_key`), or None."""
    now = time.monotonic()
    for reason, until in list(_paused.items()):
        if now < until:
            return reason
        _paused.pop(reason, None)
    return None


def reset() -> None:
    _paused.clear()


def _headers() -> dict:
    h = {"Content-Type": "application/json"}
    if not settings.egress_url():
        h["Authorization"] = f"Bearer {settings.api_key()}"
    return h


def _log(row: dict) -> None:
    logger.info("jev purpose=%s outcome=%s status=%s ms=%s input_tokens=%s cost_usd=%.6f",
                row.get("purpose"), row.get("outcome"), row.get("status"), row.get("ms"),
                row.get("input_tokens"), float(row.get("cost_usd") or 0))
    ledger.record_call(row)


async def ask(state, questions: dict, *, purpose: str,
              timeout: float | None = None) -> Result | None:
    """Jev's answers to `questions` over `state`, or None (recorded why)."""
    if not settings.enabled():
        return None
    why = paused()
    if why is not None:
        _log({"purpose": purpose, "outcome": f"paused:{why}"})
        return None
    body = {"state": state, "model": settings.model(), "questions": questions}
    t0 = time.monotonic()
    row: dict = {"purpose": purpose, "questions": len(questions)}
    try:
        async with httpx.AsyncClient(transport=transport,
                                     timeout=timeout or settings.timeout_s()) as http:
            r = await http.post(f"{settings.base_url()}/v1/systemone", headers=_headers(),
                                json=body)
    except Exception as e:  # noqa: BLE001 - never raises
        row.update(outcome="error", error=type(e).__name__,
                   ms=round((time.monotonic() - t0) * 1000))
        _log(row)
        return None
    ms = (time.monotonic() - t0) * 1000
    row.update(status=r.status_code, ms=round(ms), request_id=r.headers.get("x-typesafe-request-id"))
    if r.status_code == 402:
        _paused["empty"] = time.monotonic() + PAUSE_S["empty"]
        row["outcome"] = "empty"
    elif r.status_code in (401, 403):
        _paused["bad_key"] = time.monotonic() + PAUSE_S["bad_key"]
        row["outcome"] = "bad_key"
    elif r.status_code != 200:
        row["outcome"] = "http_error"
    if r.status_code != 200:
        _log(row)
        return None
    try:
        data = r.json()
    except ValueError:
        data = None
    answers = data.get("answers") if isinstance(data, dict) else None
    if not isinstance(answers, dict):
        row["outcome"] = "malformed"
        _log(row)
        return None
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    tokens = usage.get("input_tokens") if isinstance(usage.get("input_tokens"), int) else 0
    row.update(outcome="ok", model=data.get("model"), input_tokens=tokens,
               output_tokens=usage.get("output_tokens"), cost_usd=settings.cost_usd(tokens))
    _log(row)
    return Result(answers=answers, model=str(data.get("model") or ""), ms=ms,
                  input_tokens=tokens, request_id=row.get("request_id") or "", raw=data)


async def funded(timeout: float = 10.0) -> tuple[str, str]:
    """(state, detail) for the funds line: `funded` when a one-question
    probe is answered (it costs about $0.00002), `empty` on HTTP 402,
    `bad key`, `unreachable`, or `not configured`. The API has no balance
    endpoint (every guess 404s), so zero or not zero is what it tells."""
    if not settings.enabled():
        return "not configured", ("the egress gateway has no Jev key" if settings.egress_url()
                                  else "no DAYDREAM_JEV_API_KEY")
    body = {"state": "A probe of whether this account can answer.", "model": settings.model(),
            "questions": {"ok": {"type": "noul", "instructions": "Is this a probe?",
                                 "criteria": {"true": "yes", "false": "no"}}}}
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(transport=transport, timeout=timeout) as http:
            r = await http.post(f"{settings.base_url()}/v1/systemone", headers=_headers(),
                                json=body)
    except Exception as e:  # noqa: BLE001
        _log({"purpose": "funds_probe", "outcome": "error", "error": type(e).__name__})
        return "unreachable", type(e).__name__
    ms = round((time.monotonic() - t0) * 1000)
    tokens = 0
    if r.status_code == 200:
        try:
            tokens = int((r.json().get("usage") or {}).get("input_tokens") or 0)
        except (ValueError, AttributeError, TypeError):
            tokens = 0
    _log({"purpose": "funds_probe", "status": r.status_code, "ms": ms,
          "input_tokens": tokens, "cost_usd": settings.cost_usd(tokens),
          "outcome": {200: "ok", 402: "empty"}.get(r.status_code, "http_error")})
    if r.status_code == 200:
        return "funded", f"a probe answered in {ms} ms"
    if r.status_code == 402:
        return "empty", "HTTP 402: the account has no credits"
    if r.status_code in (401, 403):
        return "bad key", f"HTTP {r.status_code}"
    return "unreachable", f"HTTP {r.status_code}"
