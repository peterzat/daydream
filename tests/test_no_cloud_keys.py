"""No hosted-service key is in the repo (SPEC 2026-09-26 criterion 21; the
CLAUDE.md generation policy and its controlled exceptions, docs/EXTERNAL.md):
no tracked file carries a key-shaped secret or assigns a value to a key
variable, and the runtime's language model is the local engine. A declared
exception's key lives in the gitignored .env (dev) or the egress gateway's
root-only file (prod); design-time authoring is the agent in a Claude Code
session."""

import re
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.tier_short

ROOT = Path(__file__).resolve().parent.parent
KEY_SHAPES = re.compile(r"sk-ant-[A-Za-z0-9_-]{8,}|sk-proj-[A-Za-z0-9_-]{8,}|"
                        r"sk-[A-Za-z0-9]{32,}|"
                        # a TypeSafe (Jev) key: it lives in the gitignored .env
                        r"apikey_[0-9a-f]{16,}_[0-9a-f]{16,}")
ASSIGN = re.compile(r"^\s*(export\s+)?(ANTHROPIC|OPENAI|DAYDREAM_JEV|TYPESAFE)_API_KEY"
                    r"\s*=\s*\S+", re.M)


def _tracked() -> list[Path]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True,
                         check=True).stdout.splitlines()
    return [ROOT / p for p in out if (ROOT / p).is_file()]


def test_no_tracked_file_carries_a_cloud_llm_key():
    offenders = []
    for path in _tracked():
        if path.suffix in (".png", ".jpg", ".woff2", ".db", ".gz"):
            continue
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        if KEY_SHAPES.search(text) or ASSIGN.search(text):
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, offenders


def test_the_runtime_llm_endpoint_is_local():
    from daydream import config

    base = config.llm_base_url()
    assert "127.0.0.1" in base or "localhost" in base or base.startswith("http://100.")
    assert config.llm_model().startswith("hosted_vllm/")
