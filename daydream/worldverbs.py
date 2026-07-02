"""World-declared verbs: authored verb vocabulary loaded from the world's
`def:verbs` block (platform turn, SPEC 2026-07-02 criterion 3).

A world verb is pure data — there is NO Python handler. It executes only
through the declarative rule engine (`daydream.rules`); when no rule matches,
its authored `fail_text` narrates to the actor. Its effect allowlist is
therefore always `effects.RULE_KINDS`.

Authored shape (worldstate key `def:verbs`, one entry per verb name):

    {"turn": {"ui_hint": "Turn", "description": "...",
              "aliases": ["rotate"], "preps": ["with"],
              "needs_dobj": true, "needs_iobj": true,
              "valid_dobj_kinds": ["thing"], "valid_iobj_kinds": ["thing"],
              "on_bar": false, "needs_text": false, "text_prompt": "",
              "fail_text": "The bolt won't budge.",
              "dobj_default": {...}, "iobj_default": {...}}, ...}

Lookup is per-world (verbs ride the world DB, not the engine): the resolver
in `daydream.verbs` consults engine verbs first, then this module, so a world
can never shadow an engine verb (the format-2 validator refuses the
collision outright). Reads go straight to the worldstate KV — one small-row
read per lookup, no cache to invalidate across `world swap`.
"""

from __future__ import annotations

import logging

from daydream import worldstate
from daydream.skills import effects
from daydream.verbs import VERBS, VerbSpec

logger = logging.getLogger(__name__)

_STR_FIELDS = ("ui_hint", "description", "text_prompt", "fail_text")
_BOOL_FIELDS = ("needs_dobj", "needs_iobj", "on_bar", "needs_text", "free_text")
_LIST_FIELDS = ("aliases", "preps", "valid_dobj_kinds", "valid_iobj_kinds")
_KIND_VALUES = frozenset({"thing", "toon", "room"})


def defs(world_id: str) -> dict:
    d = worldstate.get(world_id, "def:verbs")
    return d if isinstance(d, dict) else {}


def _to_spec(name: str, d: dict) -> VerbSpec:
    aliases = tuple(
        a.strip().lower() for a in d.get("aliases", [])
        if isinstance(a, str) and a.strip()
    )
    preps = tuple(
        p.strip().lower() for p in d.get("preps", [])
        if isinstance(p, str) and p.strip()
    )
    return VerbSpec(
        name=name,
        ui_hint=d.get("ui_hint") or name.capitalize(),
        description=d.get("description") or f"{name} something.",
        needs_dobj=bool(d.get("needs_dobj", False)),
        needs_iobj=bool(d.get("needs_iobj", False)),
        valid_dobj_kinds=frozenset(d.get("valid_dobj_kinds") or []),
        valid_iobj_kinds=frozenset(d.get("valid_iobj_kinds") or []),
        allowed_effects=effects.RULE_KINDS,
        on_bar=bool(d.get("on_bar", False)),
        free_text=bool(d.get("free_text", False)),
        aliases=aliases,
        preps=preps,
        needs_text=bool(d.get("needs_text", False)),
        text_prompt=str(d.get("text_prompt") or ""),
        fail_text=str(d.get("fail_text") or ""),
        dobj_default=d.get("dobj_default") if isinstance(d.get("dobj_default"), dict) else None,
        iobj_default=d.get("iobj_default") if isinstance(d.get("iobj_default"), dict) else None,
        world=True,
    )


def get(world_id: str, name: str) -> VerbSpec | None:
    """Resolve a world verb by canonical name or alias."""
    n = name.strip().lower()
    d = defs(world_id)
    entry = d.get(n)
    if isinstance(entry, dict):
        return _to_spec(n, entry)
    for canonical, spec_dict in d.items():
        if not isinstance(spec_dict, dict):
            continue
        aliases = spec_dict.get("aliases", [])
        if isinstance(aliases, list) and n in [
            str(a).strip().lower() for a in aliases
        ]:
            return _to_spec(canonical, spec_dict)
    return None


def all_specs(world_id: str) -> list[VerbSpec]:
    out = []
    for name, d in defs(world_id).items():
        if isinstance(d, dict):
            out.append(_to_spec(name, d))
    return out


def bar_verbs(world_id: str) -> list[VerbSpec]:
    return [s for s in all_specs(world_id) if s.on_bar]


def vocabulary(world_id: str) -> dict[str, str]:
    """Every recognized world-verb word (canonical names + aliases) mapped to
    its canonical verb name — the parser's fast-path lookup table and the
    word list joined into the LLM grounding prompt."""
    out: dict[str, str] = {}
    for name, d in defs(world_id).items():
        if not isinstance(d, dict):
            continue
        out[name] = name
        for a in d.get("aliases", []):
            if isinstance(a, str) and a.strip():
                out[a.strip().lower()] = name
    return out


# ---- validation (format-2 load path) ---------------------------------------


def validate_verb_defs(verb_defs) -> list[str]:
    """Named errors for an authored `verbs` block (empty = valid). A world
    verb may not collide with an engine verb's name or alias — engine verbs
    win resolution, so the collision would silently dead-letter the authored
    one; refuse at load instead."""
    errors: list[str] = []
    if not isinstance(verb_defs, dict):
        return ["verbs: must be an object of name -> spec"]
    engine_words: set[str] = set()
    for spec in VERBS.values():
        engine_words.add(spec.name)
        engine_words.update(spec.aliases)
    seen_words: dict[str, str] = {}
    for name, d in verb_defs.items():
        where = f"verbs.{name}"
        if not isinstance(name, str) or not name.strip() or name != name.strip().lower():
            errors.append(f"{where}: verb names must be lowercase non-empty strings")
            continue
        if not isinstance(d, dict):
            errors.append(f"{where}: spec must be an object")
            continue
        words = [name] + [
            str(a).strip().lower() for a in d.get("aliases", [])
            if isinstance(a, str) and str(a).strip()
        ]
        for w in words:
            if w in engine_words:
                errors.append(f"{where}: {w!r} collides with an engine verb")
            if w in seen_words and seen_words[w] != name:
                errors.append(
                    f"{where}: {w!r} already claimed by verb {seen_words[w]!r}"
                )
            seen_words[w] = name
        for f in _STR_FIELDS:
            if f in d and not isinstance(d[f], str):
                errors.append(f"{where}.{f}: must be a string")
        for f in _BOOL_FIELDS:
            if f in d and not isinstance(d[f], bool):
                errors.append(f"{where}.{f}: must be a boolean")
        for f in _LIST_FIELDS:
            if f in d and not (
                isinstance(d[f], list) and all(isinstance(x, str) for x in d[f])
            ):
                errors.append(f"{where}.{f}: must be a list of strings")
        for f in ("valid_dobj_kinds", "valid_iobj_kinds"):
            for k in d.get(f) or []:
                if k not in _KIND_VALUES:
                    errors.append(f"{where}.{f}: unknown kind {k!r}")
        for f in ("dobj_default", "iobj_default"):
            if f in d and not isinstance(d[f], dict):
                errors.append(f"{where}.{f}: must be an object filter")
        if d.get("needs_iobj") and not d.get("preps"):
            errors.append(f"{where}: needs_iobj requires at least one prep")
        unknown = set(d) - set(
            _STR_FIELDS + _BOOL_FIELDS + _LIST_FIELDS
            + ("dobj_default", "iobj_default")
        )
        if unknown:
            errors.append(f"{where}: unknown field(s) {sorted(unknown)}")
    return errors
