"""The scenery lint is a ratchet (spec 2026-09-29 criterion 10). Every phrase
room prose or a thing's look names that nothing answers to (no object,
alias, glimpse, scenery, exit name, person or place) is listed; the list may
only shrink on its own. New prose that names something new must give it an
answer or add it to the baseline, which is a reviewed edit like a golden
(`python -m daydream.prose_nouns --write worlds/lost-hours.json`)."""

import copy
import json
from pathlib import Path

import pytest

from daydream import prose_nouns

pytestmark = pytest.mark.tier_short

ROOT = Path(__file__).resolve().parent.parent
ENV = json.loads((ROOT / "worlds/lost-hours.json").read_text())


def test_no_new_prose_names_something_nothing_answers_to():
    baseline = set(json.loads(prose_nouns.BASELINE.read_text()))
    new = sorted(set(prose_nouns.uncovered(ENV)) - baseline)
    assert not new, (
        "New prose names things nothing answers to. Give each an object, alias, "
        "glimpse, scenery or exit name, or (after review) add it to "
        f"{prose_nouns.BASELINE.name}:\n  " + "\n  ".join(new))


def test_the_lint_sees_a_new_noun_and_its_answer():
    env = copy.deepcopy(ENV)
    room = next(r for r in env["rooms"] if r["id"] == "r-cellar")
    room["description"] += " A copper kettle hums on a trivet."
    found = set(prose_nouns.uncovered(env)) - set(prose_nouns.uncovered(ENV))
    assert found == {"r-cellar: copper kettle hums", "r-cellar: trivet"}
    room.setdefault("properties", {}).setdefault("glimpsed", []).append(
        {"names": ["kettle", "trivet"], "text": "Umber's, and hot."})
    assert not set(prose_nouns.uncovered(env)) - set(prose_nouns.uncovered(ENV))


def test_phrases_stop_at_prepositions_and_determiners():
    assert prose_nouns.phrases("The lantern by the stair burns low.") == [["lantern"], ["stair", "burns", "low"]]
    assert prose_nouns.phrases("each holding a folded slip of paper") == [["holding"], ["folded", "slip"]]
