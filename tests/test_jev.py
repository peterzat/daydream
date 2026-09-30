"""Jev, the optional hosted decision model (daydream/jev; docs/EXTERNAL.md):
on exactly when a key is reachable (the repo's .env in dev, the egress
gateway in prod), off otherwise; the client never raises, waits at most its
timeout, and pauses on an empty account, a refused key or an outage; the
funds probe says zero or not zero; the
seam runs the local path alone when off and both when on; the ledger keeps
no text in its calls, prunes after RETAIN_DAYS and forgets a person. No
network: a mock transport."""

import asyncio
import json
import logging
import time

import httpx
import pytest

from daydream import worldclock
from daydream.jev import cli, client, ledger, seam, settings

pytestmark = pytest.mark.tier_short

ANSWER = {"model": "jev-1.13.0",
          "answers": {"verb": {"type": "choice", "choice": "take", "confidence": 0.9,
                               "probabilities": {"take": 0.95, "none": 0.05}},
                      "q": {"type": "noul", "noul": 0.2}},
          "usage": {"input_tokens": 1000, "output_tokens": 20}}


@pytest.fixture()
def jev(tmp_path, monkeypatch):
    """A fake key, a ledger in tmp, and a transport that answers from state."""
    monkeypatch.setenv("DAYDREAM_JEV_API_KEY", "test-key")
    monkeypatch.delenv("DAYDREAM_EGRESS_URL", raising=False)
    monkeypatch.setattr(ledger, "root", lambda: tmp_path / "jev")
    client.reset()
    settings.forget()
    state = {"status": 200, "body": ANSWER, "calls": [], "raise": None, "headers": []}

    def handler(request: httpx.Request) -> httpx.Response:
        state["calls"].append(json.loads(request.content))
        state["headers"].append(dict(request.headers))
        state["url"] = str(request.url)
        if state["raise"]:
            raise state["raise"]
        return httpx.Response(state["status"], json=state["body"],
                              headers={"x-typesafe-request-id": "req_1"})

    monkeypatch.setattr(client, "transport", httpx.MockTransport(handler))
    yield state
    client.reset()
    settings.forget()


def _ask():
    return asyncio.run(client.ask("state", {"verb": {"type": "choice"}}, purpose="test"))


def test_no_key_is_off_and_never_calls(monkeypatch, jev):
    monkeypatch.delenv("DAYDREAM_JEV_API_KEY")
    assert not settings.enabled()
    assert _ask() is None and jev["calls"] == []
    assert cli.status_line() == "jev: off (no DAYDREAM_JEV_API_KEY)"


def test_a_key_is_on_and_calls_direct_with_it(jev):
    assert settings.enabled()
    r = _ask()
    assert r.choice("verb") == ("take", 0.9, {"take": 0.95, "none": 0.05})
    assert r.noul("q") == 0.2 and r.choice("q") == (None, 0.0, {})
    assert jev["url"] == "https://api.typesafe.ai/v1/systemone"
    assert jev["headers"][0]["authorization"] == "Bearer test-key"
    assert jev["calls"][0]["model"] == settings.DEFAULT_MODEL  # pinned, not an alias


def test_through_the_gateway_the_game_holds_no_key(jev, monkeypatch):
    """Prod: the gateway says whether its jev route has a key, and adds it;
    the game sends none, and has none."""
    monkeypatch.delenv("DAYDREAM_JEV_API_KEY")
    monkeypatch.setenv("DAYDREAM_EGRESS_URL", "http://127.0.0.1:59999")
    monkeypatch.setattr(settings, "_gateway_has_key", lambda gw: True)
    r = _ask()
    assert r is not None and jev["url"] == "http://127.0.0.1:59999/jev/v1/systemone"
    assert "authorization" not in jev["headers"][0]
    monkeypatch.setattr(settings, "_gateway_has_key", lambda gw: False)
    assert not settings.enabled()
    assert cli.status_line() == "jev: off (the egress gateway has no Jev key)"


def test_prod_uses_the_gateway_by_default(monkeypatch):
    from daydream import config

    monkeypatch.delenv("DAYDREAM_EGRESS_URL", raising=False)
    monkeypatch.setenv("DAYDREAM_ENV", "prod")
    assert settings.egress_url() == config.EGRESS_URL == "http://127.0.0.1:54323"
    monkeypatch.setenv("DAYDREAM_ENV", "dev")
    assert settings.egress_url() is None


def test_each_call_is_a_log_line_and_a_ledger_row_without_text(jev, caplog):
    with caplog.at_level(logging.INFO, logger="daydream.jev"):
        asyncio.run(client.ask("the player said SECRET WORDS", {"q": {"type": "noul"}},
                               purpose="judge"))
    [row] = ledger.calls()
    assert row["outcome"] == "ok" and row["input_tokens"] == 1000
    assert row["cost_usd"] == pytest.approx(0.000042)
    assert "SECRET" not in json.dumps(row) and "SECRET" not in caplog.text
    assert "jev purpose=judge outcome=ok" in caplog.text


@pytest.mark.parametrize("status,outcome,pause", [
    (402, "empty", "empty"), (401, "bad_key", "bad_key"), (429, "http_error", "unreachable"),
    (500, "http_error", "unreachable"), (404, "http_error", None)])
def test_a_refusal_is_none_and_an_empty_account_pauses(jev, status, outcome, pause):
    jev["status"], jev["body"] = status, {"detail": {"error_type": "billing_error"}}
    assert _ask() is None
    assert ledger.calls()[-1]["outcome"] == outcome
    assert client.paused() == pause
    _ask()
    assert len(jev["calls"]) == (1 if pause else 2)  # paused: no second request


def test_a_network_error_or_a_malformed_answer_is_none(jev):
    jev["raise"] = httpx.ConnectTimeout("slow")
    assert _ask() is None and ledger.calls()[-1]["outcome"] == "error"
    assert client.paused() == "unreachable"  # a minute of local answers
    client.reset()
    jev["raise"], jev["body"] = None, {"answers": "nope"}
    assert _ask() is None and ledger.calls()[-1]["outcome"] == "malformed"
    assert client.paused() is None


def test_a_call_waits_at_most_the_timeout_in_all(jev, monkeypatch):
    """Codereview 2026-09-30d: httpx's timeout bounds each phase, so an
    outage cost several timeouts on every free line; the call has one
    deadline, and after it the calls pause."""
    monkeypatch.setenv("DAYDREAM_JEV_TIMEOUT", "0.5")

    async def slow(request):
        await asyncio.sleep(5)
        return httpx.Response(200, json=ANSWER)

    monkeypatch.setattr(client, "transport", httpx.MockTransport(slow))
    t0 = time.monotonic()
    assert _ask() is None
    assert time.monotonic() - t0 < 2
    assert ledger.calls()[-1]["error"] == "TimeoutError"
    assert client.paused() == "unreachable"
    _ask()
    assert ledger.calls()[-1]["outcome"] == "paused:unreachable"


@pytest.mark.parametrize("status,state", [(200, "funded"), (402, "empty"),
                                          (401, "bad key"), (503, "unreachable")])
def test_the_funds_probe_says_zero_or_not(jev, status, state):
    jev["status"] = status
    got, _ = asyncio.run(client.funded())
    assert got == state
    assert ledger.calls()[-1]["purpose"] == "funds_probe"


def test_the_status_line_says_on_funded_and_spend(jev):
    line = cli.status_line()
    assert line.startswith("jev: on, funded (a probe answered in ") and "; direct)" in line
    assert "spent $0.0000 tracked here" in line
    n = len(jev["calls"])
    assert cli.status_line(probe=False).startswith("jev: on, funded (last known, ")
    assert len(jev["calls"]) == n  # without a probe: no call
    jev["status"] = 402
    asyncio.run(client.funded())
    assert cli.status_line(probe=False).startswith("jev: on, empty (last known, ")


# ---- the seam ----------------------------------------------------------------


def _decide(local_value, answer, calls, combine=None, toon="t-1"):
    async def local():
        calls.append("local")
        return local_value

    async def remote():
        calls.append("remote")
        return answer

    return asyncio.run(seam.decide("s", local=local, remote=remote, agree=lambda a, b: a == b,
                                   about={"line": "hi"}, toon=toon, combine=combine))


def test_off_runs_only_the_local_path(jev, monkeypatch):
    monkeypatch.delenv("DAYDREAM_JEV_API_KEY")
    calls = []
    assert _decide([True], seam.Answer([False], 0.99), calls) == [True]
    assert calls == ["local"] and ledger.decisions() == []


def test_on_serves_jev_when_confident_else_local(jev):
    calls = []
    assert _decide("a", seam.Answer("b", 0.9), calls) == "b"
    assert sorted(calls) == ["local", "remote"]
    row = ledger.decisions()[-1]
    assert row["served"] == "jev" and row["agree"] is False and row["toon"] == "t-1"
    assert row["local"] == "a" and row["jev"] == "b" and row["served_value"] == "b"
    assert _decide("a", seam.Answer("b", 0.2), []) == "a"  # below the minimum
    assert ledger.decisions()[-1]["served"] == "local"
    assert _decide("a", None, []) == "a"  # Jev silent
    assert ledger.decisions()[-1]["jev"] is None


def test_on_with_a_rule_serves_the_rule(jev):
    got = _decide([True, False], seam.Answer([False, True], 0.5),
                  [], combine=lambda lv, a: [x or y for x, y in zip(lv, a.value, strict=True)])
    assert got == [True, True] and ledger.decisions()[-1]["served"] == "combined"


# ---- the ledger's lifecycle --------------------------------------------------


def test_the_reports_p95_is_never_below_its_p50(jev):
    """Nearest rank (prod 2026-09-30: two calls read p50 302 ms, p95 278)."""
    from daydream.jev import cli

    for ms in (325, 278):
        ledger.record_call({"purpose": "topics", "outcome": "ok", "ms": ms})
    assert "p50 302 ms, p95 325 ms" in cli.report()


def test_rows_older_than_the_retention_are_pruned(jev):
    worldclock.set_fake_now("2026-09-01T10:00:00+00:00")
    try:
        ledger.record_decision({"surface": "s", "toon": "t-old"})
        ledger.record_call({"purpose": "old"})
        worldclock.set_fake_now("2026-10-05T10:00:00+00:00")
        ledger.record_decision({"surface": "s", "toon": "t-new"})
        assert ledger.prune() == 2
        assert [r["toon"] for r in ledger.decisions()] == ["t-new"]
        assert ledger.calls() == []
    finally:
        worldclock.set_fake_now(None)


def test_a_persons_decisions_are_forgotten_and_the_rest_kept(jev):
    for toon in ("t-a", "t-b", "t-a"):
        ledger.record_decision({"surface": "topics", "toon": toon, "about": {"text": "hi"}})
    ledger.record_call({"purpose": "topics"})
    assert ledger.purge_toons(["t-a"]) == 2
    assert [r["toon"] for r in ledger.decisions()] == ["t-b"]
    assert len(ledger.calls()) == 1  # calls hold no dreamer and no text
