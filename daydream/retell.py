"""The retell layer (SPEC 2026-07-02 criterion 13): an OPTIONAL local-LLM
rephrase of authored rule narrations into the world's voice register,
additive and never load-bearing.

A world opts in through its envelope `voice` block:

    "voice": {"register": "...", "examples": [...],
              "retell": {"enabled": true, "banlist": [...],
                          "max_ratio": 1.6, "timeout": 3.0}}

`maybe_retell(world_id, text, purpose)` returns the retold text ONLY when
every gate passes, and the authored text on ANY failure — disabled world,
ineligible text, backend down, timeout, or a candidate that flunks
validation. It never raises: the deterministic spine is byte-identical to
a world with retell off whenever the LLM is absent (criterion 13's
vLLM-down clause; also why tests/conftest.py forces the kill-switch off —
criterion 1's walkthrough spy proves the spine makes ZERO calls).

Verbatim zones protect iconic and mechanical lines two ways:
- an authored `"verbatim": true` on a narrate effect is absolute;
- `eligible()` refuses the mechanical shapes wholesale: short lines,
  quoted speech and inscriptions, shaped/multi-line text, shouting beats.

Validation is strict and cheap: proper nouns preserved (every capitalized
token that isn't sentence-initial), digit runs preserved, length ratio
within the authored cap (and not gutted), banlist respected. The identity
stays verbatim; only the prose around it breathes (R10).

THE SHIPPED RUNG IS SCOPED (probe-ratified 2026-07-02): the authored line
always speaks FIRST — a text is retold only once this world has already
told it verbatim at least once (a per-text seen counter in worldstate).
First impressions and one-shot beats (a wall-breaking flight, the win) are
therefore always the author's; the LLM varies the echoes, which is where
staleness would otherwise live. The rung ladder remains ON -> scoped ->
OFF; the retell drift probe measures the SECOND telling."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re

from daydream import worldstate
from daydream.llm import client as llm_client

logger = logging.getLogger(__name__)

MIN_ELIGIBLE_CHARS = 60
MIN_RATIO = 0.45
DEFAULT_MAX_RATIO = 1.6
DEFAULT_TIMEOUT = 3.0
RETELL_TEMPERATURE = 0.8

_SENTENCE_START = re.compile(r"(?:^|[.!?]\s+|\n\s*)([A-Z][\w'-]*)")
_CAPS_TOKEN = re.compile(r"\b[A-Z][\w'#-]*\b")
_DIGIT_RUN = re.compile(r"\d+")


def enabled_config(world_id: str) -> dict | None:
    """The world's retell config when the layer is ON, else None. The
    DAYDREAM_RETELL_ENABLED env var is the operator kill-switch (default on;
    tests force it off so the deterministic spine stays provably LLM-free)."""
    if os.environ.get("DAYDREAM_RETELL_ENABLED", "1") != "1":
        return None
    voice = worldstate.get(world_id, "voice")
    if not isinstance(voice, dict):
        return None
    cfg = voice.get("retell")
    if not isinstance(cfg, dict) or not cfg.get("enabled"):
        return None
    return {"voice": voice, **cfg}


def eligible(text: str) -> bool:
    """Heuristic verbatim zones: mechanical and iconic shapes never retold."""
    if not isinstance(text, str):
        return False
    t = text.strip()
    if len(t) < MIN_ELIGIBLE_CHARS:
        return False  # short lines are mechanics ("Click.", "Ding, dong.")
    if '"' in t:
        return False  # speech and inscriptions stay verbatim
    if "\n" in t:
        return False  # shaped text (gate inscription, label, BOOM art)
    if re.search(r"\b[A-Z]{3,}\b", t):
        return False  # shouting beats and sigils (BOOM, GUE, XYZZY)
    return True


def proper_nouns(text: str) -> set[str]:
    """Capitalized tokens that are NOT sentence-initial — the identity the
    retold line must carry unchanged. 'I' is grammar, not identity."""
    starts = {m.group(1) for m in _SENTENCE_START.finditer(text)}
    return {tok for tok in _CAPS_TOKEN.findall(text)
            if tok not in starts and tok != "I"}


def validate(original: str, candidate, cfg: dict) -> bool:
    if not isinstance(candidate, str):
        return False
    cand = candidate.strip()
    if not cand or cand == original.strip():
        return False
    ratio = len(cand) / max(1, len(original.strip()))
    max_ratio = cfg.get("max_ratio")
    if not isinstance(max_ratio, (int, float)):
        max_ratio = DEFAULT_MAX_RATIO
    if ratio > float(max_ratio) or ratio < MIN_RATIO:
        return False
    for noun in proper_nouns(original):
        if noun not in cand:
            return False
    for run in _DIGIT_RUN.findall(original):
        if run not in cand:
            return False
    lowered = cand.lower()
    banlist = cfg.get("banlist")
    if isinstance(banlist, list):
        for word in banlist:
            if isinstance(word, str) and word.lower() in lowered:
                return False
    return True


def _system_prompt(voice: dict) -> str:
    register = voice.get("register") or ""
    examples = voice.get("examples") or []
    lines = [
        "You retell ONE line of game narration in the world's own voice.",
        f"Register: {register}",
    ]
    if examples:
        lines.append("Examples of the voice:")
        lines.extend(f"- {e}" for e in examples[:3] if isinstance(e, str))
    lines.append(
        "Rules: keep every proper noun, name, number, and stated fact exactly; "
        "change only the phrasing; similar length or shorter; never add new "
        "events or objects; no exclamation marks unless the original has them. "
        "Use plain, short words — NEVER swap a plain word for a fancier "
        "synonym; keep any joke or understatement intact. "
        'Return JSON: {"text": "<the retold line>"}'
    )
    return "\n".join(lines)


def _seen_key(text: str) -> str:
    return "retell_seen:" + hashlib.sha1(text.strip().encode()).hexdigest()[:16]


def _first_telling(world_id: str, text: str) -> bool:
    """True exactly once per (world, text): the authored line's turn to
    speak. Subsequent tellings are the retell layer's to vary."""
    key = _seen_key(text)
    count = worldstate.get(world_id, key)
    count = count if isinstance(count, int) else 0
    worldstate.set(world_id, key, count + 1)
    return count == 0


async def maybe_retell(world_id: str, text: str, *, purpose: str = "narrate") -> str:
    """The whole contract in one call: authored text in, retold-or-authored
    text out, never an exception, never a mutation."""
    cfg = enabled_config(world_id)
    if cfg is None or not eligible(text):
        return text
    if _first_telling(world_id, text):
        return text  # the scoped rung: the authored line speaks first
    timeout = cfg.get("timeout")
    if not isinstance(timeout, (int, float)) or timeout <= 0:
        timeout = DEFAULT_TIMEOUT
    try:
        result = await asyncio.wait_for(
            llm_client.acompletion_json(
                _system_prompt(cfg["voice"]),
                f"Retell this line:\n{text.strip()}",
                temperature=RETELL_TEMPERATURE,
                max_tokens=220,
                timeout=float(timeout),
            ),
            timeout=float(timeout) + 0.5,
        )
        candidate = result.get("text") if isinstance(result, dict) else None
    except Exception:
        logger.debug("retell fell back to authored text (%s)", purpose,
                     exc_info=True)
        return text
    if validate(text, candidate, cfg):
        return candidate.strip()
    return text


async def retell_effects(world_id: str, effs: list) -> list:
    """Map `maybe_retell` over a resolved effect list's eligible narrate
    texts. An authored `verbatim: true` is absolute; every other key rides
    through untouched. The returned list is new; inputs are not mutated."""
    if enabled_config(world_id) is None:
        return effs
    out = []
    for eff in effs:
        if (
            isinstance(eff, dict)
            and eff.get("kind") == "narrate"
            and not eff.get("verbatim")
            and isinstance(eff.get("text"), str)
        ):
            retold = await maybe_retell(world_id, eff["text"])
            if retold != eff["text"]:
                eff = {**eff, "text": retold}
        out.append(eff)
    return out
