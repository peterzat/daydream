"""The Jev ledger: append-only JSONL under `<data dir>/jev/` (never in the
repo; docs/DATA-LIFECYCLE.md).

- `calls.jsonl`: every call (purpose, outcome, HTTP status, latency, tokens,
  cost, model, request id). Never the request's text.
- `decisions.jsonl`: every decision a surface made with Jev on (both
  answers, which served, agreement, Jev's confidence, the dreamer's id, and
  the words the decision was about, so a disagreement can be read). This
  holds what players typed, so it follows the input log's rules: it stays
  on this box, rows older than RETAIN_DAYS are pruned, and `account delete`
  erases a person's rows (purge_toons). Not in backups: it is telemetry.

Fail-soft: a ledger write that fails is logged and play goes on. Appends
and rewrites take an flock, so a purge from the shell never loses a row the
server is writing.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import fcntl
import json
import logging
import os
import time
from collections.abc import Iterable, Iterator
from pathlib import Path

from daydream import config, worldclock

logger = logging.getLogger(__name__)

RETAIN_DAYS = 30
FILES = ("calls.jsonl", "decisions.jsonl")
_PRUNE_EVERY_S = 3600.0
_last_prune = 0.0


def root() -> Path:
    return config.data_dir() / "jev"


@contextlib.contextmanager
def _locked():
    d = root()
    d.mkdir(parents=True, exist_ok=True)
    with (d / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield d
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def _append(name: str, row: dict) -> None:
    try:
        with _locked() as d, (d / name).open("a", encoding="utf-8") as f:
            f.write(json.dumps({"at": worldclock.iso(), **row}, ensure_ascii=False,
                               default=str) + "\n")
    except Exception:  # noqa: BLE001 - the ledger never breaks play
        logger.exception("jev ledger: could not append to %s", name)
    _maybe_prune()


def record_call(row: dict) -> None:
    _append("calls.jsonl", row)


def record_decision(row: dict) -> None:
    _append("decisions.jsonl", row)


def read(name: str) -> Iterator[dict]:
    path = root() / name
    if not path.exists():
        return
    with path.open(encoding="utf-8") as f:
        for line in f:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict):
                yield row


def calls() -> list[dict]:
    return list(read("calls.jsonl"))


def decisions() -> list[dict]:
    return list(read("decisions.jsonl"))


def spent_usd() -> float:
    return sum(float(r.get("cost_usd") or 0) for r in read("calls.jsonl"))


def _rewrite(keep) -> int:
    """Rewrite each file keeping the rows `keep(name, row)` accepts; the
    number of rows dropped."""
    dropped = 0
    with _locked() as d:
        for name in FILES:
            path = d / name
            if not path.exists():
                continue
            kept = []
            with path.open(encoding="utf-8") as f:
                for line in f:
                    try:
                        row = json.loads(line)
                    except ValueError:
                        dropped += 1
                        continue
                    if keep(name, row):
                        kept.append(line if line.endswith("\n") else line + "\n")
                    else:
                        dropped += 1
            tmp = path.with_suffix(".tmp")
            tmp.write_text("".join(kept), encoding="utf-8")
            os.replace(tmp, path)
    return dropped


def prune(days: int = RETAIN_DAYS) -> int:
    """Drop rows older than `days` (by their own time)."""
    cutoff = worldclock.iso(worldclock.now() - dt.timedelta(days=days))
    return _rewrite(lambda name, row: str(row.get("at", "")) >= cutoff)


def _maybe_prune() -> None:
    global _last_prune
    now = time.monotonic()
    if now - _last_prune < _PRUNE_EVERY_S:
        return
    _last_prune = now
    try:
        prune()
    except Exception:  # noqa: BLE001
        logger.exception("jev ledger: prune failed")


def purge_toons(toon_ids: Iterable[str]) -> int:
    """Erase every decision about these dreamers (a person's end: `account
    delete`). Calls hold no text and no dreamer, so they stay."""
    ids = {t for t in toon_ids if t}
    if not ids or not root().exists():
        return 0
    return _rewrite(lambda name, row: name != "decisions.jsonl" or row.get("toon") not in ids)
