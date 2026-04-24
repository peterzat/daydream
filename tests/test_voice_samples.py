"""Unit tests for daydream/voice_samples.py.

Covers SPEC 2026-04-24 criteria 1, 2, 3, 5 without GPU or live LLM —
the mocked LLM client stands in for vLLM, and a stubbed reachability
probe keeps the harness from actually trying to reach the network.
Criterion 4 (the two in-tree captures against real models) is
operator-run and covered by the committed markdown files themselves,
not by these tests.
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from daydream import voice_samples
from daydream.llm import client as llm_client

pytestmark = pytest.mark.tier_short


# Small fake usage object shaped like LiteLLM's response.usage.
class _FakeUsage:
    def __init__(self, prompt_tokens: int, completion_tokens: int):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens


class _FakeChoice:
    class _Msg:
        def __init__(self, content: str):
            self.content = content

    def __init__(self, content: str):
        self.message = self._Msg(content)


class _FakeResponse:
    def __init__(self, content: str, prompt_tokens: int, completion_tokens: int):
        self.choices = [_FakeChoice(content)]
        self.usage = _FakeUsage(prompt_tokens, completion_tokens)


def _fake_llm(text: str, pt: int = 100, ct: int = 30):
    """Return an async factory that mimics litellm.acompletion. Each
    invocation resolves to a single _FakeResponse with the given
    narrate text wrapped as a one-effect JSON body."""
    payload = {
        "effects": [{"kind": "narrate", "text": text}]
    }

    async def _call(*args, **kwargs):
        return _FakeResponse(json.dumps(payload), pt, ct)

    return _call


# ---- corpus loading -------------------------------------------------------


def test_corpus_files_exist_and_parse():
    """SPEC criterion 1: five files, each with name + skill + player_input."""
    prompts = voice_samples._load_corpus()
    assert len(prompts) == 5
    names = {p["name"] for p in prompts}
    expected = {
        "greeting", "forge_question", "inner_life",
        "small_talk", "open_invitation",
    }
    assert names == expected
    for p in prompts:
        assert p["skill"] == "rook"
        assert isinstance(p["player_input"], str)


def test_corpus_missing_required_field_raises(tmp_path, monkeypatch):
    bad = tmp_path / "voice"
    bad.mkdir()
    (bad / "broken.json").write_text(json.dumps({"name": "x"}))
    monkeypatch.setattr(voice_samples, "VOICE_CORPUS_DIR", bad)
    with pytest.raises(ValueError, match="missing required"):
        voice_samples._load_corpus()


def test_corpus_empty_dir_raises(tmp_path, monkeypatch):
    empty = tmp_path / "voice"
    empty.mkdir()
    monkeypatch.setattr(voice_samples, "VOICE_CORPUS_DIR", empty)
    with pytest.raises(FileNotFoundError):
        voice_samples._load_corpus()


# ---- model slug -----------------------------------------------------------


def test_slug_strips_org_prefix_and_lowercases():
    assert voice_samples._slug("Qwen/Qwen2.5-7B-Instruct-AWQ") == "qwen2.5-7b-instruct-awq"


def test_slug_hyphen_normalization():
    assert voice_samples._slug("Foo/Bar_Baz Model") == "bar_baz-model"


def test_slug_handles_bare_name():
    assert voice_samples._slug("onlyname") == "onlyname"


def test_slug_never_empty():
    assert voice_samples._slug("/") == "unknown-model"
    assert voice_samples._slug("") == "unknown-model"


# ---- reachability probe ---------------------------------------------------


def test_probe_vllm_reachable_returns_true_on_200():
    class _R:
        status_code = 200

    with patch("daydream.voice_samples.httpx.get", return_value=_R()):
        assert voice_samples._probe_vllm_reachable("http://fake:8000/v1") is True


def test_probe_vllm_reachable_returns_false_on_connection_error():
    import httpx

    def _raise(*args, **kwargs):
        raise httpx.HTTPError("nope")

    with patch("daydream.voice_samples.httpx.get", side_effect=_raise):
        assert voice_samples._probe_vllm_reachable("http://fake:8000/v1") is False


# ---- end-to-end harness (mocked LLM) -------------------------------------


def test_main_unreachable_vllm_exits_clean(tmp_path, capsys):
    """SPEC criterion 3: one-line diagnostic + non-zero exit, no
    traceback, when vLLM is unreachable."""
    with patch("daydream.voice_samples._probe_vllm_reachable", return_value=False):
        rc = voice_samples.main(["--out-dir", str(tmp_path)])
    assert rc == 2
    err = capsys.readouterr().err
    assert "unreachable" in err
    assert "vllm-up" in err.lower()
    # No output file should have been written.
    assert list(tmp_path.iterdir()) == []


def test_main_writes_dated_model_slugged_markdown(tmp_path):
    """SPEC criterion 2: the harness writes one dated + model-slugged
    file under the output dir; the file contains the metrics table,
    config block, and one H3 per prompt with player_input + narrate."""
    with patch("daydream.voice_samples._probe_vllm_reachable", return_value=True), \
         patch(
             "daydream.voice_samples.config.llm_model",
             return_value="Qwen/Qwen2.5-7B-Instruct-AWQ",
         ), \
         patch(
             "daydream.voice_samples.config.llm_base_url",
             return_value="http://127.0.0.1:8000/v1",
         ), \
         patch(
             "daydream.skills.data.llm_client.acompletion_json.__wrapped__",
             create=True,
         ), \
         patch("litellm.acompletion", new=_fake_llm("Rook nods quietly.")):
        rc = voice_samples.main(["--out-dir", str(tmp_path)])
    assert rc == 0
    files = list(tmp_path.glob("*.md"))
    assert len(files) == 1
    name = files[0].name
    # Filename carries today's date + a slug of the model.
    import datetime
    today = datetime.date.today().isoformat()
    assert name.startswith(today)
    assert "qwen2.5-7b-instruct-awq" in name
    text = files[0].read_text()
    # Header names the model.
    assert "Qwen2.5-7B-Instruct-AWQ" in text
    # Config block surfaces key flags.
    assert "`model`" in text
    assert "`kv_cache_dtype`" in text
    # Metrics table has a row per prompt, with token counts populated
    # from the mocked usage.
    assert "| prompt | tokens in | tokens out | wall seconds |" in text
    assert "`greeting`" in text
    assert "`forge_question`" in text
    assert "`inner_life`" in text
    assert "`small_talk`" in text
    assert "`open_invitation`" in text
    # Narrate text from the mocked LLM reached the captured section.
    assert "Rook nods quietly." in text


def test_main_overwrites_same_date_same_model(tmp_path):
    """SPEC criterion 2: same-date + same-model re-runs overwrite."""
    with patch("daydream.voice_samples._probe_vllm_reachable", return_value=True), \
         patch(
             "daydream.voice_samples.config.llm_model",
             return_value="Qwen/Qwen2.5-7B-Instruct-AWQ",
         ), \
         patch("litellm.acompletion", new=_fake_llm("First capture.")):
        voice_samples.main(["--out-dir", str(tmp_path)])
    with patch("daydream.voice_samples._probe_vllm_reachable", return_value=True), \
         patch(
             "daydream.voice_samples.config.llm_model",
             return_value="Qwen/Qwen2.5-7B-Instruct-AWQ",
         ), \
         patch("litellm.acompletion", new=_fake_llm("Second capture overwrites.")):
        voice_samples.main(["--out-dir", str(tmp_path)])
    files = list(tmp_path.glob("*.md"))
    assert len(files) == 1  # one file, not two
    text = files[0].read_text()
    assert "Second capture overwrites." in text
    assert "First capture." not in text


def test_main_different_model_writes_distinct_file(tmp_path):
    """SPEC criterion 2/4: same date + DIFFERENT model = two files."""
    with patch("daydream.voice_samples._probe_vllm_reachable", return_value=True), \
         patch(
             "daydream.voice_samples.config.llm_model",
             return_value="Qwen/Qwen2.5-7B-Instruct-AWQ",
         ), \
         patch("litellm.acompletion", new=_fake_llm("AWQ baseline here.")):
        voice_samples.main(["--out-dir", str(tmp_path)])
    with patch("daydream.voice_samples._probe_vllm_reachable", return_value=True), \
         patch(
             "daydream.voice_samples.config.llm_model",
             return_value="Qwen/Qwen2.5-7B-RP-Ink",
         ), \
         patch("litellm.acompletion", new=_fake_llm("RP-Ink variant here.")):
        voice_samples.main(["--out-dir", str(tmp_path)])
    files = sorted(tmp_path.glob("*.md"))
    assert len(files) == 2
    slugs = {f.name.rsplit("-", 6)[-1].replace(".md", "") for f in files}
    # Both files carry distinct model slugs in their names.
    names = [f.name for f in files]
    assert any("qwen2.5-7b-instruct-awq" in n for n in names)
    assert any("qwen2.5-7b-rp-ink" in n for n in names)


# ---- llm client usage side channel ---------------------------------------


def test_reset_and_get_last_usage_flow():
    """The side channel in llm/client.py: reset, then a populated
    response writes usage, then reset clears again."""
    llm_client.reset_last_usage()
    assert llm_client.get_last_usage() is None
    # Simulate an acompletion_json having just run: we set the
    # internal state as that function would, then read it.
    llm_client._last_usage = {"prompt_tokens": 42, "completion_tokens": 17}
    got = llm_client.get_last_usage()
    assert got is not None
    assert got["prompt_tokens"] == 42
    assert got["completion_tokens"] == 17
    llm_client.reset_last_usage()
    assert llm_client.get_last_usage() is None
