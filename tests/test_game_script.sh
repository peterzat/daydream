#!/usr/bin/env bash
# Smoke tests for bin/game. Side-effect free: never starts a real server.
# Real up/down integration is hand-verified in Inc 9.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GAME="$PROJECT_ROOT/bin/game"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Isolate from any live dev session.
export DAYDREAM_ENV="test-$$"
export XDG_RUNTIME_DIR="$TMP"
export HOME="$TMP"

fail() { echo "FAIL: $*" >&2; exit 1; }

[[ -x "$GAME" ]] || fail "bin/game not executable"

# Bad invocation.
if "$GAME" 2>/dev/null; then fail "no-args invocation should exit non-zero"; fi
if "$GAME" bogus 2>/dev/null; then fail "bogus subcommand should exit non-zero"; fi

# image-test subcommand should be in the usage line.
out="$("$GAME" 2>&1 || true)"
echo "$out" | grep -q "image-test" || fail "usage line should mention image-test; got: $out"
echo "$out" | grep -q "up-all" || fail "usage line should mention up-all; got: $out"

# image-test --help should not crash (uses argparse, exits 0).
if ! "$GAME" image-test --help >/dev/null 2>&1; then
    fail "image-test --help should exit 0"
fi

# status when nothing is running.
out="$("$GAME" status 2>&1)"
echo "$out" | grep -q "fastapi: stopped" || fail "status: expected 'fastapi: stopped'; got: $out"
echo "$out" | grep -q "env: test-" || fail "status: expected env line"
echo "$out" | grep -q "port: " || fail "status: expected port line"
echo "$out" | grep -q "rundir: " || fail "status: expected rundir line"

# down when nothing is running -> "not running", exit 0.
out="$("$GAME" down 2>&1)"
echo "$out" | grep -q "not running" || fail "down: expected 'not running'; got: $out"

# logs on a missing log -> non-zero (best-effort signal).
if "$GAME" logs 2>/dev/null; then fail "logs on missing log should exit non-zero"; fi

# Already-up fast path: `up` short-circuits with a friendly message instead of
# tripping the GPU preflight on the resident engines' own VRAM. Stub curl so
# every reachability probe reports the service up, and stub tailscale so the
# listening URLs fall back to hostname deterministically. No real server boots.
STUB="$TMP/stub"
mkdir -p "$STUB"
printf '#!/usr/bin/env bash\nexit 0\n' > "$STUB/curl"
printf '#!/usr/bin/env bash\nexit 1\n' > "$STUB/tailscale"
chmod +x "$STUB/curl" "$STUB/tailscale"

# GPU mode, whole stack already serving: friendly message, and crucially the
# short-circuit happens BEFORE the preflight + engine launch -- assert we never
# fall through to the full cmd_status block ('rundir:') or the engine banner.
out="$(PATH="$STUB:$PATH" "$GAME" up 2>&1)" || fail "up (already-up) should exit 0; got: $out"
echo "$out" | grep -q "game is already up" || fail "up (already-up): expected friendly message; got: $out"
echo "$out" | grep -q "listening:" || fail "up (already-up): expected listening URLs; got: $out"
if echo "$out" | grep -q "rundir:"; then fail "up (already-up): must not fall through to full status; got: $out"; fi
if echo "$out" | grep -q "Starting GPU engines"; then fail "up (already-up): engines must not start; got: $out"; fi

# --no-gpu already-up: FastAPI reachable alone is sufficient (engines ignored).
out="$(PATH="$STUB:$PATH" "$GAME" up --no-gpu 2>&1)" || fail "up --no-gpu (already-up) should exit 0; got: $out"
echo "$out" | grep -q "game is already up" || fail "up --no-gpu (already-up): expected friendly message; got: $out"

echo "PASS bin/game smoke checks"
