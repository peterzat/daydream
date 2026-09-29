"""The scenery lint (spec 2026-09-29 criterion 10): what room prose names
that nothing answers to.

A phrase is what a determiner ("the", "a", "its", ...) opens, up to three
words, stopping at a preposition, a conjunction or punctuation. It is
covered when any of its words is a name the world answers to where the
prose is read: an object here (or its alias), a glimpse, the room's
scenery, an exit's name, a person, or a place. Everything else is listed.

There is no part-of-speech tagging, so the list is noisy ("the dream", "a
hush"); it is a ratchet, not a rule. `tests/test_prose_nouns.py` compares
the list with a committed baseline and fails only on phrases that new prose
adds; changing the baseline is a reviewed edit, like a golden.
`python -m daydream.prose_nouns --write <envelope>` rewrites it."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

DETERMINERS = frozenset({"the", "a", "an", "its", "their", "his", "her", "every", "each",
                         "some", "one", "two", "three"})
STOP = frozenset("""
of in on at to from with by for over under into onto through above below behind beside
near toward towards across around along up down out off and or but that which who whom
where when while as like than is are was were be been being has have had it its not no
so if then there here this these those very just only
""".split())
BASELINE = Path(__file__).resolve().parent.parent / "tests" / "baselines" / "prose_nouns.json"
_WORD = re.compile(r"[a-z][a-z'-]*|[.,;:!?]")


def _singular(w: str) -> str:
    w = re.sub(r"['\u2019]s$", "", w)  # a possessive names the thing too
    return w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w


def _words_of(names) -> set[str]:
    out: set[str] = set()
    for n in names or []:
        if isinstance(n, str):
            out |= {_singular(w) for w in re.findall(r"[a-z][a-z'-]*", n.lower())}
    return out


def phrases(text: str) -> list[list[str]]:
    """The determiner-opened phrases of a text, as word lists."""
    toks = _WORD.findall((text or "").lower())
    out = []
    for i, t in enumerate(toks):
        if t not in DETERMINERS:
            continue
        window = []
        for w in toks[i + 1:i + 4]:
            if w in STOP or w in DETERMINERS or not w[0].isalpha():
                break
            window.append(w)
        if window:
            out.append(window)
    return out


def _glimpse_names(props: dict) -> list[str]:
    names = []
    for e in props.get("glimpsed") or []:
        if isinstance(e, dict):
            names += [n for n in e.get("names") or [] if isinstance(n, str)]
    return names


def uncovered(env: dict) -> list[str]:
    """Sorted "<room or thing id>: <phrase>" lines for every uncovered phrase
    in room descriptions and things' looks."""
    rooms = {r["id"]: r for r in env.get("rooms", [])}
    things = env.get("things", [])
    toons = env.get("toons", [])
    cfg = env.get("config") or {}
    everywhere = _words_of([t.get("name") for t in toons])
    for t in toons:
        everywhere |= _words_of(t.get("aliases"))
    everywhere |= _words_of([r.get("title") for r in rooms.values()])

    def room_of(th: dict) -> str | None:
        loc = th.get("location")
        if isinstance(loc, dict) and "room" in loc:
            return loc["room"]
        if isinstance(loc, dict) and "in" in loc:
            parent = next((x for x in things if x.get("id") == loc["in"]), None)
            return room_of(parent) if parent else None
        return None

    covered_in: dict[str, set[str]] = {}
    for rid, r in rooms.items():
        props = r.get("properties") or {}
        words = set(everywhere)
        words |= _words_of(_glimpse_names(props))
        for names in (props.get("exit_names") or {}).values():
            words |= _words_of(names)
        for sc in cfg.get("scenery") or []:
            if isinstance(sc, dict) and rid in (sc.get("rooms") or []):
                words |= _words_of(sc.get("names"))
        covered_in[rid] = words
    for th in things:
        rid = room_of(th)
        if rid in covered_in:
            covered_in[rid] |= _words_of([th.get("name")]) | _words_of(th.get("aliases"))
            covered_in[rid] |= _words_of(_glimpse_names(th.get("properties") or {}))

    found: set[str] = set()

    def check(where: str, text: str, words: set[str]) -> None:
        for window in phrases(text):
            if not any(_singular(w) in words for w in window):
                found.add(f"{where}: {' '.join(window)}")

    for rid, r in rooms.items():
        check(rid, r.get("description", ""), covered_in[rid])
    for th in things:
        rid = room_of(th)
        if rid not in covered_in:
            continue
        props = th.get("properties") or {}
        texts = [th.get("seed", "")] + [v for v in (props.get("state_text") or {}).values()
                                        if isinstance(v, str)]
        for text in texts:
            check(th["id"], text, covered_in[rid])
    return sorted(found)


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[0] != "--write":
        print("usage: python -m daydream.prose_nouns --write <envelope.json>", file=sys.stderr)
        return 2
    env = json.loads(Path(argv[1]).read_text())
    BASELINE.write_text(json.dumps(uncovered(env), indent=2) + "\n")
    print(f"wrote {BASELINE}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
