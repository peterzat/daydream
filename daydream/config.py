"""Configuration: paths, env, ports, secrets. Functions, not module globals,
so tests can monkeypatch env vars and re-read."""

import os
import secrets
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = PROJECT_ROOT / "migrations"
WEB_DIR = PROJECT_ROOT / "web"  # v0 ships hand-written assets here; v1 may add Vite -> web/dist/


def env() -> str:
    return os.environ.get("DAYDREAM_ENV", "dev")


def target() -> str:
    """Operational test target for the current run. One of:

      local         full test behavior (default).
      staging       probes against a deployed staging env.
      prod_verify   read-only probes against production.

    v0 implements only 'local'. When DAYDREAM_TARGET is staging or
    prod_verify, tests carrying tier_medium / tier_long markers skip
    cleanly with a 'not yet wired' reason (see tests/conftest.py's
    _resolve_target fixture). tier_short tests stay target-agnostic by
    construction. Unknown values fall back to 'local' rather than
    erroring, so a typo never silently runs the wrong suite."""
    v = os.environ.get("DAYDREAM_TARGET", "local").strip().lower()
    if v not in ("local", "staging", "prod_verify"):
        return "local"
    return v


def port() -> int:
    """Daydream FastAPI server port. Default is 54321 (memorable, non-default;
    modest security-by-obscurity for a user-visible port). Override via
    DAYDREAM_PORT."""
    return int(os.environ.get("DAYDREAM_PORT", "54321"))


def access_mode() -> str:
    """Network access mode. Either 'tailscale' (default, the access middleware
    rejects clients outside the Tailscale CGNAT range 100.64.0.0/10 and
    localhost) or 'public' (middleware lets all through; operator must also
    open UFW for traffic to arrive). Override via DAYDREAM_ACCESS in .env."""
    return os.environ.get("DAYDREAM_ACCESS", "tailscale").strip().lower()


def data_dir() -> Path:
    return Path(os.environ.get("DAYDREAM_DATA_DIR", str(Path.home() / "data" / "daydream")))


def worlds_dir() -> Path:
    return data_dir() / f"worlds-{env()}"


def live_db_path() -> Path:
    return worlds_dir() / "live.db"


def llm_base_url() -> str:
    return os.environ.get("DAYDREAM_LLM_BASE_URL", "http://localhost:8000/v1")


def llm_model() -> str:
    """litellm-prefixed model name. Default matches bin/vllm-bootstrap's
    default model (Qwen 2.5 7B Instruct AWQ); override via DAYDREAM_LLM_MODEL
    if vLLM is serving something else.

    Why Qwen 2.5 7B Instruct AWQ specifically: see docs/gpu-and-models.md
    "LLM stack" — the picks alongside this one (Gemma 2 9B, Llama 3.x 8B,
    Mistral 7B variants), and why we landed here for our VRAM budget +
    vLLM compatibility. Bumping the model? Re-run tools/arbiter-smoke.py;
    the strict-JSON probe catches the 7B-class precision regressions
    documented in the same file (the fp8-KV-cache story)."""
    return os.environ.get("DAYDREAM_LLM_MODEL", "hosted_vllm/Qwen/Qwen2.5-7B-Instruct-AWQ")


def llm_api_key() -> str:
    return os.environ.get("DAYDREAM_LLM_API_KEY", "unused")


def comfyui_base_url() -> str:
    """ComfyUI HTTP server endpoint (default ComfyUI port). Override with
    DAYDREAM_COMFYUI_BASE_URL when running ComfyUI on a non-default port."""
    return os.environ.get("DAYDREAM_COMFYUI_BASE_URL", "http://localhost:8188")


def password() -> str:
    """Source the shared site password from DAYDREAM_PASSWORD. Empty string
    means no password is configured; the auth endpoint refuses logins in
    that state. Set in .env at the project root (sourced by bin/game) or
    in ~/.config/daydream/secrets.env."""
    return os.environ.get("DAYDREAM_PASSWORD", "")


def session_secret() -> str:
    """Source the session-cookie signing secret. Env var wins; otherwise fall
    back to a per-install random secret persisted under ~/.config/daydream/.
    Mirrors the password-source pattern (~/.config/daydream/secrets.env) so
    the published default never signs real cookies, even if an operator forgets
    to set DAYDREAM_SESSION_SECRET."""
    env_val = os.environ.get("DAYDREAM_SESSION_SECRET")
    if env_val:
        return env_val
    secret_path = Path.home() / ".config" / "daydream" / "session_secret"
    if secret_path.exists():
        existing = secret_path.read_text().strip()
        if existing:
            return existing
    secret_path.parent.mkdir(parents=True, exist_ok=True)
    new_secret = secrets.token_urlsafe(48)
    secret_path.write_text(new_secret + "\n")
    secret_path.chmod(0o600)
    return new_secret


def ensure_dirs() -> None:
    worlds_dir().mkdir(parents=True, exist_ok=True)
