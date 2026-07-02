"""Drive the real Zork I headless as a differential ground truth (SPEC
2026-07-02 criterion 14).

`Oracle` wraps `dfrotz -p -m -w 9999 -s <seed> <story>` behind pexpect:
plain output, no MORE prompts, no wrap, deterministic RNG. `send()` posts
one command and returns the reply text (everything up to the next `>`
prompt). State probes parse the game's own reporting:

    room()       the current room name (first line of a `look`)
    score()      the integer score (from `score`)
    inventory()  carried item names, containers flattened (from `i`)

The probes cost in-game turns in the real engine (LOOK ticks the clock in
Zork I exactly as it does on our side), so callers compare state at segment
checkpoints, not per command.

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
from pathlib import Path

DEATH_MARKER = "black fog"
PROMPT = "\n>"

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
        self.proc = pexpect.spawn(
            binary, ["-p", "-m", "-w", "9999", "-s", str(seed), story],
            encoding="utf-8", timeout=timeout,
        )
        self.transcript: list[tuple[str, str]] = []
        self._read_reply()  # banner through the first prompt

    def close(self) -> None:
        if self.proc.isalive():
            self.proc.close(force=True)

    def _read_reply(self) -> str:
        self.proc.expect_exact(PROMPT)
        return self.proc.before.replace("\r", "")

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
        'You are empty-handed.' yields the empty set."""
        reply = self.send("i", check=False)
        items: set[str] = set()
        for line in reply.splitlines():
            line = line.strip()
            if not line or line.lower().startswith("you are carrying"):
                continue
            if "empty-handed" in line.lower():
                return set()
            line = re.sub(r"^(a|an|the)\s+", "", line.rstrip(".").strip(), flags=re.I)
            line = re.sub(r"\s*\((?:providing light|being worn)\)$", "", line, flags=re.I)
            if line and not line.endswith(":"):
                items.add(line.lower())
        return items

    def attack_until_dead(self, attack_cmd: str, *, cap: int = 15) -> str:
        """Send `attack_cmd`, then repeat `again` until the villain-death
        marker appears (outcome-faithful combat, R3). Returns the full
        accumulated reply. Raises if the cap is reached — a fight the
        original cannot win with this weapon/seed is a real divergence."""
        acc = self.send(attack_cmd)
        for _ in range(cap):
            if DEATH_MARKER in acc:
                return acc
            acc += "\n" + self.send("again")
        raise AssertionError(
            f"villain not dead after {cap} rounds of {attack_cmd!r}")
