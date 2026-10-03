"""Instances (docs/INSTANCES.md): which game this process serves, and its
words.

An instance is a complete data dir (its world, its accounts, its art, its
backups); `instance.json` inside it names it and carries the words that
differ between games: the place, the door's lede and plate image, the
link-preview card, the operator's title, the invite blurb, and the world envelope `world reset`
loads. Every key is optional and defaults to The Village of Lost Hours'
words, so a data dir with no file (dev, the tests, prod before `instance
migrate`) reads exactly as before. The words are data, never engine
literals (tests/test_no_world_literals.py).

`python -m daydream.instance envelope` prints the envelope for bin/game."""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

from daydream import config

FILE = "instance.json"
NAME_RE = config.INSTANCE_NAME
DEFAULTS: dict[str, str] = {
    "name": "",
    "title": "The Village of Lost Hours",
    "place": "the village",
    "lede": "A small storybook village, kept for friends.",
    "door_image": "assets/door-village.png",
    # A link's preview image (og:image; tools/make_link_card.py). An instance
    # that names its own door and no card shows its door painting instead.
    "card_image": "assets/card-village.jpg",
    "operator": "",  # empty: DAYDREAM_OPERATOR_NAME, then the generic default
    "envelope": "worlds/lost-hours.json",
    "invite_blurb": "a small storybook village I keep for friends",
}
_SHAPES = {
    "name": NAME_RE,
    "door_image": re.compile(r"^assets/[a-z0-9_-]+\.(?:png|jpg|webp)$"),
    "card_image": re.compile(r"^assets/[a-z0-9_-]+\.(?:png|jpg)$"),
    "envelope": re.compile(r"^worlds/[a-z0-9_-]+\.json$"),
}
MAX_WORDS = 200


class InstanceError(ValueError):
    pass


_cache: dict[str, dict[str, str]] = {}


def path(data_dir: Path | None = None) -> Path:
    return (data_dir or config.data_dir()) / FILE


def validate(raw: object) -> dict[str, str]:
    """The instance's words, defaults filled in. Raises InstanceError on a
    wrong type, an unknown key, or a value outside its shape (a door image or
    an envelope that could point anywhere is refused)."""
    if not isinstance(raw, dict):
        raise InstanceError(f"{FILE} must be a JSON object")
    unknown = sorted(set(raw) - set(DEFAULTS))
    if unknown:
        raise InstanceError(f"{FILE}: unknown key(s) {', '.join(unknown)}")
    words = dict(DEFAULTS)
    for key, value in raw.items():
        if not isinstance(value, str):
            raise InstanceError(f"{FILE}: {key} must be a string")
        value = value.strip()
        if len(value) > MAX_WORDS or not value.isprintable():
            raise InstanceError(f"{FILE}: {key} must be printable and at most {MAX_WORDS} chars")
        shape = _SHAPES.get(key)
        if shape is not None and value and not shape.match(value):
            raise InstanceError(f"{FILE}: {key} {value!r} is not an allowed value")
        if value or key in ("name", "operator"):
            words[key] = value
    # Decide on the validated (stripped) values: a door the file set, and no
    # card it set, previews with the door, but only when the door has the
    # card's shape (png/jpg); otherwise the default card stays.
    set_door = bool(raw.get("door_image", "").strip())
    set_card = bool(raw.get("card_image", "").strip())
    if set_door and not set_card and _SHAPES["card_image"].match(words["door_image"]):
        words["card_image"] = words["door_image"]
    return words


def load(data_dir: Path | None = None) -> dict[str, str]:
    """This data dir's words (cached per dir; a running server reads its file
    once, and `instance` verbs write it with the service stopped)."""
    d = data_dir or config.data_dir()
    key = str(d)
    if key not in _cache:
        p = d / FILE
        words = validate(json.loads(p.read_text())) if p.exists() else dict(DEFAULTS)
        if d.parent.name == "instances" and NAME_RE.match(d.name):
            # An instance's name is its directory's (the cookie, /status/build
            # and the swap's served check all read it): a file may omit it,
            # never contradict it (codereview WARN 2026-09-28e).
            if words["name"] not in ("", d.name):
                raise InstanceError(f"{p}: name {words['name']!r} is not its directory's "
                                    f"({d.name!r})")
            words["name"] = d.name
        _cache[key] = words
    return _cache[key]


def forget() -> None:
    """Drop the cache (tests, and a tool that writes instance.json)."""
    _cache.clear()


def name(data_dir: Path | None = None) -> str:
    """The instance's name, or "" for a data dir with no instance.json."""
    return load(data_dir)["name"]


def place(data_dir: Path | None = None, *, capital: bool = False) -> str:
    p = load(data_dir)["place"]
    return p[:1].upper() + p[1:] if capital else p


# The door's icons by link rel, the same for every instance (web/door.html
# links them).
ICONS = {"icon": "assets/icon-32.png", "apple-touch-icon": "assets/icon-180.png"}


def preview(data_dir: Path | None = None) -> dict[str, str]:
    """What a shared link's preview says (og:title, og:description, the card
    and its alt text): the door's page fills it in, and the keepsakes sync
    carries it to the edge so the asleep page says the same."""
    words = load(data_dir)
    return {"title": words["title"],
            "invite_title": f"An invitation to {words['title']}",
            "lede": words["lede"],
            "card": words["card_image"],
            "card_alt": f"A watercolour of {words['place']}"}


# ---- the box's instances (run as the service user by `bin/game prod instance`) ----

# What stays in the box's data dir when a flat layout becomes instances: the
# GPU lock every process shares, the service user's HOME dirs, and the
# instances themselves. Everything else is the one instance it held.
BOX_ENTRIES = {"gpu.lock", ".local", ".cache", ".config", "instances", "active"}


def instances_root() -> Path:
    return config.data_root() / "instances"


def attached() -> str | None:
    """The attached instance's name (the `active` link), or None."""
    link = config.data_root() / "active"
    if not link.is_symlink():
        return None
    return Path(link.readlink()).name


def listing() -> list[dict]:
    out = []
    root = instances_root()
    for d in sorted(root.iterdir()) if root.is_dir() else []:
        if not d.is_dir() or not NAME_RE.match(d.name):
            continue
        words = load(d)
        out.append({"name": d.name, "title": words["title"], "place": words["place"],
                    "attached": d.name == attached(),
                    "world": (d / f"worlds-{config.env()}" / "live.db").exists(),
                    "accounts": (d / f"accounts-{config.env()}.db").exists()})
    return out


def create(name: str, words: dict) -> Path:
    """A new instance dir with its instance.json (the world is loaded by the
    caller, `bin/game world load`, with DAYDREAM_DATA_DIR pointing here)."""
    if not NAME_RE.match(name):
        raise InstanceError(f"{name!r} is not an instance name")
    validate({**words, "name": name})
    d = instances_root() / name
    d.mkdir(parents=True, exist_ok=False)
    (d / FILE).write_text(json.dumps({**words, "name": name}, indent=2, ensure_ascii=False) + "\n")
    return d


def discard(name: str) -> None:
    """Remove an instance that holds nothing yet (a `create` whose world did
    not load), so a retry starts clean. Refuses the attached instance and
    any dir that holds a world or accounts."""
    d = instances_root() / name
    if not NAME_RE.match(name) or d.is_symlink() or not d.is_dir():
        raise InstanceError(f"no instance {name!r}")
    if name == attached():
        raise InstanceError(f"{name} is attached")
    held = sorted(p.name for p in (*d.glob("worlds-*/live.db"), *d.glob("accounts-*.db")))
    if held:
        raise InstanceError(f"{name} holds {', '.join(held)}; not discarded")
    shutil.rmtree(d)


def attach(name: str) -> None:
    """Point `active` at an instance, atomically (a new link renamed over the
    old). The service must be stopped: a running server keeps the instance it
    resolved at boot, and a swap under it would split it."""
    target = instances_root() / name
    if not NAME_RE.match(name) or not target.is_dir():
        raise InstanceError(f"no instance {name!r}")
    link = config.data_root() / "active"
    tmp = config.data_root() / ".active.new"
    if tmp.is_symlink() or tmp.exists():
        tmp.unlink()
    tmp.symlink_to(Path("instances") / name)
    tmp.replace(link)


def migrate(name: str) -> list[str]:
    """The one-time move of a flat data dir into `instances/<name>` and the
    `active` link to it (service stopped, a backup taken first by the
    caller). Refuses a box that already has instances."""
    root = config.data_root()
    if (root / "instances").exists() or (root / "active").is_symlink():
        raise InstanceError("this data dir already has instances")
    if not NAME_RE.match(name):
        raise InstanceError(f"{name!r} is not an instance name")
    # A flat dir's own instance.json moves with it and takes the new name; a
    # bad one refuses here, before anything moves.
    raw = json.loads((root / FILE).read_text()) if (root / FILE).exists() else {}
    validate(raw)
    d = root / "instances" / name
    d.mkdir(parents=True)
    moved = []
    for entry in sorted(root.iterdir()):
        if entry.name in BOX_ENTRIES:
            continue
        entry.rename(d / entry.name)
        moved.append(entry.name)
    (d / FILE).write_text(json.dumps({**raw, "name": name}, indent=2, ensure_ascii=False) + "\n")
    attach(name)
    return moved


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        if args == ["envelope"]:
            print(load()["envelope"])
        elif args == ["show"]:
            print(json.dumps(load(), indent=2, ensure_ascii=False))
        elif args == ["flag-words"]:
            words = load()
            print(json.dumps({"place": words["place"], "title": words["title"],
                              "operator": config.operator_name(),
                              "cookie": config.cookie_name()}, ensure_ascii=False))
        elif args == ["list"]:
            print(json.dumps(listing(), ensure_ascii=False))
        elif len(args) == 3 and args[0] == "create":
            print(create(args[1], json.loads(args[2])))
        elif len(args) == 2 and args[0] == "attach":
            attach(args[1])
            print(f"attached {args[1]}")
        elif len(args) == 2 and args[0] == "discard":
            discard(args[1])
            print(f"discarded {args[1]}")
        elif len(args) == 2 and args[0] == "migrate":
            moved = migrate(args[1])
            print(f"migrated into instances/{args[1]}: {', '.join(moved) or 'nothing'}")
        else:
            print("usage: python -m daydream.instance envelope|show|flag-words|list|"
                  "create NAME WORDS_JSON|attach NAME|discard NAME|migrate NAME",
                  file=sys.stderr)
            return 2
    except (InstanceError, ValueError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
