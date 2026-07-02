"""The declarative rule engine + world-declared verbs (Zork turn, SPEC
2026-07-02 criterion 3): dispatch order, fallthrough, sigil resolution,
allowlist rejection, the closed condition vocabulary, and the fail-loud
validators the format-2 loader calls."""

from pathlib import Path

import pytest

from daydream import config, db, events, objects, rules, verbs, worldstate, worldverbs

pytestmark = pytest.mark.tier_short

WORLD = "w-bunny"
ACTOR = "t-wren"
ROOM = "r-meadow"


@pytest.fixture(autouse=True)
def fresh_db(tmp_path: Path):
    db.close_db()
    events.reset_subscribers()
    db.init_live(path=tmp_path / "test.db", migrations_dir=config.MIGRATIONS_DIR)
    yield
    db.close_db()
    events.reset_subscribers()


def narrates() -> list[str]:
    return [
        e.payload.get("text", "")
        for e in events.fetch_since(0)
        if e.kind == "narrate"
    ]


def install_turn_verb(fail_text="The dream doesn't turn that way."):
    worldstate.set(WORLD, "def:verbs", {
        "turn": {
            "ui_hint": "Turn", "description": "Turn something, maybe with a tool.",
            "aliases": ["rotate"], "preps": ["with"],
            "needs_dobj": True, "needs_iobj": True,
            "valid_dobj_kinds": ["thing"], "valid_iobj_kinds": ["thing"],
            "fail_text": fail_text,
        },
        "pray": {
            "ui_hint": "Pray", "description": "Offer a quiet prayer.",
            "fail_text": "Nothing answers.",
        },
    })


def spawn_bolt_and_wrench():
    bolt = objects.spawn(
        WORLD, "thing", "bolt", ROOM,
        properties={
            "verbs": ["turn"],
            "rules": [
                {"on": "turn",
                 "if": [{"iobj": "o-wrench"}, {"flag": "GATE-UNLOCKED"}],
                 "do": [{"kind": "set_flag", "name": "GATES-OPEN", "value": True},
                        {"kind": "narrate", "text": "The sluice gates open."}]},
                {"on": "turn", "if": [{"iobj": "o-wrench"}],
                 "do": [{"kind": "narrate",
                         "text": "The bolt won't turn with your best effort.",
                         "to": "@actor"}]},
                {"on": "turn",
                 "do": [{"kind": "narrate", "text": "The bolt won't turn using that.",
                         "to": "@actor"}]},
            ],
        },
        object_id="o-bolt",
    )
    wrench = objects.spawn(WORLD, "thing", "wrench", ACTOR, object_id="o-wrench")
    spoon = objects.spawn(WORLD, "thing", "spoon", ACTOR, object_id="o-spoon")
    return bolt, wrench, spoon


# ---- world verbs + ordered first-match (the dam-bolt example) --------------


async def test_world_verb_rule_fires_with_conditions_met():
    install_turn_verb()
    spawn_bolt_and_wrench()
    worldstate.set_flag(WORLD, "GATE-UNLOCKED", True)
    await verbs.execute_command(ACTOR, "turn", "o-bolt", "o-wrench")
    assert worldstate.get_flag(WORLD, "GATES-OPEN") is True
    assert "The sluice gates open." in narrates()


async def test_fallthrough_wrong_flag_hits_second_rule():
    install_turn_verb()
    spawn_bolt_and_wrench()  # GATE-UNLOCKED stays false
    await verbs.execute_command(ACTOR, "turn", "o-bolt", "o-wrench")
    assert worldstate.get_flag(WORLD, "GATES-OPEN") is False
    assert "The bolt won't turn with your best effort." in narrates()


async def test_fallthrough_wrong_tool_hits_last_rule():
    install_turn_verb()
    spawn_bolt_and_wrench()
    await verbs.execute_command(ACTOR, "turn", "o-bolt", "o-spoon")
    assert "The bolt won't turn using that." in narrates()
    assert worldstate.get_flag(WORLD, "GATES-OPEN") is False


async def test_world_verb_alias_resolves():
    install_turn_verb()
    spawn_bolt_and_wrench()
    worldstate.set_flag(WORLD, "GATE-UNLOCKED", True)
    await verbs.execute_command(ACTOR, "rotate", "o-bolt", "o-wrench")
    assert worldstate.get_flag(WORLD, "GATES-OPEN") is True


async def test_world_verb_fail_text_when_no_rule_matches():
    install_turn_verb()
    await verbs.execute_command(ACTOR, "pray")
    assert "Nothing answers." in narrates()


async def test_world_verb_missing_iobj_asks():
    install_turn_verb()
    spawn_bolt_and_wrench()
    await verbs.execute_command(ACTOR, "turn", "o-bolt", None)
    assert any("what" in t.lower() for t in narrates())
    assert worldstate.get_flag(WORLD, "GATES-OPEN") is False


def test_bar_verbs_merges_world_bar_verbs():
    worldstate.set(WORLD, "def:verbs", {
        "dig": {"ui_hint": "Dig", "description": "Dig.", "on_bar": True},
    })
    names = [v.name for v in verbs.bar_verbs(WORLD)]
    assert "dig" in names and "examine" in names
    assert names.index("examine") < names.index("dig")  # engine verbs first


# ---- dispatch order + as-role + stop ---------------------------------------


async def test_dobj_rule_beats_room_and_world_rules():
    install_turn_verb()
    objects.spawn(WORLD, "thing", "crank", ROOM,
                  properties={"verbs": ["turn"],
                              "rules": [{"on": "turn",
                                         "do": [{"kind": "narrate", "text": "dobj rule"}]}]},
                  object_id="o-crank")
    objects.set_property(ROOM, "rules",
                         [{"on": "turn", "do": [{"kind": "narrate", "text": "room rule"}]}])
    worldstate.set(WORLD, "def:rules",
                   [{"on": "turn", "do": [{"kind": "narrate", "text": "world rule"}]}])
    await verbs.execute_command(ACTOR, "turn", "o-crank", "o-crank")
    texts = narrates()
    assert "dobj rule" in texts and "room rule" not in texts and "world rule" not in texts


async def test_room_rule_fires_when_no_dobj_rule():
    install_turn_verb()
    objects.set_property(ROOM, "rules",
                         [{"on": "pray", "do": [{"kind": "narrate", "text": "room hears you"}]}])
    worldstate.set(WORLD, "def:rules",
                   [{"on": "pray", "do": [{"kind": "narrate", "text": "world hears you"}]}])
    await verbs.execute_command(ACTOR, "pray")
    texts = narrates()
    assert "room hears you" in texts and "world hears you" not in texts


async def test_world_rule_is_last_resort():
    install_turn_verb()
    worldstate.set(WORLD, "def:rules",
                   [{"on": "pray", "do": [{"kind": "narrate", "text": "world hears you"}]}])
    await verbs.execute_command(ACTOR, "pray")
    assert "world hears you" in narrates()
    assert "Nothing answers." not in narrates()  # rule fired; fail_text skipped


async def test_iobj_rules_fire_only_as_iobj():
    install_turn_verb()
    spawn_bolt_and_wrench()
    # A rule ON the wrench for when it is the TOOL of a turn.
    objects.set_property("o-wrench", "rules", [
        {"on": "turn", "as": "iobj",
         "do": [{"kind": "narrate", "text": "the wrench bites"}]},
    ])
    # Plain bolt with no rules: strip the bolt's own rules so iobj scan wins.
    objects.set_property("o-bolt", "rules", [])
    await verbs.execute_command(ACTOR, "turn", "o-bolt", "o-wrench")
    assert "the wrench bites" in narrates()


async def test_stop_false_continues_to_next_holder():
    install_turn_verb()
    objects.set_property(ROOM, "rules", [
        {"on": "pray", "stop": False,
         "do": [{"kind": "narrate", "text": "a hush falls"}]},
    ])
    worldstate.set(WORLD, "def:rules",
                   [{"on": "pray", "do": [{"kind": "narrate", "text": "then an answer"}]}])
    await verbs.execute_command(ACTOR, "pray")
    texts = narrates()
    assert "a hush falls" in texts and "then an answer" in texts


# ---- rules shadow legacy engine handlers ------------------------------------


async def test_rule_shadows_engine_open_handler():
    box = objects.spawn(
        WORLD, "thing", "strange box", ROOM,
        properties={"verbs": ["open"], "state": "closed",
                    "rules": [{"on": "open",
                               "do": [{"kind": "narrate", "text": "It refuses, politely."}]}]},
        object_id="o-strangebox",
    )
    await verbs.execute_command(ACTOR, "open", box.id)
    assert "It refuses, politely." in narrates()
    # The legacy engine open did NOT run: state unchanged.
    assert objects.get(box.id).properties["state"] == "closed"


async def test_no_rules_means_legacy_engine_behavior():
    box = objects.spawn(WORLD, "thing", "plain box", ROOM,
                        properties={"verbs": ["open"], "state": "closed"},
                        object_id="o-plainbox")
    await verbs.execute_command(ACTOR, "open", box.id)
    assert objects.get(box.id).properties["state"] == "open"


# ---- sigils + allowlist ------------------------------------------------------


async def test_sigils_resolve_to_concrete_ids():
    install_turn_verb()
    orb = objects.spawn(WORLD, "thing", "orb", ROOM,
                        properties={"verbs": ["turn"],
                                    "rules": [{"on": "turn",
                                               "do": [{"kind": "move_object",
                                                       "object_id": "@self",
                                                       "dest_id": "@actor"},
                                                      {"kind": "narrate",
                                                       "text": "It leaps to your hand.",
                                                       "to": "@actor"}]}]},
                        object_id="o-orb")
    await verbs.execute_command(ACTOR, "turn", orb.id, orb.id)
    assert objects.get(orb.id).location_id == ACTOR
    private = [e for e in events.fetch_since(0)
               if e.kind == "narrate" and e.recipient_id == ACTOR]
    assert any("leaps to your hand" in e.payload["text"] for e in private)


async def test_rule_cannot_emit_world_shaping_kinds():
    install_turn_verb()
    objects.set_property(ROOM, "rules", [
        {"on": "pray",
         "do": [{"kind": "spawn_room", "room_id": "r-evil", "slug": "evil",
                 "title": "Evil", "seed": "x"}]},
    ])
    await verbs.execute_command(ACTOR, "pray")
    assert objects.get("r-evil") is None  # rejected like an unknown kind


# ---- condition vocabulary ----------------------------------------------------


def ctx_for(actor_id=ACTOR, dobj=None, iobj=None, holder=None):
    actor = objects.get(actor_id)
    return rules._build_ctx(actor, dobj, iobj, ROOM, holder, "test")


def test_prop_condition_ops():
    objects.set_property("i-lantern", "weight", 7)
    lantern = objects.get("i-lantern")
    ctx = ctx_for(dobj=lantern)
    assert rules.conditions_hold(
        [{"prop": "weight", "of": "@dobj", "gte": 7}], ctx)
    assert not rules.conditions_hold(
        [{"prop": "weight", "of": "@dobj", "lt": 7}], ctx)
    assert rules.conditions_hold(
        [{"prop": "weight", "of": "@dobj", "in": [5, 7, 9]}], ctx)
    # No op = truthy check; missing prop = falsy.
    assert rules.conditions_hold([{"prop": "weight", "of": "@dobj"}], ctx)
    assert not rules.conditions_hold([{"prop": "absent", "of": "@dobj"}], ctx)


def test_flag_counter_score_conditions():
    ctx = ctx_for()
    worldstate.set_flag(WORLD, "LOW-TIDE", True)
    assert rules.conditions_hold([{"flag": "LOW-TIDE"}], ctx)
    assert rules.conditions_hold([{"flag": "OTHER", "eq": False}], ctx)
    worldstate.set_counter(WORLD, "digs", 3)
    assert rules.conditions_hold([{"counter": "digs", "eq": 3}], ctx)
    worldstate.adjust_score(WORLD, 350)
    assert rules.conditions_hold([{"score": {"gte": 350}}], ctx)


def test_carry_conditions():
    ctx = ctx_for()
    assert rules.conditions_hold([{"empty_handed": True}], ctx)
    sword = objects.spawn(WORLD, "thing", "sword", ACTOR,
                          properties={"weapon": True}, object_id="o-sword")
    assert rules.conditions_hold([{"carried": "o-sword"}], ctx)
    assert not rules.conditions_hold([{"empty_handed": True}], ctx)
    assert rules.conditions_hold(
        [{"carried_filter": {"key": "weapon", "eq": True}}], ctx)
    assert not rules.conditions_hold(
        [{"carried_filter": {"key": "flame", "eq": True}}], ctx)
    assert rules.conditions_hold([{"only_carrying": ["o-sword"]}], ctx)
    assert rules.conditions_hold([{"carrying_count": {"lte": 2}}], ctx)
    assert not rules.conditions_hold([{"carrying_count": {"gt": 1}}], ctx)
    assert sword.location_id == ACTOR


def test_place_conditions():
    ctx = ctx_for()
    assert rules.conditions_hold([{"in": ROOM}], ctx)
    assert not rules.conditions_hold([{"in": "r-forge"}], ctx)
    assert rules.conditions_hold([{"present": "i-lantern"}], ctx)  # on the ground
    assert not rules.conditions_hold([{"present": "t-rook"}], ctx)  # elsewhere


def test_contains_condition():
    basket = objects.spawn(WORLD, "thing", "basket", ROOM, object_id="o-basket")
    objects.spawn(WORLD, "thing", "pebble", basket.id, object_id="o-pebble")
    ctx = ctx_for(holder=objects.get("o-basket"))
    assert rules.conditions_hold([{"contains": "o-pebble"}], ctx)
    assert not rules.conditions_hold([{"contains": "i-lantern"}], ctx)


def test_in_vehicle_condition():
    boat = objects.spawn(WORLD, "thing", "boat", ROOM,
                         properties={"vehicle": True}, object_id="o-boat")
    ctx = ctx_for()
    assert rules.conditions_hold([{"in_vehicle": False}], ctx)
    objects.move(ACTOR, boat.id)
    ctx = ctx_for()
    assert rules.conditions_hold([{"in_vehicle": True}], ctx)
    assert rules.conditions_hold([{"in_vehicle": "o-boat"}], ctx)
    assert not rules.conditions_hold([{"in_vehicle": "o-other"}], ctx)


def test_chance_condition_is_seeded_deterministic():
    worldstate.set(WORLD, "rng_seed", "pin")
    ctx = ctx_for()
    roll = worldstate.rng(WORLD, "test").random()
    assert rules.conditions_hold([{"chance": roll + 0.001}], ctx)
    assert not rules.conditions_hold([{"chance": roll - 0.001}], ctx)


def test_unknown_condition_key_is_false():
    ctx = ctx_for()
    assert not rules.conditions_hold([{"falg": "TYPO"}], ctx)


def test_conditions_and_together():
    ctx = ctx_for()
    worldstate.set_flag(WORLD, "A", True)
    assert rules.conditions_hold([{"flag": "A"}, {"in": ROOM}], ctx)
    assert not rules.conditions_hold([{"flag": "A"}, {"in": "r-forge"}], ctx)


# ---- validators ---------------------------------------------------------------

KNOWN = dict(
    known_verbs={"turn", "pray"},
    known_flags={"GATES-OPEN"},
    known_ids={"o-bolt", "o-wrench", "r-dam"},
    known_fuses={"bell"},
    known_daemons={"river"},
)


def test_validate_rules_accepts_the_worked_example():
    rule_list = [
        {"on": "turn",
         "if": [{"iobj": "o-wrench"}, {"flag": "GATES-OPEN", "eq": False}],
         "do": [{"kind": "set_flag", "name": "GATES-OPEN", "value": True},
                {"kind": "narrate", "text": "The sluice gates open."},
                {"kind": "start_daemon", "name": "river"}]},
        {"on": "turn", "do": [{"kind": "narrate", "text": "No.", "to": "@actor"}]},
    ]
    assert rules.validate_rules(rule_list, source="o-bolt", **KNOWN) == []


@pytest.mark.parametrize("rule,fragment", [
    ({"on": "frob", "do": [{"kind": "narrate", "text": "x"}]}, "unknown verb"),
    ({"on": "turn", "if": [{"falg": "GATES-OPEN"}],
      "do": [{"kind": "narrate", "text": "x"}]}, "condition key"),
    ({"on": "turn", "if": [{"flag": "NOPE"}],
      "do": [{"kind": "narrate", "text": "x"}]}, "undeclared flag"),
    ({"on": "turn", "do": [{"kind": "explode"}]}, "not in RULE_KINDS"),
    ({"on": "turn", "do": [{"kind": "spawn_room", "room_id": "r-x", "slug": "x",
                            "title": "X", "seed": "s"}]}, "not in RULE_KINDS"),
    ({"on": "turn", "do": [{"kind": "move_object", "object_id": "o-ghost",
                            "dest_id": "@actor"}]}, "dangling reference"),
    ({"on": "turn", "do": [{"kind": "start_fuse", "name": "nope"}]},
     "undeclared fuse"),
    ({"on": "turn", "do": [{"kind": "start_daemon", "name": "nope"}]},
     "undeclared daemon"),
    ({"on": "turn", "as": "subject", "do": [{"kind": "narrate", "text": "x"}]},
     "'as' must be"),
    ({"on": "turn", "do": []}, "non-empty"),
    ({"on": "turn", "do": [{"kind": "narrate", "text": "x"}], "extra": 1},
     "unknown rule key"),
    ({"on": "turn", "if": [{"flag": "GATES-OPEN", "gte": 3}],
      "do": [{"kind": "narrate", "text": "x"}]}, "unknown condition key"),
])
def test_validate_rules_names_each_failure(rule, fragment):
    errors = rules.validate_rules([rule], source="t", **KNOWN)
    assert errors, f"expected an error for {rule}"
    assert any(fragment in e for e in errors), f"{fragment!r} not in {errors}"


def test_validate_verb_defs_ok_and_collisions():
    ok = {"turn": {"ui_hint": "Turn", "description": "d", "preps": ["with"],
                   "needs_dobj": True, "needs_iobj": True,
                   "valid_dobj_kinds": ["thing"], "valid_iobj_kinds": ["thing"]}}
    assert worldverbs.validate_verb_defs(ok) == []
    collide = {"take": {"description": "steal"}}
    assert any("collides" in e for e in worldverbs.validate_verb_defs(collide))
    alias_collide = {"douse": {"description": "d", "aliases": ["get"]}}
    assert any("collides" in e for e in worldverbs.validate_verb_defs(alias_collide))
    bad_kind = {"zap": {"description": "d", "valid_dobj_kinds": ["monster"]}}
    assert any("unknown kind" in e for e in worldverbs.validate_verb_defs(bad_kind))
    missing_prep = {"tie": {"description": "d", "needs_iobj": True}}
    assert any("requires at least one prep" in e
               for e in worldverbs.validate_verb_defs(missing_prep))
    unknown_field = {"dig": {"description": "d", "power": 9}}
    assert any("unknown field" in e for e in worldverbs.validate_verb_defs(unknown_field))
