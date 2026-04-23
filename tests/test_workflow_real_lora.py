"""Sanity check the painterly_room.json workflow's lora_name field is
configured (not still the unconfigured placeholder) and points at a real
.safetensors file. Catches the mistake of pasting a fresh upstream
workflow and forgetting to set the LoRA name during install."""

import pytest

from daydream.images import client

pytestmark = pytest.mark.tier_short

# This is the explicit "I have not configured a LoRA yet" sentinel that
# painterly_room.json shipped with originally. If it ever reappears in
# the workflow JSON, that's a regression — the bootstrap or the operator
# install missed the lora_name update.
PLACEHOLDER = "watercolor.safetensors"


def test_workflow_lora_name_is_a_safetensors_file():
    wf = client.load_workflow()
    name = wf[client.LORA_NODE]["inputs"]["lora_name"]
    assert isinstance(name, str) and name, "lora_name is empty"
    assert name.endswith(".safetensors"), f"lora_name is not a .safetensors file: {name!r}"


def test_workflow_lora_name_is_not_the_unconfigured_placeholder():
    wf = client.load_workflow()
    name = wf[client.LORA_NODE]["inputs"]["lora_name"]
    assert name != PLACEHOLDER, (
        f"lora_name is the unconfigured placeholder ({PLACEHOLDER!r}). "
        "Edit daydream/images/workflows/painterly_room.json to point at "
        "the actual LoRA file you dropped into external/ComfyUI/models/loras/. "
        "See docs/gpu-and-models.md 'Image gen stack' for the current pick."
    )


def test_workflow_checkpoint_name_is_real():
    """Same check for the SDXL base checkpoint — a placeholder there would
    silently default to whatever ComfyUI shipped with."""
    wf = client.load_workflow()
    name = wf[client.CHECKPOINT_NODE]["inputs"]["ckpt_name"]
    assert isinstance(name, str) and name, "ckpt_name is empty"
    assert name.endswith(".safetensors"), f"ckpt_name is not a .safetensors file: {name!r}"
