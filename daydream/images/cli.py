"""`bin/game image-test` entry point.

Routes through the unified `daydream.images.client.generate_image` with an
EphemeralTarget so the aesthetic A/B path shares all plumbing with the
room-background path. Acquires the GPU arbiter for safety in case vLLM
also happens to be running.

Output lives at ~/data/daydream/images/ephemeral/{safe-name}-{prompt-hash}.png
(deterministic per-prompt so re-runs overwrite, which is what A/B work
wants). ComfyUI must be running at config.comfyui_base_url() (default
http://localhost:8188); on failure the script exits 2 with a hint."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from daydream import config
from daydream.gpu import arbiter
from daydream.images import client


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
    target = client.EphemeralTarget(
        name=args.prompt,
        prompt=args.prompt,
        with_whimsy_suffix=not args.no_suffix,
        out_path=args.out,
    )

    async def _run() -> Path:
        async with arbiter.acquire():
            return await client.generate_image(
                target,
                model=args.model,
                lora=args.lora,
                seed=args.seed,
            )

    try:
        path = asyncio.run(_run())
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
