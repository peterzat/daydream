"""bin/game image-test CLI: arg parsing, EphemeralTarget construction,
mocked end-to-end. No real ComfyUI needed."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from daydream.images import cli, client


@pytest.fixture(autouse=True)
def tmp_data_dir(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    yield


# ---- arg parsing -------------------------------------------------------


def test_parse_args_minimal():
    args = cli.parse_args(["a meadow"])
    assert args.prompt == "a meadow"
    assert args.model is None
    assert args.lora is None
    assert args.seed == 0
    assert args.no_suffix is False


def test_parse_args_full():
    args = cli.parse_args(
        ["a meadow", "--model", "x.safetensors", "--lora", "y.safetensors", "--seed", "42"]
    )
    assert args.model == "x.safetensors"
    assert args.lora == "y.safetensors"
    assert args.seed == 42


# ---- main: target construction + plumbing ------------------------------


def _capture_target_mock(captured: dict):
    """Build a generate_image mock that records the target and kwargs."""
    async def _gen(target, *, model=None, lora=None, seed=None, base_url=None):
        captured["target"] = target
        captured["model"] = model
        captured["lora"] = lora
        captured["seed"] = seed
        # Materialize the file at the target's resolved path so
        # downstream existence checks pass.
        out = target.out_path or client.ephemeral_path(
            target.name,
            target.prompt + (
                " " + client.WHIMSY_PROMPT_SUFFIX if target.with_whimsy_suffix else ""
            ),
        )
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"fake")
        return out
    return AsyncMock(side_effect=_gen)


def test_main_appends_whimsy_suffix_by_default(capsys):
    captured: dict = {}
    with patch.object(client, "generate_image", new=_capture_target_mock(captured)):
        rc = cli.main(["a meadow at dusk"])
    assert rc == 0
    assert captured["target"].with_whimsy_suffix is True
    assert captured["target"].prompt == "a meadow at dusk"


def test_main_omits_suffix_with_no_suffix_flag():
    captured: dict = {}
    with patch.object(client, "generate_image", new=_capture_target_mock(captured)):
        rc = cli.main(["a meadow", "--no-suffix"])
    assert rc == 0
    assert captured["target"].with_whimsy_suffix is False


def test_main_passes_model_and_lora_overrides():
    captured: dict = {}
    with patch.object(client, "generate_image", new=_capture_target_mock(captured)):
        rc = cli.main(
            ["a meadow", "--model", "MyCkpt.safetensors",
             "--lora", "MyLora.safetensors", "--seed", "99"]
        )
    assert rc == 0
    assert captured["model"] == "MyCkpt.safetensors"
    assert captured["lora"] == "MyLora.safetensors"
    assert captured["seed"] == 99


def test_main_writes_to_default_ephemeral_path():
    captured: dict = {}
    with patch.object(client, "generate_image", new=_capture_target_mock(captured)):
        rc = cli.main(["a meadow"])
    assert rc == 0
    expected = client.ephemeral_path("a meadow", "a meadow " + client.WHIMSY_PROMPT_SUFFIX)
    assert expected.exists()
    assert expected.read_bytes() == b"fake"


def test_main_writes_to_explicit_out_path(tmp_path: Path):
    target_path = tmp_path / "explicit.png"
    captured: dict = {}
    with patch.object(client, "generate_image", new=_capture_target_mock(captured)):
        rc = cli.main(["a meadow", "--out", str(target_path)])
    assert rc == 0
    assert target_path.exists()
    assert captured["target"].out_path == target_path


def test_main_returns_2_on_comfyui_error(capsys):
    with patch.object(
        client,
        "generate_image",
        new=AsyncMock(side_effect=client.ComfyUIError("connection refused")),
    ):
        rc = cli.main(["a meadow"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "ComfyUI error" in err
    assert "connection refused" in err
    assert "Is ComfyUI running at" in err
