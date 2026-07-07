"""Drive the real Zork I headless as a differential ground truth (SPEC
2026-07-02 criterion 14).

`Oracle` wraps `dfrotz -p -m -w 200 -s <seed> <story>` behind pexpect:
plain output, no MORE prompts, wide enough that no game line wraps (dfrotz
2.44 silently falls back to a tiny width on out-of-range values like 9999,
so the width is a real 200), deterministic RNG. The pty echo is disabled
and the status line dfrotz reprints each turn (`<room>  Score: N  Moves: M`)
is filtered out of every reply, so probes parse game text only. `send()`
posts one command and returns the reply text (everything up to the next `>`
prompt). State probes parse the game's own reporting:

    room()       the current room name (first line of a `look`)
    score()      the integer score (from `score`)
    inventory()  carried item names, containers flattened (from `i`)
    state()      all three, bracketed by Z-machine save/restore

The raw probes cost in-game turns in the real engine (LOOK ticks the clock
in Zork I exactly as it does on our side), which perturbs fuses (the altar
candles burn down) and the thief's wanderings. `state()` removes the cost
entirely: it saves the Z-machine, probes, and restores, so the clock,
fuses, thief, and RNG stream are exactly as if the probe never happened.
Checkpoint comparisons should always use `state()`.

Combat is compared on OUTCOMES (fidelity relaxation R3): `attack_until_dead`
repeats the last attack until the original's villain-death marker ("black
fog" — Zork I uses it for every melee death) appears, bounded, so seeded
blow-by-blow differences between the two engines never desynchronize a
replay.

Nothing from the story file is stored by this module; it is a live probe
only. The story file itself lives outside the repo (see
bin/zork-oracle-bootstrap)."""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from pathlib import Path

DEATH_MARKER = "black fog"
PROMPT = "\n>"

# The dumb interface reprints the status window whenever it changes — with
# Zork I's move counter that is every turn. Shaped `<room>  Score: N
# Moves: M`; dropped from replies so state probes never mistake it for
# game text (e.g. inventory() reading it as a carried item).
_STATUS_LINE_RE = re.compile(r"Score:\s*-?\d+\s+Moves:\s*\d+\s*$")

# Real-engine responses that mean "the command did not resolve" and would
# invalidate a replay if silently accepted (a typo'd dataset command, a
# grounding failure). Turn-consuming refusals ("The trap door is closed")
# are NOT errors — both engines refuse identically by design.
_PARSE_FAILURES = (
    "I don't know the word",
    "That sentence isn't one I recognize",
    "You used the word",
    "There was no verb in that sentence",
)


def find_dfrotz() -> str | None:
    """The dfrotz binary: $DAYDREAM_DFROTZ, ~/data/zork/bin/dfrotz, or PATH."""
    env = os.environ.get("DAYDREAM_DFROTZ")
    if env and Path(env).is_file():
        return env
    home_build = Path.home() / "data/zork/bin/dfrotz"
    if home_build.is_file():
        return str(home_build)
    return shutil.which("dfrotz")


def find_story() -> str | None:
    """The story file: $DAYDREAM_ZORK_ORACLE_STORY only (never guessed)."""
    env = os.environ.get("DAYDREAM_ZORK_ORACLE_STORY")
    if env and Path(env).is_file():
        return env
    return None


class OracleParseError(AssertionError):
    """The real engine did not understand a replayed command."""


class Oracle:
    def __init__(self, story: str, *, seed: int = 4, dfrotz: str | None = None,
                 timeout: float = 5.0):
        import pexpect

        binary = dfrotz or find_dfrotz()
        if binary is None:
            raise FileNotFoundError("dfrotz not found (bin/zork-oracle-bootstrap)")
        # -R restricts frotz file I/O to a scratch dir AND lets save files
        # be named with short relative names (dfrotz 2.44 rejects long
        # absolute paths with "Filename too long").
        self._save_dir = tempfile.mkdtemp(prefix="zork-oracle-")
        self._ck = 0
        self.proc = pexpect.spawn(
            binary,
            ["-p", "-m", "-w", "200", "-s", str(seed), "-R", self._save_dir, story],
            encoding="utf-8", timeout=timeout, echo=False,
        )
        self.transcript: list[tuple[str, str]] = []
        self._read_reply()  # banner through the first prompt

    def close(self) -> None:
        if self.proc.isalive():
            self.proc.close(force=True)
        shutil.rmtree(self._save_dir, ignore_errors=True)

    def _read_reply(self) -> str:
        self.proc.expect_exact(PROMPT)
        raw = self.proc.before.replace("\r", "")
        return "\n".join(
            ln for ln in raw.split("\n") if not _STATUS_LINE_RE.search(ln)
        )

    def send(self, cmd: str, *, check: bool = True) -> str:
        self.proc.sendline(cmd)
        reply = self._read_reply()
        self.transcript.append((cmd, reply))
        if check:
            for marker in _PARSE_FAILURES:
                if marker in reply:
                    raise OracleParseError(f"real engine rejected {cmd!r}: {reply.strip()[:200]}")
        return reply

    # ---- state probes ------------------------------------------------------

    def _file_dialog(self, cmd: str, filename: str) -> str:
        """Drive a save/restore filename prompt ('Please enter a filename
        [...]:') and require the interpreter's 'Ok.'"""
        self.proc.sendline(cmd)
        self.proc.expect_exact(":")
        self.proc.sendline(filename)
        reply = self._read_reply()
        if "Ok" not in reply:
            raise AssertionError(f"{cmd} {filename!r} failed: {reply.strip()[:200]}")
        return reply

    def checkpoint(self) -> str:
        """Z-machine save to a fresh slot; returns the name for restore().
        Saving costs no move (verified against dfrotz 2.44)."""
        name = f"ck{self._ck}.sav"
        self._ck += 1
        self._file_dialog("save", name)
        return name

    def restore(self, name: str) -> None:
        """Restore a checkpoint() slot. Rewinds the GAME (clock, fuses, the
        thief, object state) but NOT the interpreter's RNG stream — so a
        restored-and-replayed stretch samples fresh rolls. Segment-retry
        replays (the outcome-faithful combat contract, R3, applied at
        segment scope) depend on exactly that property."""
        self._file_dialog("restore", name)

    def state(self) -> tuple[str, int, set[str]]:
        """(room, score, inventory) probed at ZERO real-game cost: the raw
        probes each tick the Z-machine clock, so they run inside a Z-machine
        save/restore bracket — afterwards the clock, fuses, the thief, and
        object state are exactly as if the probe never happened. (The
        interpreter RNG does advance — see restore() — which is harmless
        here and load-bearing for segment retries.)"""
        name = self.checkpoint()
        room, score, inv = self.room(), self.score(), self.inventory()
        self.restore(name)
        return room, score, inv

    def room(self) -> str:
        """The room name: the first non-blank line of `look` output. In a
        dark room Zork I prints its darkness line instead; that is returned
        verbatim so callers can assert darkness too."""
        reply = self.send("look", check=False)
        for line in reply.splitlines():
            line = line.strip()
            if line:
                return line
        return ""

    def score(self) -> int:
        reply = self.send("score", check=False)
        m = re.search(r"score is (\d+)", reply)
        if not m:
            raise AssertionError(f"unparseable score reply: {reply.strip()[:200]}")
        return int(m.group(1))

    def inventory(self) -> set[str]:
        """Carried item names, lowercased, articles stripped, container
        nesting flattened ('A jewel-encrusted egg' -> 'jewel-encrusted egg').
        'You are empty-handed.' yields the empty set.

        Only INDENTED lines under the 'You are carrying:' header count as
        items — the game indents its listing, while interleaved ambient
        text (the thief wandering through) starts at column 0 and must not
        be scooped up as a carried item."""
        reply = self.send("i", check=False)
        items: set[str] = set()
        in_listing = False
        for line in reply.splitlines():
            if "empty-handed" in line.lower():
                return set()
            if line.strip().lower().startswith("you are carrying"):
                in_listing = True
                continue
            if not in_listing or not line.strip():
                continue
            if not line[0].isspace():
                in_listing = False  # ambient text resumes at column 0
                continue
            name = line.strip()
            name = re.sub(r"^(a|an|the)\s+", "", name.rstrip(".").strip(), flags=re.I)
            name = re.sub(r"\s*\((?:providing light|being worn)\)$", "", name, flags=re.I)
            if name and not name.endswith(":"):
                items.add(name.lower())
        return items

    def attack_until_dead(self, attack_cmd: str, *, cap: int = 20) -> str:
        """Repeat `attack_cmd` until the villain-death marker appears
        (outcome-faithful combat, R3). Returns the full accumulated reply.

        Disarms are part of a normal Zork melee: when a blow knocks the
        weapon from the player's hand, the next attack fails with a
        'not holding' refusal — the loop re-takes the weapon (as any human
        player would; the villain gets its free swing while we stoop) and
        keeps fighting. A villain never disarms on its own death blow, so
        the weapon is back in hand by the time the fight ends and
        inventory checkpoints stay faithful.

        Raises on player death (a seed-shopping signal) or if the cap is
        reached — a fight the original cannot win with this weapon/seed is
        a real divergence."""
        weapon = attack_cmd.split(" with ")[-1].strip() if " with " in attack_cmd else None
        acc = ""
        for _ in range(cap):
            reply = self.send(attack_cmd, check=False)
            acc += "\n" + reply
            if "You have died" in reply:
                raise AssertionError(
                    f"player died fighting ({attack_cmd!r}); shop DAYDREAM_ZORK_ORACLE_SEED")
            if DEATH_MARKER in acc:
                return acc
            if weapon and ("holding" in reply or "don't have" in reply):
                self.send(f"take {weapon}", check=False)
        raise AssertionError(
            f"villain not dead after {cap} rounds of {attack_cmd!r}")
