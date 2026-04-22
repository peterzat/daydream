"""Configuration: paths, env, ports, secrets. Functions, not module globals,
so tests can monkeypatch env vars and re-read."""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = PROJECT_ROOT / "migrations"
WEB_DIST_DIR = PROJECT_ROOT / "web" / "dist"


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
    return os.environ.get("DAYDREAM_LLM_MODEL", "hosted_vllm/Qwen/Qwen2.5-7B-Instruct")


def llm_api_key() -> str:
    return os.environ.get("DAYDREAM_LLM_API_KEY", "unused")


def password() -> str:
    return os.environ.get("DAYDREAM_PASSWORD", "REDACTED")


def session_secret() -> str:
    return os.environ.get("DAYDREAM_SESSION_SECRET", "daydream-dev-secret-not-prod")


def ensure_dirs() -> None:
    worlds_dir().mkdir(parents=True, exist_ok=True)
