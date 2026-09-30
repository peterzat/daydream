"""Where Jev is configured, and whether it is on (docs/EXTERNAL.md).

Jev is ON exactly when this process can reach it with a key, and OFF
otherwise; there is no other switch (the operator's call, 2026-09-30):

- dev: the key is in the repo's gitignored `.env` (`DAYDREAM_JEV_API_KEY`),
  and calls go straight to the API;
- prod: the game's sandbox reaches loopback only, so calls go through the
  egress gateway (daydream/egress.py), which holds the key
  (`/etc/daydream/egress.env`, set with `bin/game prod root egress set`).
  Jev is on when the gateway says its `jev` route has a key.

Off, every surface is exactly its local path."""

from __future__ import annotations

import json
import os
import time
import urllib.request

# Input tokens only: output is free (docs.typesafe.ai/models).
USD_PER_INPUT_TOKEN = 0.042 / 1_000_000
# The versioned model, not an alias: thresholds tuned on one version are
# not carried to the next silently (docs/JEV-SPIKE.md).
DEFAULT_MODEL = "jev-1.13.0"
API = "https://api.typesafe.ai"
ROUTE = "jev"  # the egress gateway's route name
_ROUTES_TTL_S = 60.0
_routes: tuple[float, bool] | None = None


def api_key() -> str | None:
    """The key for direct calls (dev). Prod's is the gateway's, never here."""
    key = (os.environ.get("DAYDREAM_JEV_API_KEY") or os.environ.get("TYPESAFE_API_KEY")
           or "").strip()
    return key or None


def egress_url() -> str | None:
    """The egress gateway this process must use: set in prod (a fixed
    loopback port), unset in dev (`DAYDREAM_EGRESS_URL` overrides)."""
    from daydream import config

    url = os.environ.get("DAYDREAM_EGRESS_URL", "").strip()
    if url:
        return url.rstrip("/")
    return config.EGRESS_URL if config.env() == "prod" else None


def base_url() -> str:
    gw = egress_url()
    return f"{gw}/{ROUTE}" if gw else os.environ.get("DAYDREAM_JEV_BASE_URL", API).rstrip("/")


def model() -> str:
    return os.environ.get("DAYDREAM_JEV_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL


def timeout_s() -> float:
    """A live decision waits this long, then the local path serves."""
    try:
        return max(0.5, float(os.environ.get("DAYDREAM_JEV_TIMEOUT", "3")))
    except ValueError:
        return 3.0


def _gateway_has_key(gw: str) -> bool:
    """Whether the gateway's `jev` route has a key, asked at most once a
    minute (a loopback call; a gateway that does not answer is off)."""
    global _routes
    now = time.monotonic()
    if _routes is not None and now - _routes[0] < _ROUTES_TTL_S:
        return _routes[1]
    try:
        with urllib.request.urlopen(f"{gw}/routes", timeout=1.0) as r:  # noqa: S310 - loopback
            data = json.loads(r.read(65536) or b"{}")
        on = bool((data.get("routes") or {}).get(ROUTE))
    except Exception:  # noqa: BLE001 - no gateway is off
        on = False
    _routes = (now, on)
    return on


def enabled() -> bool:
    """On: a key here (dev), or a gateway whose `jev` route has one (prod)."""
    gw = egress_url()
    if gw:
        return _gateway_has_key(gw)
    return api_key() is not None


def forget() -> None:
    """Drop the cached gateway answer (tests, a key just set)."""
    global _routes
    _routes = None


def cost_usd(input_tokens: int | None) -> float:
    return (input_tokens or 0) * USD_PER_INPUT_TOKEN
