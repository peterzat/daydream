"""bin/game image-test CLI: arg parsing, deterministic output paths,
mocked end-to-end. No real ComfyUI needed."""

import asyncio
import hashlib
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from daydream.images import cli, client


@pytest.fixture(autouse=True)
def tmp_data_dir(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    yield


def test_derive_out_path_is_deterministic():
    p1 = cli.derive_out_path("a quiet meadow")
    p2 = cli.derive_out_path("a quiet meadow")
    assert p1 == p2


def test_derive_out_path_changes_with_prompt():
    p1 = cli.derive_out_path("a quiet meadow")
    p2 = cli.derive_out_path("a noisy meadow")
    assert p1 != p2


def test_derive_out_path_includes_prompt_slug():
    p = cli.derive_out_path("a quiet meadow")
    assert "quiet" in p.name or "meadow" in p.name
    assert p.suffix == ".png"


def test_derive_out_path_handles_long_or_messy_prompts():
    long_prompt = "x" * 200 + " ! @ # $ %"
    p = cli.derive_out_path(long_prompt)
    assert p.suffix == ".png"
    assert len(p.name) < 100  # safety filter caps the slug portion


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


def test_main_appends_whimsy_suffix_by_default(tmp_path: Path, capsys):
    captured_prompt: dict[str, str] = {}

    async def fake_gen(prompt, out_path, model, lora, seed, base_url=None):
        captured_prompt["full"] = prompt
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"fake")
        return out_path

    with patch.object(client, "generate_to_path", new=AsyncMock(side_effect=fake_gen)):
        rc = cli.main(["a meadow at dusk"])
    assert rc == 0
    assert "soft watercolor" in captured_prompt["full"]
    assert "a meadow at dusk" in captured_prompt["full"]


def test_main_omits_suffix_with_no_suffix_flag():
    captured_prompt: dict[str, str] = {}

    async def fake_gen(prompt, out_path, model, lora, seed, base_url=None):
        captured_prompt["full"] = prompt
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"fake")
        return out_path

    with patch.object(client, "generate_to_path", new=AsyncMock(side_effect=fake_gen)):
        rc = cli.main(["a meadow", "--no-suffix"])
    assert rc == 0
    assert captured_prompt["full"] == "a meadow"


def test_main_passes_model_and_lora_overrides():
    captured: dict = {}

    async def fake_gen(prompt, out_path, model, lora, seed, base_url=None):
        captured["model"] = model
        captured["lora"] = lora
        captured["seed"] = seed
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"fake")
        return out_path

    with patch.object(client, "generate_to_path", new=AsyncMock(side_effect=fake_gen)):
        rc = cli.main(["a meadow", "--model", "MyCkpt.safetensors", "--lora", "MyLora.safetensors", "--seed", "99"])
    assert rc == 0
    assert captured["model"] == "MyCkpt.safetensors"
    assert captured["lora"] == "MyLora.safetensors"
    assert captured["seed"] == 99


def test_main_writes_to_default_path(tmp_path: Path):
    async def fake_gen(prompt, out_path, model, lora, seed, base_url=None):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"fake-bytes")
        return out_path

    with patch.object(client, "generate_to_path", new=AsyncMock(side_effect=fake_gen)):
        rc = cli.main(["a meadow"])
    assert rc == 0
    expected = cli.derive_out_path("a meadow")
    assert expected.exists()
    assert expected.read_bytes() == b"fake-bytes"


def test_main_writes_to_explicit_out_path(tmp_path: Path):
    target = tmp_path / "explicit.png"

    async def fake_gen(prompt, out_path, model, lora, seed, base_url=None):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"fake")
        return out_path

    with patch.object(client, "generate_to_path", new=AsyncMock(side_effect=fake_gen)):
        rc = cli.main(["a meadow", "--out", str(target)])
    assert rc == 0
    assert target.exists()


def test_main_returns_2_on_comfyui_error(capsys):
    with patch.object(
        client,
        "generate_to_path",
        new=AsyncMock(side_effect=client.ComfyUIError("connection refused")),
    ):
        rc = cli.main(["a meadow"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "ComfyUI error" in err
    assert "connection refused" in err
    assert "Is ComfyUI running at" in err
