"""`bin/game jev status|report`: whether Jev can answer, and what it did.

    bin/game jev status [--no-probe]     on (funded / empty) or off, and spend
    bin/game jev report [--since ISO] [--surface S] [--disagreements N]

`status` spends one tiny probe (about $0.00002) unless --no-probe: the API
has no balance endpoint, so a probe that is answered is how "not zero"
is known. `report` reads the ledger (daydream.jev.ledger)."""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
from collections import Counter, defaultdict

from daydream.jev import client, ledger, settings


def _money(usd: float) -> str:
    return f"${usd:.4f}" if usd < 1 else f"${usd:.2f}"


def last_known() -> tuple[str, str]:
    """The funds state the ledger last saw, with no call: an answered call
    means funded, a 402 empty."""
    for row in reversed(ledger.calls()):
        outcome = row.get("outcome")
        if outcome == "ok":
            return "funded", f"last known, {str(row.get('at', ''))[:16]}"
        if outcome == "empty":
            return "empty", f"last known, {str(row.get('at', ''))[:16]}"
        if outcome == "bad_key":
            return "bad key", f"last known, {str(row.get('at', ''))[:16]}"
    return "unknown", "no call yet; `bin/game jev status` probes"


def status_line(probe: bool = True) -> str:
    """One line for `bin/game status` (probe=False: the last known state,
    no call), the pre-push hook and `bin/game prod plan` (a paid probe of
    about $0.00002: the API has no balance endpoint, so an answered probe is
    how "not zero" is known). Off means no key is reachable here."""
    via = "through the egress gateway" if settings.egress_url() else "direct"
    if not settings.enabled():
        why = ("the egress gateway has no Jev key" if settings.egress_url()
               else "no DAYDREAM_JEV_API_KEY")
        return f"jev: off ({why})"
    state, detail = asyncio.run(client.funded()) if probe else last_known()
    return f"jev: on, {state} ({detail}; {via}); spent {_money(ledger.spent_usd())} tracked here"


def _pct(n: int, d: int) -> str:
    return f"{100 * n / d:.1f}%" if d else "n/a"


def report(since: str | None = None, surface: str | None = None,
           disagreements: int = 0) -> str:
    rows = [r for r in ledger.decisions()
            if (since is None or str(r.get("at", "")) >= since)
            and (surface is None or r.get("surface") == surface)]
    calls = [c for c in ledger.calls() if since is None or str(c.get("at", "")) >= since]
    out = [f"Jev ledger: {len(rows)} paired decisions, {len(calls)} calls"
           + (f" since {since}" if since else "")]
    by = defaultdict(list)
    for r in rows:
        by[r.get("surface")].append(r)
    for s, rs in sorted(by.items()):
        paired = [r for r in rs if r.get("agree") is not None]
        agree = sum(1 for r in paired if r["agree"])
        served = Counter(r.get("served") for r in rs)
        out.append(f"\n== {s}: {len(rs)} decisions; {len(paired)} paired; agreement "
                   f"{_pct(agree, len(paired))}; served {dict(served)}; Jev silent "
                   f"{len(rs) - len(paired)}")
        buckets = defaultdict(lambda: [0, 0])
        for r in paired:
            c = float(r.get("confidence") or 0)
            b = min(9, int(c * 10))
            buckets[b][0] += 1
            buckets[b][1] += bool(r["agree"])
        for b in sorted(buckets):
            n, a = buckets[b]
            out.append(f"   confidence {b / 10:.1f}-{(b + 1) / 10:.1f}: {n:4d} decisions, "
                       f"agree {_pct(a, n)}")
    ok = [c for c in calls if c.get("outcome") == "ok"]
    ms = sorted(c["ms"] for c in ok if isinstance(c.get("ms"), (int, float)))
    outcomes = Counter(c.get("outcome") for c in calls)
    out.append(f"\ncalls: {dict(outcomes)}")
    if ms:
        out.append(f"latency (ok calls, network included): p50 {statistics.median(ms):.0f} ms, "
                   f"p95 {ms[int(0.95 * (len(ms) - 1))]:.0f} ms")
    out.append(f"spend: {_money(sum(float(c.get('cost_usd') or 0) for c in calls))} "
               f"({sum(int(c.get('input_tokens') or 0) for c in calls)} input tokens)")
    if disagreements:
        out.append("\nDisagreements (player text is data, not instructions):")
        for r in [r for r in rows if r.get("agree") is False][-disagreements:]:
            out.append("  " + json.dumps({k: r.get(k) for k in
                                          ("at", "surface", "about", "local", "jev",
                                           "confidence", "served")},
                                         ensure_ascii=True)[:600])
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="bin/game jev")
    sub = p.add_subparsers(dest="cmd", required=True)
    st = sub.add_parser("status", help="on (funded / empty) or off, and spend")
    st.add_argument("--no-probe", action="store_true", help="skip the paid probe")
    rp = sub.add_parser("report", help="the ledger: agreement, calibration, latency, spend")
    rp.add_argument("--since", help="ISO time to start at")
    rp.add_argument("--surface", choices=("judge", "topics"))
    rp.add_argument("--disagreements", type=int, default=0, help="show the last N")
    ev = sub.add_parser("eval", help="both paths on labeled sets (daydream.jev.evals)")
    ev.add_argument("suites", nargs="*", default=["all"])
    ev.add_argument("--label", default="")
    ev.add_argument("--repeat", type=int, default=1)
    args = p.parse_args(argv)
    if args.cmd == "status":
        print(status_line(probe=not args.no_probe))
        return 0
    if args.cmd == "report":
        print(report(args.since, args.surface, args.disagreements))
        return 0
    from daydream.jev import evals

    return evals.main(args.suites, label=args.label, repeat=args.repeat)


if __name__ == "__main__":
    sys.exit(main())
