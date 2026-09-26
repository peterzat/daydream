"""The static analyzer (SPEC 2026-09-26 criterion 1): proves rooms reachable
and arcs solvable, and fails loudly on deliberately broken worlds."""

import copy

import pytest

from daydream import analyzer
from tests.story_helpers import FIXTURE

pytestmark = pytest.mark.tier_short


def test_the_fixture_world_is_sound():
    assert analyzer.analyze(copy.deepcopy(FIXTURE)) == []


def _broken(mutate):
    env = copy.deepcopy(FIXTURE)
    mutate(env)
    return analyzer.analyze(env)


def test_flags_an_unreachable_room():
    def cut(e):
        e["rooms"][0]["exits"].pop("east")   # the lane
        e["rooms"][2]["exits"] = {}
    probs = _broken(cut)
    assert any("room r-lane is unreachable" in p for p in probs)
    # ...and the guest who arrives there, and the oats that live there.
    assert any("o-oats" in p for p in probs)


def test_flags_a_beat_with_no_producer():
    def orphan(e):
        e["arcs"]["moth"]["beats"]["extra"] = {"text": "Nothing brings this about."}
    assert any("beat extra: no deterministic producer" in p for p in _broken(orphan))


def test_flags_an_ending_nothing_can_bring_about():
    def lonely(e):
        e["arcs"]["reed"]["endings"]["lost"] = {"text": "Never happens."}
    assert any("ending lost: nothing can bring it about" in p for p in _broken(lonely))


def test_flags_an_arc_that_can_never_open():
    def sealed(e):
        e["arcs"]["reed"].pop("arrival")
    assert any("arc reed can never open" in p for p in _broken(sealed))


def test_flags_a_needed_item_that_is_never_obtainable():
    def hide(e):
        e["things"][0]["location"] = "offstage"   # the oats
        e["rules"].append({"on": "give", "if": [{"dobj": "o-oats"}], "do": [
            {"kind": "advance_beat", "arc": "reed", "beat": "sing"}]})
    probs = _broken(hide)
    assert any("thing o-oats is never obtainable" in p for p in probs)


def test_flags_a_talk_beat_whose_npc_is_never_reachable():
    def strand(e):
        e["toons"][1]["room"] = "offstage"   # Wynn
    assert any("NPC t-wynn is never reachable" in p for p in _broken(strand))


def test_flags_an_after_cycle():
    def loop(e):
        e["arcs"]["moth"]["beats"]["hob-notices"]["after"] = ["hear-story"]
    assert any("'after' cycle" in p for p in _broken(loop))
