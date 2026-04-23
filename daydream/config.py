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


def port() -> int:
    return int(os.environ.get("DAYDREAM_PORT", "8080"))


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
    if vLLM is serving something else."""
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
