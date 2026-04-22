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

echo "PASS bin/game smoke checks"
