"""Tiered test dispatcher: one entry point for every flavor from unit to
aesthetic review. Invoked by `bin/game test <tier>`.

Tiers (see TESTING.md for the full contract):

  short   unit / fast           -m "tier_short"                   ~<10s
  medium  integration           -m "tier_short or tier_medium"    ~<90s
  long    real-GPU drift + E2E  -m "tier_short or tier_medium or tier_long"
                                                                  ~<15min
  ci      semantic alias for long; intended for "run all that's
          machine-verifiable" invocations. May diverge from long
          later (structured exit codes, compact summary).
  human   aesthetic rubric via qpeek; lands in commit 4 as
          daydream.testing.human_eval.

Operational target (--target / DAYDREAM_TARGET):

  local         full behavior (default).
  staging       scaffolded; tier_medium/long tests skip cleanly
                until staging probes are wired.
  prod_verify   scaffolded; same skip behavior until read-only
                probes are wired.

Remaining args after the tier are forwarded to pytest unchanged so
`bin/game test short -q -k cache` becomes `pytest -m tier_short -q -k cache`.
An explicit `--` separator is also accepted and stripped.

Flat argparse (tier as a positional, --target parsed, everything else
passed through via parse_known_args) instead of subparsers — avoids the
argparse.REMAINDER quirk where a pytest flag like `-q` after a subparser
gets rejected as an unknown option."""

from __future__ import annotations

import argparse
import os
import sys

import pytest


_TIERS = ("short", "medium", "long", "ci")

_TIER_MARKERS: dict[str, str] = {
    "short": "tier_short",
    "medium": "tier_short or tier_medium",
    "long": "tier_short or tier_medium or tier_long",
    "ci": "tier_short or tier_medium or tier_long",
}


def _preamble(tier: str, target: str, marker: str) -> None:
    """One-line header so the tier+target actually in effect is visible
    above pytest's own output, even under -q."""
    print(f"tier={tier} target={target} marker={marker!r}", file=sys.stderr, flush=True)


def _run_pytest(tier: str, target: str, extra: list[str]) -> int:
    os.environ["DAYDREAM_TARGET"] = target
    marker = _TIER_MARKERS[tier]
    _preamble(tier, target, marker)
    argv = ["-m", marker, *extra]
    return int(pytest.main(argv))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="daydream.testing",
        description="tiered test dispatcher for daydream (see TESTING.md)",
    )
    p.add_argument(
        "tier",
        choices=list(_TIERS),
        help="short=fast unit; medium=integration; long=real-GPU drift; ci=alias for long",
    )
    p.add_argument(
        "--target",
        choices=["local", "staging", "prod_verify"],
        default=os.environ.get("DAYDREAM_TARGET", "local"),
        help="operational target (default: local; staging/prod_verify are "
        "scaffolded and skip tier_medium/long cleanly)",
    )

    # Everything argparse doesn't consume goes straight to pytest. Using
    # parse_known_args means `bin/game test short -q -k foo` works
    # without a leading `--`; we still strip a leading `--` if supplied.
    args, pytest_args = p.parse_known_args(argv)
    if pytest_args and pytest_args[0] == "--":
        pytest_args = pytest_args[1:]

    return _run_pytest(args.tier, args.target, pytest_args)


if __name__ == "__main__":
    sys.exit(main())
