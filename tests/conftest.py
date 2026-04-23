"""Project-wide pytest configuration. Loaded before any test module is
collected, so env vars set here are visible to module-level imports such as
`daydream.server.app` (which calls `config.session_secret()` at import time
to seed SessionMiddleware).

Without this, a clean `pytest` run would materialize
`~/.config/daydream/session_secret` in the developer's real home directory,
because `session_secret()` falls back to writing there when no env var is set.
"""

import os
import tempfile

# Stable test value for the session-cookie signing secret. Set before any
# `from daydream.server import app` runs, so SessionMiddleware never triggers
# the on-disk fallback during tests.
os.environ.setdefault("DAYDREAM_SESSION_SECRET", "test-session-secret-not-for-production")

# Stable test value for the shared site password. Decoupled from whatever
# .env holds in production so tests never depend on or leak the real value.
os.environ.setdefault("DAYDREAM_PASSWORD", "test-password")

# Redirect HOME to a session-scoped temp dir as a belt-and-suspenders measure:
# any other code that resolves `~/...` during tests writes under this dir,
# which the OS reaps. Use mkdtemp (not TemporaryDirectory) so the dir lives
# for the whole pytest process; pytest's own tmp_path fixture is unaffected.
os.environ.setdefault("HOME", tempfile.mkdtemp(prefix="daydream-test-home-"))
