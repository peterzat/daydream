"""LLM safety primitives for the data-skill prompt/response path.

Three responsibilities, each a pure function so callers can compose
them without pulling in LLM or DB state:

1. Banlist check (`first_banned`) — regex filter anchored in the seven
   "Banned moods" categories WHIMSY.md enumerates. Applied to the
   player's free-text args BEFORE they reach a prompt template, and to
   the LLM's narrative text AFTER the response comes back but BEFORE
   effects are applied. A hit at either point should drop effects and
   emit a tone-appropriate narrate fallback.

2. Role-separator containment (`wrap_player_input`) — wraps the player
   text in <player_input>...</player_input> tags so a skill's Jinja
   template can inject `{{ player_input }}` into an LLM prompt without
   the player being able to break out of the quoted region. Any
   literal `</player_input>` inside the player's text is neutralized
   so it cannot close the wrapper early.

3. Refusal-schema parsing (`parse_refusal`) — when the LLM chooses to
   refuse, it returns `{"refused": true, "reason": "..."}` at the top
   of its JSON payload. The caller short-circuits effects and narrates
   the reason instead.

Intentionally minimal. v2's full pipeline (Jinja template sandboxing
beyond the stdlib SandboxedEnvironment, per-effect jsonschema, a
content-safety ML classifier, audit + undo) lives in the BACKLOG
entry `skills-authoring-and-security` and is explicitly out of scope
for this spec's safety baseline."""

import re
from dataclasses import dataclass

# One regex per WHIMSY "Banned moods" category. Kept small and
# demonstrable — enough to exercise both safety paths in tests and
# give an operator a baseline to extend. Each pattern uses \b word
# boundaries so "classical" won't trip "class" etc. IGNORECASE so
# "PIXEL-ART" and "pixel-art" both match.
#
# WHIMSY.md categories (order preserved):
#   1. pixel-art / 8-bit / crunchy / retro-game (visual anti-tone)
#   2. grimdark / dystopian / brutalist / horror (mood anti-tone)
#   3. sexual / sensual / romantic-explicit (content anti-tone)
#   4. violence directed at any toon (content anti-tone)
#   5. urgency / deadlines / pressure / "you must" (framing anti-tone)
#   6. modern-tech / machinery / vehicles / computers (breaks-the-dream)
#   7. sarcasm / cynicism / irony at the player (tone anti-tone)
#
# Extending the banlist is additive and safe. Tightening a pattern is
# a review event: it may start firing on previously-accepted text.
_BANLIST: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("pixel-art",
     re.compile(r"\b(?:pixel[- ]?art|8[- ]?bit|crunchy|retro[- ]?game|retrowave)\b", re.IGNORECASE)),
    ("grimdark",
     re.compile(r"\b(?:grimdark|dystopian|brutalist|horror|nightmare)\b", re.IGNORECASE)),
    ("sexual",
     re.compile(r"\b(?:sexual|sensual|erotic)\b", re.IGNORECASE)),
    ("violence",
     re.compile(r"\b(?:stab|slash|slaughter|bludgeon|murder|maim|strangle)\b", re.IGNORECASE)),
    ("urgency",
     re.compile(r"\b(?:urgent|deadline|hurry|immediately|you must)\b", re.IGNORECASE)),
    ("modern-tech",
     re.compile(r"\b(?:computer|laptop|smartphone|motorcycle|rifle|machinery)\b", re.IGNORECASE)),
    ("sarcasm",
     re.compile(r"\b(?:stupid|idiot|pathetic|moron)\b", re.IGNORECASE)),
)


def first_banned(text: str) -> str | None:
    """Return the category name of the first banlist hit, or None.

    Categories are scanned in the order declared in `_BANLIST`; when
    multiple patterns match, the earlier-declared category wins. The
    returned name is the category label (e.g., "pixel-art"), not the
    matched substring, so logs stay compact and the actual offending
    word stays out of telemetry."""
    for name, pat in _BANLIST:
        if pat.search(text):
            return name
    return None


_CLOSE_TAG = "</player_input>"
# Visible, log-friendly replacement for a closing tag appearing
# inside the player's text. Any string that is NOT a recognizable
# closing tag works; this one is cheap and obviously intentional in
# a log line when it shows up.
_CLOSE_TAG_NEUTRALIZED = "<!player_input>"


def wrap_player_input(text: str) -> str:
    """Wrap `text` in role-separator tags for injection into an LLM
    prompt as a quoted player-authored region.

    Neutralizes any literal `</player_input>` inside `text` so the
    player cannot close the wrapper early and escape the quoted
    region. The output is guaranteed to contain exactly one opening
    tag and exactly one closing tag — the legitimate wrapper itself."""
    safe = text.replace(_CLOSE_TAG, _CLOSE_TAG_NEUTRALIZED)
    return f"<player_input>{safe}</player_input>"


@dataclass(frozen=True)
class Refusal:
    """A structured refusal extracted from an LLM response. The
    caller turns it into a `narrate` event and drops any effects
    that accompanied it in the same JSON payload."""

    reason: str


_DEFAULT_REFUSAL_REASON = "the dream won't hold that thought"


def parse_refusal(payload: object) -> Refusal | None:
    """If `payload` is a dict with `{"refused": True}` at the top
    level, return a Refusal with the supplied `reason` (or a
    tone-appropriate default if the reason is missing or blank).
    Otherwise return None.

    Strict `is True` check: only a real boolean True counts as
    refusal, so a stray `1` or the string `"true"` in a malformed
    response does not accidentally short-circuit effects."""
    if not isinstance(payload, dict):
        return None
    if payload.get("refused") is not True:
        return None
    reason = payload.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        return Refusal(reason=_DEFAULT_REFUSAL_REASON)
    return Refusal(reason=reason.strip())
