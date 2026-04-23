"""`bin/game image-test` entry point.

Runs a single ComfyUI prompt through the same workflow JSON the room-
background generator uses, with optional --model and --lora overrides
so aesthetic A/B swaps stay one-liners (SPEC criterion 2's mitigation
of the painterly-vs-Turbo risk in the plan).

Output lives at ~/data/daydream/images/test/{safe-prompt}-{hash}.png.
ComfyUI must be running at config.comfyui_base_url() (default
http://localhost:8188); on failure the script exits 2 with a hint."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import sys
from pathlib import Path

from daydream import config
from daydream.images import client


def derive_out_path(prompt: str, root: Path | None = None) -> Path:
    """Deterministic path under ~/data/daydream/images/test/. Same prompt
    always lands at the same path so re-runs overwrite cleanly."""
    if root is None:
        root = config.data_dir() / "images" / "test"
    h = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:12]
    safe = "".join(c if c.isalnum() else "-" for c in prompt[:40]).strip("-") or "untitled"
    return root / f"{safe}-{h}.png"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="bin/game image-test",
        description="Generate one image via ComfyUI for aesthetic-A/B work.",
    )
    parser.add_argument("prompt", help="prompt text; the WHIMSY suffix is appended")
    parser.add_argument("--model", help="override checkpoint name in the workflow")
    parser.add_argument("--lora", help="override LoRA name in the workflow")
    parser.add_argument("--seed", type=int, default=0, help="KSampler seed (default 0)")
    parser.add_argument(
        "--out", type=Path, help="output path (default: derived from prompt)"
    )
    parser.add_argument(
        "--no-suffix",
        action="store_true",
        help="skip appending the WHIMSY prompt suffix (rarely what you want)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    out = args.out or derive_out_path(args.prompt)
    if args.no_suffix:
        full_prompt = args.prompt.strip()
    else:
        full_prompt = (args.prompt.strip() + " " + client.WHIMSY_PROMPT_SUFFIX).strip()

    try:
        path = asyncio.run(
            client.generate_to_path(
                prompt=full_prompt,
                out_path=out,
                model=args.model,
                lora=args.lora,
                seed=args.seed,
            )
        )
    except client.ComfyUIError as e:
        print(f"ComfyUI error: {e}", file=sys.stderr)
        print(
            f"Is ComfyUI running at {config.comfyui_base_url()}?",
            file=sys.stderr,
        )
        return 2
    print(str(path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
