"""Constants-drift probes: machine-verified claims in CLAUDE.md, code,
and WHIMSY.md stay synchronized.

These tests are the cheap, always-on half of the drift system — no GPU,
no network, no engines required. They run in every `bin/game test short`
invocation as a regression gate against silent constants rot.

Four checks, ordered by importance:
1. WHIMSY_PROMPT_SUFFIX constant matches WHIMSY.md "## Prompt suffix".
   Absorbs the old tests/test_whimsy_prompt_suffix.py.
2. DAYDREAM_VLLM_MODEL default in bin/game matches CLAUDE.md's claim.
3. vllm version pinned in bin/vllm-bootstrap matches CLAUDE.md's table
   claim (today: vllm==0.19.1).
4. DAYDREAM_VLLM_GPU_FRACTION default in bin/game matches CLAUDE.md's
   "0.45 = ~9 GB on a 20 GB card" claim.

All four fail with a clear message pointing at BOTH sides of the
mismatch so the operator immediately knows which side to update."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from daydream.images import client as image_client

pytestmark = pytest.mark.tier_short


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
WHIMSY = PROJECT_ROOT / "WHIMSY.md"
CLAUDE_MD = PROJECT_ROOT / "CLAUDE.md"
BIN_GAME = PROJECT_ROOT / "bin" / "game"
BIN_VLLM_BOOTSTRAP = PROJECT_ROOT / "bin" / "vllm-bootstrap"


# ---- 1: WHIMSY_PROMPT_SUFFIX vs WHIMSY.md ------------------------------


def _extract_prompt_suffix_block() -> str:
    """Pull the verbatim text inside the first triple-backtick block
    under WHIMSY.md's '## Prompt suffix' section."""
    text = WHIMSY.read_text()
    assert "## Prompt suffix" in text, "WHIMSY.md is missing '## Prompt suffix'"
    after = text.split("## Prompt suffix", 1)[1]
    parts = after.split("```", 2)
    assert len(parts) >= 3, "WHIMSY.md '## Prompt suffix' is missing its code block"
    return parts[1].strip()


def _normalize_ws(s: str) -> str:
    """Collapse all whitespace runs to a single space so a line wrap or
    extra newline in WHIMSY.md does not register as drift."""
    return " ".join(s.split())


def test_whimsy_prompt_suffix_matches_code_constant():
    from_doc = _normalize_ws(_extract_prompt_suffix_block())
    from_code = _normalize_ws(image_client.WHIMSY_PROMPT_SUFFIX)
    assert from_doc == from_code, (
        "drift between WHIMSY.md '## Prompt suffix' and daydream/images/"
        "client.py WHIMSY_PROMPT_SUFFIX.\n"
        f"  WHIMSY.md:  {from_doc!r}\n"
        f"  client.py:  {from_code!r}\n"
        "edit either side to match; the doc is the durable tone source."
    )


def test_whimsy_prompt_suffix_mentions_anchors():
    """Belt-and-suspenders: even if both sides match, they must both
    keep the aesthetic anchors (watercolor + Spiritfarer/Short Hike)."""
    s = image_client.WHIMSY_PROMPT_SUFFIX.lower()
    assert "watercolor" in s
    assert "spiritfarer" in s or "short hike" in s


# ---- 2: DAYDREAM_VLLM_MODEL default --------------------------------------


def test_vllm_model_default_matches_claude_md():
    """bin/game defaults VLLM_MODEL to the HF model slug (e.g.
    'Qwen/Qwen2.5-7B-Instruct-AWQ'); CLAUDE.md describes the same model
    in prose ('Qwen 2.5 7B Instruct AWQ'). Don't require textual
    equality — extract the identifying tokens (family, size, variants)
    from the slug and assert CLAUDE.md mentions each. A model swap
    drops at least one token and this test fires."""
    game = BIN_GAME.read_text()
    m = re.search(r'VLLM_MODEL="\$\{DAYDREAM_VLLM_MODEL:-(?P<model>[^}]+)\}"', game)
    assert m, "bin/game no longer defines DAYDREAM_VLLM_MODEL in the expected shape"
    default = m.group("model")
    # Split an HF slug into tokens by /, -, and the size-digit boundary.
    # 'Qwen/Qwen2.5-7B-Instruct-AWQ' -> ['Qwen', 'Qwen2.5', '7B',
    # 'Instruct', 'AWQ']. Drop the org repetition so we don't require
    # it twice.
    tokens = [t for t in re.split(r"[/\-]", default) if t]
    # Drop org token if it repeats as a prefix of the model name
    # (Qwen / Qwen2.5 case).
    seen: set[str] = set()
    unique_tokens: list[str] = []
    for t in tokens:
        key = t.lower()
        if key not in seen:
            seen.add(key)
            unique_tokens.append(t)
    # Normalize '2.5' <-> '2.5' style: CLAUDE.md writes 'Qwen 2.5'
    # (space) but the slug has 'Qwen2.5' (no space). Check that each
    # token substring (case-insensitive) appears somewhere in CLAUDE.md.
    claude = CLAUDE_MD.read_text().lower()
    missing: list[str] = []
    for t in unique_tokens:
        probe = t.lower()
        # For a concatenated token like 'Qwen2.5', accept either the
        # raw token OR its split parts ('qwen', '2.5').
        parts = re.split(r"(\d+(?:\.\d+)?)", probe)
        parts = [p for p in parts if p]
        if probe in claude:
            continue
        if all(p in claude for p in parts):
            continue
        missing.append(t)
    assert not missing, (
        f"DAYDREAM_VLLM_MODEL default {default!r} has tokens {missing!r} "
        "not mentioned in CLAUDE.md. If you changed the model, update "
        "CLAUDE.md's 'vLLM (v1 LLM)' section and docs/gpu-and-models.md's "
        "'Model choice' narrative, then re-run tools/arbiter-smoke.py "
        "(the JSON probe catches 7B-class regressions)."
    )


# ---- 3: vllm version pin ------------------------------------------------


def test_vllm_version_pin_matches_claude_md():
    """CLAUDE.md's 'vLLM tunings on Ada' table pins vllm==0.19.1. The
    bootstrap script installs the same version. Bumping vllm is allowed
    but must come with a smoke re-run — catch the doc skew here."""
    if not BIN_VLLM_BOOTSTRAP.exists():
        pytest.skip("bin/vllm-bootstrap not present yet")
    script = BIN_VLLM_BOOTSTRAP.read_text()
    # bin/vllm-bootstrap defines VLLM_VERSION="${DAYDREAM_VLLM_PACKAGE_VERSION:-<X>}"
    # rather than a literal `vllm==X`, so pull the default from the env-var
    # default expression.
    m = re.search(r"DAYDREAM_VLLM_PACKAGE_VERSION:-(?P<version>[0-9.]+)", script)
    assert m, "bin/vllm-bootstrap no longer pins a vllm version"
    pinned = m.group("version")
    claude = CLAUDE_MD.read_text()
    claude_m = re.search(r"`vllm==([0-9.]+)`\s*\(pinned in bootstrap\)", claude)
    assert claude_m, (
        "CLAUDE.md no longer cites `vllm==<X>` (pinned in bootstrap) in the "
        "'vLLM tunings on Ada' table"
    )
    claimed = claude_m.group(1)
    assert pinned == claimed, (
        f"vllm version drift: bin/vllm-bootstrap pins {pinned}, "
        f"CLAUDE.md cites {claimed}. If you bumped, also re-run "
        "`tools/arbiter-smoke.py` and update both sides."
    )


# ---- 4: DAYDREAM_VLLM_GPU_FRACTION default ------------------------------


def test_vllm_gpu_fraction_default_matches_claude_md():
    """bin/game defaults the GPU fraction to 0.45, matching CLAUDE.md's
    '0.45 = ~9 GB on a 20 GB card' claim. A change here reshapes the
    arbiter's implicit VRAM budget and must be paired with a CLAUDE.md
    update so future readers see the new number."""
    game = BIN_GAME.read_text()
    m = re.search(
        r'VLLM_GPU_FRACTION="\$\{DAYDREAM_VLLM_GPU_FRACTION:-(?P<frac>[0-9.]+)\}"',
        game,
    )
    assert m, "bin/game no longer defines DAYDREAM_VLLM_GPU_FRACTION"
    default = m.group("frac")
    claude = CLAUDE_MD.read_text()
    assert default in claude, (
        f"DAYDREAM_VLLM_GPU_FRACTION default {default!r} not mentioned in "
        "CLAUDE.md. If you changed the GPU fraction, update CLAUDE.md's "
        "'vLLM (v1 LLM)' section (the '~9 GB on 20 GB card' narrative) "
        "so future sessions see the current number."
    )
