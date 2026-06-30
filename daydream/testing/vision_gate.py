"""Claude-vision aesthetic gate — design-time / test-time ONLY.

Rates a rendered image against the WHIMSY rubric (`WHIMSY.md`) via one Opus
vision call and returns a structured verdict. This is an OPT-IN convenience
that replaces a human aesthetic eyeball with an automated rubric check, so an
agent can confirm "the render is on-aesthetic" without a person looking.

Policy (CLAUDE.md, load-bearing). The running game is local-only and makes NO
cloud LLM calls. This gate is NOT runtime: it is invoked by the operator or an
agent at design / test time (the `bin/game review` harness; a `tier_long`
probe), the same category as Opus authoring a world envelope. It is OFF unless
`DAYDREAM_CLAUDE_VISION_GATE` is set, so routine and autonomous runs cost
nothing and add no cloud dependency. Enabling it requires `ANTHROPIC_API_KEY`
in the dev environment (litellm convention). There is no runtime call site.
"""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from pathlib import Path

ENV_FLAG = "DAYDREAM_CLAUDE_VISION_GATE"
MODEL_ENV = "DAYDREAM_VISION_MODEL"
THRESHOLD_ENV = "DAYDREAM_VISION_THRESHOLD"

# litellm Anthropic-provider id (mirrors bootstrap.py's design-time default,
# bumped to the current Opus). Override via DAYDREAM_VISION_MODEL.
DEFAULT_MODEL = "anthropic/claude-opus-4-8"
DEFAULT_THRESHOLD = 6  # score out of 10; below this reads as off-aesthetic

# The rubric mirrors WHIMSY.md (the tone bible). Keep the disqualifying list in
# sync with WHIMSY.md "Banned moods" + the image-gen prompt suffix if either
# drifts. A disqualifying element caps the verdict to FAIL regardless of score.
RUBRIC_SYSTEM = (
    "You are an art director grading a single illustration against a fixed "
    "house aesthetic for a cozy multiplayer dream-game. The house style is: "
    "soft watercolor, painterly, warm late-day or twilight light, cozy "
    "storybook illustration, gentle composition, soft edges; a low-saturation "
    "cream and sage palette with warm amber highlights; touchstones Spiritfarer "
    "and A Short Hike. DISQUALIFYING elements (seeing any one means the image "
    "is off-aesthetic): pixel-art or 8-bit or crunchy retro-game look; "
    "grimdark, dystopian, brutalist, or horror mood; modern technology, "
    "machinery, vehicles, or computers; harsh edges, high contrast, or neon; "
    "pure black, pure white, or bright-red dominance; visible text or logos; "
    "people in modern dress. Grade ONLY the aesthetic, not how well the subject "
    "is drawn. Respond with a JSON object and nothing else: "
    '{"score": <integer 0-10>, "banned": [<disqualifying elements you see, '
    'else empty>], "reason": "<one short sentence>"}. A score of 10 means '
    "unmistakably on-aesthetic; 0 means entirely off."
)


def enabled() -> bool:
    """True when the gate is switched on. Off (the default) means callers skip
    it entirely — no API call, no cost."""
    return os.environ.get(ENV_FLAG, "").strip().lower() not in (
        "", "0", "false", "no", "off",
    )


def model() -> str:
    return os.environ.get(MODEL_ENV) or DEFAULT_MODEL


def threshold() -> int:
    raw = os.environ.get(THRESHOLD_ENV)
    if not raw or not raw.strip():
        return DEFAULT_THRESHOLD
    try:
        return int(raw)
    except ValueError:
        return DEFAULT_THRESHOLD


@dataclass(frozen=True)
class VisionVerdict:
    score: int
    passed: bool
    reason: str
    banned: tuple[str, ...]

    @property
    def label(self) -> str:
        return f"{'PASS' if self.passed else 'FAIL'} {self.score}/10"


def _data_url(png_path: Path | str) -> str:
    raw = Path(png_path).read_bytes()
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:image/png;base64,{b64}"


def parse_verdict(content: str, thr: int) -> VisionVerdict:
    """Parse the model's JSON reply into a verdict. A non-empty `banned` list
    caps the result to FAIL even with a generous score (a single disqualifying
    element means off-aesthetic, per the rubric)."""
    data = json.loads(content)
    score = int(data.get("score", 0))
    banned = tuple(str(x) for x in (data.get("banned") or []) if str(x).strip())
    reason = str(data.get("reason", "")).strip()
    passed = score >= thr and not banned
    return VisionVerdict(score=score, passed=passed, reason=reason, banned=banned)


def build_messages(png_path: Path | str, subject: str) -> list[dict]:
    """The litellm `messages` payload: the WHIMSY rubric as system, the image
    as a base64 data URL. Split out so a test can assert the rubric + image
    block without making a network call."""
    return [
        {"role": "system", "content": RUBRIC_SYSTEM},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": f"Grade this image ({subject})."},
                {"type": "image_url", "image_url": {"url": _data_url(png_path)}},
            ],
        },
    ]


async def rate_image(png_path: Path | str, *, subject: str = "a room background") -> VisionVerdict:
    """Rate one PNG against the WHIMSY rubric via one Opus vision call.

    Requires the gate enabled (`enabled()` True) AND `ANTHROPIC_API_KEY` set.
    Raises RuntimeError if called while disabled (callers check `enabled()`
    first); propagates any litellm error so a broken gate fails loudly rather
    than silently passing. CPU/network only — never takes the GPU arbiter."""
    if not enabled():
        raise RuntimeError(
            f"vision gate disabled; set {ENV_FLAG}=1 (and ANTHROPIC_API_KEY) to enable"
        )
    import litellm

    resp = await litellm.acompletion(
        model=model(),
        messages=build_messages(png_path, subject),
        response_format={"type": "json_object"},
        max_tokens=300,
        temperature=0,
    )
    return parse_verdict(resp.choices[0].message.content, threshold())
