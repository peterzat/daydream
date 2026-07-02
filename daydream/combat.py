"""Seeded, outcome-faithful combat (platform turn, SPEC 2026-07-02 criterion 8;
fidelity relaxation R3: outcomes match the original, blow-by-blow sub-states
don't ship).

All villain parameters are authored world data on the toon's
`properties.combat` block:

    {"strength": 2,                    # hits to kill
     "weak_to": "o-sword",             # the correct weapon's object id
     "unkillable": false,
     "refuse_text": "...",             # unkillable: how combat is refused
     "hit_texts": [...], "miss_texts": [...],       # player's swings
     "death_text": "...",
     "counter_kill_chance": 0.1,       # villain's swing back (kill_actor)
     "counter_texts": [...],           # villain misses / grazes
     "on_death": [effects]}            # hoard reveal etc (RULE_KINDS)

Mechanics, deterministic under the world rng_seed:

- The CORRECT weapon (weak_to) lands every swing — the ZIL quirk where the
  right weapon decrements strength even on a miss roll, which is what makes
  the canonical fights near-deterministic under a pinned seed.
- Any other carried thing connects on a seeded roll (0.4).
- Remaining strength persists as `properties.combat_strength`.
- At zero: the authored death text, the authored on_death effects, then the
  villain is destroyed — its carried hoard drops to the room by the
  destroy_object contract.
- A survivor swings back: a seeded roll under counter_kill_chance applies
  kill_actor (the authored death policy); otherwise an authored counter
  line narrates.
- An unkillable villain refuses combat entirely (the unkillable villain wants a magic
  word or a meal, not a sword)."""

from __future__ import annotations

import logging

from daydream import objects, worldstate
from daydream.skills import effects

logger = logging.getLogger(__name__)

WRONG_WEAPON_HIT_CHANCE = 0.4


def combat_block(villain: objects.Object) -> dict | None:
    block = villain.properties.get("combat")
    return block if isinstance(block, dict) else None


def _texts(block: dict, key: str, fallback: str) -> list[str]:
    v = block.get(key)
    if isinstance(v, list) and all(isinstance(t, str) for t in v) and v:
        return v
    return [fallback]


def _pick(rng, options: list[str]) -> str:
    return options[rng.randrange(len(options))]


async def execute_attack(actor, room_id, dobj, iobj, args, spec) -> None:
    """The `attack` engine verb: attack DOBJ (a toon) with IOBJ (a carried
    thing). Deterministic given the world seed + turn; no LLM."""
    world_id = actor.world_id
    block = combat_block(dobj)

    def narrate(text: str, private: bool = False) -> None:
        eff = {"kind": "narrate", "text": text}
        if private:
            eff["to"] = "@actor"
        effects.dispatch_effects([eff], actor_id=actor.id, room_id=room_id,
                                 world_id=world_id, allowed=spec.allowed_effects)

    if block is None:
        narrate(f"{dobj.name} doesn't want to fight.", private=True)
        return
    if block.get("unkillable"):
        refuse = block.get("refuse_text")
        narrate(refuse if isinstance(refuse, str) and refuse.strip()
                else f"Your blows glance off {dobj.name} without notice.")
        return
    if iobj.location_id != actor.id:
        narrate(f"You aren't carrying the {iobj.name}.", private=True)
        return

    rng = worldstate.rng(world_id, f"combat:{dobj.id}")
    strength = dobj.properties.get("combat_strength")
    if not isinstance(strength, int):
        strength = block.get("strength")
        if not isinstance(strength, int) or strength < 1:
            strength = 1

    correct_weapon = iobj.id == block.get("weak_to")
    lands = correct_weapon or rng.random() < WRONG_WEAPON_HIT_CHANCE
    if lands:
        strength -= 1
        objects.set_property(dobj.id, "combat_strength", strength)
        if strength <= 0:
            death = block.get("death_text")
            narrate(death if isinstance(death, str) and death.strip()
                    else f"{dobj.name} falls and is still.")
            on_death = block.get("on_death")
            if isinstance(on_death, list) and on_death:
                from daydream import rules

                ctx = rules._build_ctx(actor, dobj, iobj, room_id, dobj,
                                       f"combat-death:{dobj.id}")
                effects.dispatch_effects(
                    rules.resolve_sigils(on_death, ctx),
                    actor_id=actor.id, room_id=room_id, world_id=world_id,
                    allowed=effects.RULE_KINDS,
                )
            # The body goes; anything it carried (the hoard, stolen loot)
            # drops to the room by the destroy contract.
            effects.dispatch_effects(
                [{"kind": "destroy_object", "object_id": dobj.id}],
                actor_id=actor.id, room_id=room_id, world_id=world_id,
                allowed=spec.allowed_effects,
            )
            return
        narrate(_pick(rng, _texts(block, "hit_texts",
                                  f"Your blow staggers {dobj.name}.")))
    else:
        narrate(_pick(rng, _texts(block, "miss_texts",
                                  f"You miss {dobj.name}.")))

    # The survivor swings back.
    counter_chance = block.get("counter_kill_chance")
    if isinstance(counter_chance, (int, float)) and counter_chance > 0 \
            and rng.random() < float(counter_chance):
        effects.dispatch_effects(
            [{"kind": "kill_actor"}],
            actor_id=actor.id, room_id=room_id, world_id=world_id,
            allowed=spec.allowed_effects,
        )
        return
    narrate(_pick(rng, _texts(block, "counter_texts",
                              f"{dobj.name} swings back and misses.")))
