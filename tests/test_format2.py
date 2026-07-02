"""Format-2 world envelopes (SPEC 2026-07-02, Zork turn): relaxed counts,
stable authored ids, the location union, one-way exits as lint, fail-loud
section validation with zero writes, def:* blocks landing in world_state,
the treasure-scoring engine hooks, and the assembler's sugar expansion."""

import json
from pathlib import Path

import pytest

from daydream import config, db, events, objects, verbs, worldstate
from daydream.llm import bootstrap, format2

pytestmark = pytest.mark.tier_short


@pytest.fixture(autouse=True)
def clean_db():
    db.close_db()
    events.reset_subscribers()
    yield
    db.close_db()
    events.reset_subscribers()


def minimal_env(**overrides) -> dict:
    env = {
        "format": 2,
        "world": {"name": "Testland", "slug": "testland",
                  "aesthetic_seed": "plain stone", "rng_seed": "pin"},
        "start_room": "r-one",
        "flags": ["DOOR-OPEN"],
        "verbs": {
            "pray": {"ui_hint": "Pray", "description": "Pray quietly.",
                     "fail_text": "Nothing answers."},
        },
        "rules": [
            {"on": "pray", "do": [{"kind": "narrate", "text": "A hush."}]},
        ],
        "fuses": {"bell": {"turns": 3, "do": [{"kind": "narrate", "text": "dong"}]}},
        "daemons": {"drip": {"kind": "script", "if": [{"flag": "DOOR-OPEN"}],
                             "do": [{"kind": "narrate", "text": "drip"}]}},
        "scoring": {"ranks": [{"min": 0, "name": "Novice"}]},
        "config": {"carry_capacity": 100},
        "voice": {"register": "dry"},
        "rooms": [
            {"id": "r-one", "slug": "one", "title": "Room One",
             "seed": "a bare room", "description": "The first room.",
             "exits": {"east": "r-two",
                       "west": {"text": "The wall is solid."},
                       "down": {"to": "r-two", "if": [{"flag": "DOOR-OPEN"}],
                                "blocked_text": "The hatch is shut.",
                                "secret": True}}},
            {"id": "r-two", "slug": "two", "title": "Room Two",
             "seed": "a darker room", "dark": True,
             "exits": {"west": "r-one"}},
        ],
        "toons": [
            {"id": "t-hero", "name": "Hero", "slot": 1, "room": "r-one",
             "appearance_seed": "a wanderer", "is_human_controlled": 0},
        ],
        "things": [
            {"id": "o-case", "name": "trophy case", "location": {"room": "r-one"},
             "seed": "a glass case", "fixture": True,
             "properties": {"container": True, "transparent": True,
                            "state": "open", "score_deposits": True},
             "verbs": ["open", "close", "put"]},
            {"id": "o-egg", "name": "jeweled egg", "location": {"in": "o-case"},
             "seed": "a jeweled egg",
             "properties": {"treasure": True, "score_take": 5, "score_case": 5}},
            {"id": "o-coin", "name": "coin", "location": {"toon": "t-hero"},
             "seed": "a worn coin"},
            {"id": "o-ghostly", "name": "ghostly diamond", "location": "offstage",
             "seed": "not yet in the world"},
        ],
    }
    env.update(overrides)
    return env


def load(env, tmp_path) -> Path:
    out = tmp_path / "world.db"
    return bootstrap.load_world("testland", env, out)


# ---- happy path -------------------------------------------------------------


def test_load_and_reopen(tmp_path):
    path = load(minimal_env(), tmp_path)
    db.init_live(path=path, migrations_dir=config.MIGRATIONS_DIR)
    one = objects.get("r-one")
    assert one is not None and one.kind == "room"
    assert one.properties["description_cached"] == "The first room."
    assert objects.get("r-two").properties["dark"] is True
    hero = objects.get("t-hero")
    assert hero.slot == 1 and hero.location_id == "r-one"
    egg = objects.get("o-egg")
    assert egg.location_id == "o-case"  # containment via two-pass insert
    assert objects.get("o-coin").location_id == "t-hero"
    assert objects.get("o-ghostly").location_id is None  # offstage
    row = db.get_conn().execute("SELECT * FROM worlds").fetchone()
    assert row["id"] == "w-testland" and row["starting_room_id"] == "r-one"
    assert row["world_version"] == "1.3"
    # def:* blocks landed in world_state.
    assert worldstate.get("w-testland", "def:verbs")["pray"]["ui_hint"] == "Pray"
    assert worldstate.get("w-testland", "def:flags") == ["DOOR-OPEN"]
    assert worldstate.get("w-testland", "def:fuses")["bell"]["turns"] == 3
    assert worldstate.get("w-testland", "config")["carry_capacity"] == 100
    assert worldstate.get("w-testland", "voice")["register"] == "dry"
    assert worldstate.rng_seed("w-testland") == "pin"
    assert worldstate.rank_for("w-testland", 0) == "Novice"


async def test_loaded_world_verbs_and_rules_execute(tmp_path):
    path = load(minimal_env(), tmp_path)
    db.init_live(path=path, migrations_dir=config.MIGRATIONS_DIR)
    await verbs.execute_command("t-hero", "pray")
    texts = [e.payload.get("text") for e in events.fetch_since(0)
             if e.kind == "narrate"]
    assert "A hush." in texts


async def test_treasure_scoring_hooks(tmp_path):
    path = load(minimal_env(), tmp_path)
    db.init_live(path=path, migrations_dir=config.MIGRATIONS_DIR)
    await verbs.execute_command("t-hero", "take", "o-egg")
    assert worldstate.score("w-testland") == 5  # first-take award
    await verbs.execute_command("t-hero", "put", "o-egg", "o-case")
    assert worldstate.score("w-testland") == 10  # case deposit award
    await verbs.execute_command("t-hero", "take", "o-egg")
    await verbs.execute_command("t-hero", "put", "o-egg", "o-case")
    assert worldstate.score("w-testland") == 10  # once-keys hold


def test_one_way_exit_is_lint_not_error(tmp_path):
    env = minimal_env()
    env["rooms"][1]["exits"] = {}  # r-one -> r-two now one-way
    lints = format2.validate_envelope2(env)
    assert any("one-way exit: r-one -> r-two" in l for l in lints)
    load(env, tmp_path)  # loads fine


def test_secret_exit_hidden_in_snapshot_shape(tmp_path):
    path = load(minimal_env(), tmp_path)
    db.init_live(path=path, migrations_dir=config.MIGRATIONS_DIR)
    from daydream import rooms as rooms_mod

    room = rooms_mod.get_room("r-one")
    hero = objects.get("t-hero")
    vis = verbs.visible_exits(room, hero)
    assert "down" not in vis and vis["west"] is None and vis["east"] == "r-two"
    worldstate.set_flag("w-testland", "DOOR-OPEN", True)
    vis = verbs.visible_exits(rooms_mod.get_room("r-one"), hero)
    assert vis["down"] == "r-two"


# ---- fail-loud validation ------------------------------------------------------


@pytest.mark.parametrize("mutate,fragment", [
    (lambda e: e["rooms"][0]["exits"].update({"north": "r-nowhere"}),
     "unknown room"),
    (lambda e: e["things"].append(
        {"id": "o-x", "name": "x", "location": {"in": "o-nowhere"}}),
     "unknown thing"),
    (lambda e: e["rules"].append(
        {"on": "frob", "do": [{"kind": "narrate", "text": "x"}]}),
     "unknown verb"),
    (lambda e: e["rules"].append(
        {"on": "pray", "if": [{"flag": "NOPE"}],
         "do": [{"kind": "narrate", "text": "x"}]}),
     "undeclared flag"),
    (lambda e: e["rules"].append(
        {"on": "pray", "do": [{"kind": "spawn_room", "room_id": "r-x",
                               "slug": "x", "title": "X", "seed": "s"}]}),
     "not in RULE_KINDS"),
    (lambda e: e["fuses"].update({"bad": {"turns": 0, "do": [
        {"kind": "narrate", "text": "x"}]}}),
     "turns must be an int >= 1"),
    (lambda e: e["daemons"].update({"bad": {"kind": "poltergeist"}}),
     "kind must be one of"),
    (lambda e: e["verbs"].update({"take": {"description": "steal"}}),
     "collides"),
    (lambda e: e.update({"start_room": "r-nowhere"}),
     "start_room"),
    (lambda e: e["rooms"][0]["exits"].update(
        {"up": {"to": "r-two", "iff": []}}),
     "unknown key"),
    (lambda e: e["rooms"][0].update(
        {"enter_if": [{"falg": "DOOR-OPEN"}]}),
     "condition key"),
    (lambda e: e["toons"].append(
        {"id": "t-two", "name": "Two", "slot": 1, "room": "r-one"}),
     "duplicate slot"),
    (lambda e: e["things"].append(
        {"id": "o-egg", "name": "dupe", "location": "offstage"}),
     "duplicate id"),
])
def test_validation_refuses_with_named_error(tmp_path, mutate, fragment):
    env = minimal_env()
    mutate(env)
    with pytest.raises(format2.Format2ValidationError) as exc:
        load(env, tmp_path)
    assert fragment in str(exc.value)
    assert not (tmp_path / "world.db").exists()  # zero writes


def test_v1_envelope_still_routes_to_v1_loader(tmp_path):
    # No "format": 2 -> the old validator (which demands exactly 5 rooms).
    with pytest.raises(bootstrap.BootstrapValidationError):
        bootstrap.load_world("x", {"world": {}, "rooms": [], "toons": [],
                                   "items": [], "skills": []},
                             tmp_path / "v1.db")


def test_prototypes_match_v1_loader():
    assert format2._PROTOTYPES == bootstrap._PROTOTYPES


# ---- assembler -------------------------------------------------------------------


def test_assembler_merges_and_expands_sugar(tmp_path):
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "assemble_world",
        Path(__file__).resolve().parent.parent / "tools" / "assemble_world.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    source = tmp_path / "testworld"
    (source / "regions").mkdir(parents=True)
    (source / "world.json").write_text(json.dumps({
        "format": 2,
        "world": {"name": "T", "slug": "t", "aesthetic_seed": "x"},
        "start_room": "r-a",
    }))
    (source / "regions" / "01-a.json").write_text(json.dumps({
        "rooms": [{"id": "r-a", "slug": "a", "title": "A", "seed": "s",
                   "zork_name": "West of House", "bonus": 10, "exits": {}}],
        "things": [{"id": "o-t", "name": "painting", "location": {"room": "r-a"},
                    "zork_name": "painting",
                    "treasure": {"take": 4, "case": 6}}],
    }))
    (source / "regions" / "02-b.json").write_text(json.dumps({
        "rooms": [{"id": "r-b", "slug": "b", "title": "B", "seed": "s",
                   "exits": {}}],
    }))
    env, oracle = mod.assemble(source)
    assert [r["id"] for r in env["rooms"]] == ["r-a", "r-b"]  # filename order
    room_a = env["rooms"][0]
    assert "zork_name" not in room_a and "bonus" not in room_a
    assert room_a["rules"][0]["do"][0] == {
        "kind": "adjust_score", "delta": 10, "once": "room:r-a"}
    thing = env["things"][0]
    assert thing["properties"] == {
        "treasure": True, "score_take": 4, "score_case": 6}
    assert "treasure" not in thing
    assert oracle["rooms"]["r-a"] == "West of House"
    assert oracle["things"]["o-t"] == "painting"
