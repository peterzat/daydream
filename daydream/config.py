"""Configuration: paths, env, ports, secrets. Functions, not module globals,
so tests can monkeypatch env vars and re-read."""

import os
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


ACCESS_MODES = ("tailscale", "public", "edge")


def access_mode() -> str:
    """Network access mode (DAYDREAM_ACCESS):

      tailscale  (default, dev) the access middleware rejects clients outside
                 the Tailscale CGNAT range 100.64.0.0/10 and loopback.
      public     no network filter (the test suite; a bare public bind would
                 also need UFW opened, which this project never does).
      edge       prod behind the Cloudflare Worker + tunnel (docs/GOING-LIVE.md):
                 no network location grants anything, CSRF compares Origin to
                 DAYDREAM_PUBLIC_ORIGIN, and the client address comes only from
                 the Worker's X-Daydream-Client-IP header.

    Every mode requires an account session for everything outside the public
    allowlist; the mode only adds network-level rules. An unknown value is a
    boot error (`boot_problems`), never a silent default."""
    return os.environ.get("DAYDREAM_ACCESS", "tailscale").strip().lower()


def public_base() -> str:
    """The URL path prefix the browser sees, with leading and trailing slash:
    "/" in dev, "/daydream/" in prod. The edge Worker strips it before
    proxying, so the origin always serves at "/" and only browser-facing URLs
    (the SPA's <base href>, redirects, cookie path) carry it."""
    raw = os.environ.get("DAYDREAM_PUBLIC_BASE", "").strip()
    if not raw:
        return "/"
    if not raw.startswith("/"):
        raw = "/" + raw
    if not raw.endswith("/"):
        raw += "/"
    return raw


def public_origin() -> str:
    """scheme://host the browser uses (prod: https://www.eidolon.com), no
    trailing slash. Empty in dev, where CSRF compares Origin to Host. Behind
    the Worker, Host is the tunnel hostname, so edge mode requires this."""
    return os.environ.get("DAYDREAM_PUBLIC_ORIGIN", "").strip().rstrip("/")


def bind_host() -> str:
    """The address uvicorn binds (DAYDREAM_BIND_HOST). bin/game and the prod
    systemd unit both pass it as --host, so this is the single source the boot
    guard can check. Dev default 0.0.0.0 (tailnet clients reach it; UFW keeps
    the public interface closed); prod must be loopback."""
    return os.environ.get("DAYDREAM_BIND_HOST", "0.0.0.0").strip()


def public_url(path: str = "") -> str:
    """An absolute browser-facing URL for `path` (an invite link, say): the
    public origin + base in prod; the box's own tailnet name in dev."""
    import socket

    origin = public_origin() or f"http://{socket.gethostname()}:{port()}"
    return origin + public_base() + path.lstrip("/")


def cookie_name() -> str:
    """The session cookie's name, per env, so a dev cookie and a prod cookie
    on the same browser never collide."""
    return f"dd_session_{env()}"


def cookie_secure() -> bool:
    """Mark the session cookie Secure whenever the browser reaches us over
    https (prod always)."""
    return public_origin().startswith("https://")


def operator_name(fallback: str = "the person who invited you") -> str:
    """Who friends ask for help (an invite that won't work, a sleeping
    village). Set DAYDREAM_OPERATOR_NAME in the deployment's env; the default
    stays generic because this repo is public. `fallback=""` hands the choice
    to a client that adds a title to a real name."""
    return os.environ.get("DAYDREAM_OPERATOR_NAME", "").strip() or fallback


LOOPBACK_HOSTS = ("127.0.0.1", "::1", "localhost")


def boot_problems() -> list[str]:
    """Reasons this process must refuse to serve (checked in the server
    lifespan). Prod fails closed: it boots only in edge mode, with a public
    https origin, an explicit public base, and a loopback bind."""
    problems: list[str] = []
    mode = access_mode()
    if mode not in ACCESS_MODES:
        problems.append(f"DAYDREAM_ACCESS={mode!r} is not one of {', '.join(ACCESS_MODES)}")
    if mode == "edge" and not public_origin():
        problems.append("edge mode needs DAYDREAM_PUBLIC_ORIGIN (e.g. https://www.eidolon.com)")
    if env() == "prod":
        if mode != "edge":
            problems.append(f"prod must run with DAYDREAM_ACCESS=edge (got {mode!r})")
        if not public_origin().startswith("https://"):
            problems.append("prod needs an https DAYDREAM_PUBLIC_ORIGIN")
        if not os.environ.get("DAYDREAM_PUBLIC_BASE", "").strip():
            problems.append("prod needs an explicit DAYDREAM_PUBLIC_BASE (e.g. /daydream/)")
        if bind_host() not in LOOPBACK_HOSTS:
            problems.append(f"prod must bind loopback (DAYDREAM_BIND_HOST={bind_host()!r})")
    return problems


def data_dir() -> Path:
    return Path(os.environ.get("DAYDREAM_DATA_DIR", str(Path.home() / "data" / "daydream")))


def worlds_dir() -> Path:
    return data_dir() / f"worlds-{env()}"


def live_db_path() -> Path:
    return worlds_dir() / "live.db"


def accounts_db_path() -> Path:
    """Who may play: accounts, sessions, invites (daydream/accounts.py). One
    per env, beside the worlds dir and never inside it, so `world reset`,
    swap and refresh cannot touch it."""
    return data_dir() / f"accounts-{env()}.db"


def llm_base_url() -> str:
    return os.environ.get("DAYDREAM_LLM_BASE_URL", "http://localhost:8000/v1")


def llm_model() -> str:
    """litellm-prefixed model name. Default matches bin/vllm-bootstrap's
    default model (Qwen3.5 9B AWQ 4-bit); override via DAYDREAM_LLM_MODEL
    if vLLM is serving something else.

    Why this model: see docs/gpu-and-models.md "September 2026
    re-evaluation": the bake-off against Qwen 2.5 7B, Qwen3 8B/14B,
    Gemma 4 12B and Qwen3.5 4B, and why the 9B won inside the unchanged
    0.45 VRAM slice. Bumping the model? Run `bin/game model-eval run`
    against it (and tools/arbiter-smoke.py); compare with `model-eval
    compare` before switching."""
    return os.environ.get("DAYDREAM_LLM_MODEL", "hosted_vllm/cyankiwi/Qwen3.5-9B-AWQ-4bit")


def llm_api_key() -> str:
    return os.environ.get("DAYDREAM_LLM_API_KEY", "unused")


def llm_is_local() -> bool:
    """Whether the LLM endpoint is this box's (or a tailnet) engine. Only a
    local endpoint takes the GPU arbiter's slots; a remote one (the seam in
    docs/remote-reflexes.md; off under the generation policy) gets its own
    concurrency limit instead (SPEC 2026-09-27 criterion 23)."""
    from urllib.parse import urlparse

    host = (urlparse(llm_base_url()).hostname or "").lower()
    return host in ("localhost", "127.0.0.1", "::1") or host.startswith("100.")


def remote_llm_concurrency() -> int:
    try:
        return max(1, int(os.environ.get("DAYDREAM_REMOTE_LLM_CONCURRENCY", "3")))
    except ValueError:
        return 3


def image_backend() -> str:
    """Which image backend renders (DAYDREAM_IMAGE_BACKEND): "comfyui", the
    local engine, is the default and the only one implemented; the seam and
    the policy for another are in docs/remote-reflexes.md."""
    return os.environ.get("DAYDREAM_IMAGE_BACKEND", "comfyui").strip().lower() or "comfyui"


def image_backend_model() -> str:
    return os.environ.get("DAYDREAM_IMAGE_BACKEND_MODEL", "").strip()


def growth_max_rooms() -> int:
    """Cap on runtime-GROWN rooms per world (dreamseed plants, SPEC
    2026-07-02). Counts only grown rooms (`rooms.grown_room_count`), never
    authored ones, so a bigger authored world doesn't eat the growth budget.
    Checked before the growth LLM call and again at commit. Override via
    DAYDREAM_GROWTH_MAX_ROOMS."""
    return int(os.environ.get("DAYDREAM_GROWTH_MAX_ROOMS", "12"))


def comfyui_base_url() -> str:
    """ComfyUI HTTP server endpoint (default ComfyUI port). Override with
    DAYDREAM_COMFYUI_BASE_URL when running ComfyUI on a non-default port."""
    return os.environ.get("DAYDREAM_COMFYUI_BASE_URL", "http://localhost:8188")


def llm_concurrency() -> int:
    """Max concurrent LLM calls admitted by the GPU arbiter's shared "llm"
    gate. vLLM batches internally within its preallocated VRAM slice, so
    concurrency here costs KV-cache tokens, not extra weights memory; the
    KV math behind the default of 3 (pool ~50-60k tokens vs 24.6k worst
    case at 3x8192) is in docs/gpu-and-models.md. Override with
    DAYDREAM_LLM_CONCURRENCY; keep <= vLLM's --max-num-seqs."""
    raw = os.environ.get("DAYDREAM_LLM_CONCURRENCY", "3")
    try:
        return max(1, int(raw))
    except ValueError:
        return 3


PROD_GPU_LOCK = Path("/srv/daydream/data/gpu.lock")


def gpu_lock_path() -> Path | None:
    """The lock file every daydream process on this box shares for the GPU
    (daydream/gpu/arbiter.py's cross-process layer, SPEC 2026-09-27 criterion
    21). DAYDREAM_GPU_LOCK names it; empty turns the layer off (the test
    suite). Unset, it is the prod install's file when that exists (so dev and
    prod coordinate with no configuration), else none."""
    raw = os.environ.get("DAYDREAM_GPU_LOCK")
    if raw is not None:
        return Path(raw) if raw.strip() else None
    return PROD_GPU_LOCK if PROD_GPU_LOCK.exists() else None


def regen_ui_enabled() -> bool:
    """Whether the dev room-repaint surface is live: the two
    /api/rooms/{id}/image* endpoints and the SPA's plate tools (the
    snapshot carries the flag). Default ON — dev is where this project
    lives; flip DAYDREAM_REGEN_UI=0 on a shared deployment so players
    cannot repaint shared room art (BACKLOG regen-ui-gate)."""
    return os.environ.get("DAYDREAM_REGEN_UI", "1").strip().lower() not in (
        "0", "false", "no", "off",
    )


def journal_enabled() -> bool:
    """Whether leaving the dream writes a journal recap (one local-LLM call
    per leave — SPEC 2026-07-07 criterion 3). Default ON; the test suite
    forces DAYDREAM_JOURNAL_ENABLED=0 in conftest so deterministic tests
    stay zero-LLM (journal tests opt in and mock the client). Also the kill
    switch for a shared deployment, or the honest-default flip if the 7B
    recap quality misses the bar (flag-local-limits pact)."""
    return os.environ.get("DAYDREAM_JOURNAL_ENABLED", "1").strip().lower() not in (
        "0", "false", "no", "off",
    )


def ensure_dirs() -> None:
    worlds_dir().mkdir(parents=True, exist_ok=True)
