"""`bin/game world refresh` (daydream/refresh.py): authored content reaches a
played world without losing play. Fixture world, zero LLM calls."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from daydream import db, events, objects, refresh, story, worldclock, worldstate
from daydream.skills import effects
from tests.story_helpers import FIXTURE, WORLD, at, load, player, say

pytestmark = pytest.mark.tier_medium


@pytest.fixture(autouse=True)
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("DAYDREAM_VILLAGE_ENABLED", "0")
    at("2026-10-01T10:00:00+00:00")
    load(tmp_path)
    yield
    worldclock.set_fake_now(None)
    db.close_db()
    events.reset_subscribers()


def _envelope(tmp_path, mutate) -> Path:
    env = copy.deepcopy(FIXTURE)
    mutate(env)
    p = tmp_path / "next.json"
    p.write_text(json.dumps(env))
    return p


def _hob_topic_text(env):
    hob = next(t for t in env["toons"] if t["id"] == "t-hob")
    return hob["properties"]["topics"][0]


async def test_refresh_carries_authored_fixes_and_keeps_play(tmp_path):
    ada = player(1, "Ada", "r-lane")
    await say(ada, "take oats")
    # Play writes a key on an authored object, and grows a room off r-lane.
    effects.dispatch_effects(
        [{"kind": "set_property", "target_id": "t-hob", "key": "presence_text",
          "value": "Hob is asleep on a bench."}],
        actor_id=ada, room_id="r-lane", world_id=WORLD, allowed=effects.RULE_KINDS)
    objects.spawn(WORLD, "room", "Moss Stair", None, object_id="r-moss",
                  properties={"title": "Moss Stair", "exits": {"west": "r-lane"},
                              "grown": {"phrase": "a mossy stair"}})
    lane = objects.get("r-lane")
    objects.set_property("r-lane", "exits", {**lane.properties["exits"], "east": "r-moss"})
    objects.set_property("r-lane", "description_cached",
                         (lane.properties.get("description_cached") or "The lane.")
                         + " A new way opens to the east, toward Moss Stair.")
    rel_before = story.rel(WORLD, "t-wynn", ada)

    def fix(env):
        _hob_topic_text(env)["variants"] = ["'Twelve lamps, and every one polished.'"]
        env["things"].append({"id": "o-new-bench", "name": "new bench",
                              "location": {"room": "r-green"}, "fixture": True,
                              "seed": "a freshly painted bench"})
        hob = next(t for t in env["toons"] if t["id"] == "t-hob")
        hob["presence_text"] = "Hob waves from the ladder."
        hob["properties"]["declines_text"] = ["Hob shakes their head at the {item}."]
        env.setdefault("config", {})["rest_returns_things"] = True

    report = refresh.refresh(_envelope(tmp_path, fix))
    hob = objects.get("t-hob")
    # The authored fix is live...
    assert hob.properties["topics"][0]["variants"] == ["'Twelve lamps, and every one polished.'"]
    assert hob.properties["declines_text"] == ["Hob shakes their head at the {item}."]
    assert objects.get("o-new-bench").location_id == "r-green"
    assert "o-new-bench" in report["inserted"] and "t-hob" in report["updated"]
    # ...and play is kept: the player, their inventory, what play wrote, the
    # grown room, its exit, and the room text's new-way sentence.
    assert objects.get(ada).location_id == "r-lane"
    assert objects.get("o-oats").location_id == ada
    assert hob.properties["presence_text"] == "Hob is asleep on a bench."
    assert objects.get("r-moss") is not None
    lane = objects.get("r-lane")
    assert lane.properties["exits"]["east"] == "r-moss"
    assert lane.properties["description_cached"].endswith("A new way opens to the east, toward Moss Stair.")
    assert story.rel(WORLD, "t-wynn", ada) == rel_before
    assert worldstate.get(WORLD, "refresh:last")["inserted"] == 1
    assert worldstate.get(WORLD, "config")["rest_returns_things"] is True   # authored config
    from daydream import version
    stamped = db.get_conn().execute("SELECT world_version FROM worlds WHERE id = ?", (WORLD,)).fetchone()[0]
    assert stamped == version.WORLD_VERSION


async def test_refresh_check_writes_nothing(tmp_path):
    before = objects.get("t-hob").properties

    def fix(env):
        _hob_topic_text(env)["variants"] = ["'Changed.'"]

    report = refresh.refresh(_envelope(tmp_path, fix), check=True)
    assert "t-hob" in report["updated"]
    assert objects.get("t-hob").properties == before
    assert worldstate.get(WORLD, "refresh:last") is None


async def test_refresh_refuses_another_world(tmp_path):
    def other(env):
        env["world"]["slug"] = "elsewhere"

    with pytest.raises(SystemExit):
        refresh.refresh(_envelope(tmp_path, other))



async def test_refresh_sends_home_what_resting_players_hold(tmp_path):
    """A player who left before the rest-return rule arrived still holds a
    world object; the refresh that brings `home` sends it back."""
    from daydream import toons
    ada = player(1, "Ada", "r-lane")
    await say(ada, "take oats")
    objects.move(ada, "r-mill")
    toons.kick_slot(1)                      # no home yet: the oats stay carried
    assert objects.get("o-oats").location_id == ada

    def enable(env):
        env.setdefault("config", {})["rest_returns_things"] = True

    report = refresh.refresh(_envelope(tmp_path, enable))
    assert "o-oats" in report["sent_home"]
    assert objects.get("o-oats").location_id == "r-lane"


async def test_refresh_keeps_a_grown_exit_the_envelope_now_authors(tmp_path):
    """A way play grew keeps its direction when the envelope later authors
    one there (codereview 2026-09-27): the grown room is never orphaned, the
    rest of the change lands, and the refresh reports the conflict."""
    objects.spawn(WORLD, "room", "Moss Stair", None, object_id="r-moss",
                  properties={"title": "Moss Stair", "exits": {"west": "r-lane"},
                              "grown": {"phrase": "a mossy stair"}})
    lane = objects.get("r-lane")
    objects.set_property("r-lane", "exits", {**lane.properties["exits"], "east": "r-moss"})

    def author_east(env):
        rooms = {r["id"]: r for r in env["rooms"]}
        rooms["r-lane"]["exits"]["east"] = "r-mill"
        rooms["r-mill"]["exits"]["west"] = "r-lane"

    report = refresh.refresh(_envelope(tmp_path, author_east))
    assert objects.get("r-lane").properties["exits"]["east"] == "r-moss"
    assert objects.get("r-mill").properties["exits"]["west"] == "r-lane"
    assert report["exit_conflicts"] == {"r-lane": ["east -> r-moss (envelope: r-mill)"]}


async def test_refresh_refuses_a_major_version_change(tmp_path):
    """A MAJOR mismatch is the boot gate's refusal: a refresh never stamps
    past it, and names world reset instead."""
    db.get_conn().execute("UPDATE worlds SET world_version = '99.0' WHERE id = ?", (WORLD,))
    with pytest.raises(SystemExit, match="world reset"):
        refresh.refresh(_envelope(tmp_path, lambda env: None))
