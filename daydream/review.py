"""bin/game review — one offline artifact that batches every qualitative check.

Loads `worlds/bunny.json` into a throwaway temp DB (NO live server, NO live.db
touch, NO API key), renders every aesthetic anchor (including the forge) and a
fresh `talk` sample for each authored NPC, and writes a single self-contained
`index.html` contact sheet. The operator reviews all the qualitative checks in
ONE glance instead of a live reset plus a browser session per check, which is
the whole point: keep precious eyes-on time for gameplay, not mechanics.

Engines: ComfyUI (images) + vLLM (voices) — the same local engines the game
uses. Either being down degrades that section to a short note rather than
aborting the whole sheet (the project's graceful-failure ethos).

The aesthetic check is done by Claude Code (the agent running this in the TUI),
NOT by any cloud API: after this writes the sheet, the agent Reads each rendered
PNG under the output dir and grades it against `WHIMSY.md`, recording the
verdict. This is the sanctioned design-time use of Opus-in-the-TUI (CLAUDE.md
generation policy) — there is no API key and no `litellm` vision call anywhere
in the runtime or the tooling.

Invoked via `bin/game review` (thin shell wrapper shelling to
`python -m daydream.review`). The image/voice renders need the GPU; in dev the
agent may take the GPU freely (stop the server if needed) per the CLAUDE.md
dev-mode lifecycle policy.
"""

from __future__ import annotations

import argparse
import asyncio
import html
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import httpx

from daydream import admin, config, db, events

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BUNNY_JSON = PROJECT_ROOT / "worlds" / "bunny.json"
AESTHETICS_DIR = PROJECT_ROOT / "tests" / "drift" / "aesthetics"
BASELINES_DIR = PROJECT_ROOT / "tests" / "baselines"

# Same probe applied to each NPC so the operator compares voices on identical
# input (distinctness reads at a glance). Benign inputs: no banlist trip.
REVIEW_INPUTS = ["Hello.", "What are you working on?"]
ACTOR_ID = "t-review-visitor"  # phantom speaker; memory is fail-closed
PROBE_TIMEOUT_SECONDS = 2.0


# ---- engine reachability (same 2s pattern as the test suite) ------------


def _comfyui_reachable() -> bool:
    url = config.comfyui_base_url().rstrip("/") + "/system_stats"
    try:
        return httpx.get(url, timeout=PROBE_TIMEOUT_SECONDS).status_code < 500
    except httpx.HTTPError:
        return False


def _vllm_reachable() -> bool:
    url = config.llm_base_url().rstrip("/") + "/models"
    try:
        return httpx.get(url, timeout=PROBE_TIMEOUT_SECONDS).status_code < 500
    except httpx.HTTPError:
        return False


# ---- image anchors ------------------------------------------------------


async def _render_anchors(out_dir: Path) -> list[dict]:
    """Render every aesthetic anchor into out_dir as <name>.png (so the sheet
    is self-contained). The agent grades each PNG against WHIMSY.md afterward
    by Reading it in the TUI; there is no in-process aesthetic scorer."""
    from daydream.gpu import arbiter
    from daydream.images import client as image_client

    results: list[dict] = []
    for f in sorted(AESTHETICS_DIR.glob("*.json")):
        spec = json.loads(f.read_text())
        name = spec["name"]
        target = image_client.EphemeralTarget(
            name=name,
            prompt=spec["prompt"],
            with_whimsy_suffix=True,
            out_path=out_dir / f"{name}.png",
        )
        async with arbiter.acquire():
            path = await image_client.generate_image(target)
        results.append({
            "name": name,
            "prompt": spec["prompt"],
            "file": Path(path).name,
            "tracked": (BASELINES_DIR / f"image_{name}.golden.json").exists(),
        })
    return results


# ---- NPC voices ---------------------------------------------------------


def _narrate_since(before_seq: int) -> str:
    texts = [
        e.payload.get("text", "")
        for e in events.fetch_since(before_seq)
        if e.kind == "narrate"
    ]
    return "\n".join(t for t in texts if t) or "(no narrate emitted)"


async def _render_voices() -> list[dict]:
    """Dispatch REVIEW_INPUTS through each authored NPC's `talk` dialogue
    against the loaded bunny world. Uses the SHIPPED worlds/bunny.json prompts
    (installed as hidden dialogue skills by load_world), so the capture
    reflects what the game actually says."""
    from daydream import objects, toons
    from daydream.skills import data as data_skills

    out: list[dict] = []
    for npc in toons.get_npcs():
        skill_name = objects.get_property(npc.id, "dialogue")
        if not skill_name:
            continue  # e.g. Wren is a wandering toon with no dialogue binding
        room_id = npc.current_room_id
        samples: list[dict] = []
        for player_input in REVIEW_INPUTS:
            before = events.max_seq()
            try:
                await data_skills.execute_by_name(
                    skill_name, ACTOR_ID, room_id, player_input
                )
                narrate = _narrate_since(before)
            except Exception as e:  # one bad turn shouldn't drop the NPC
                narrate = f"(dispatch error: {e})"
            samples.append({"input": player_input, "narrate": narrate})
        out.append({"name": npc.name, "seed": npc.seed, "samples": samples})
    return out


# ---- HTML composition ---------------------------------------------------

_CSS = """
  :root { color-scheme: light; }
  body { background:#f6f3ec; color:#3a4a44; font:16px/1.5 -apple-system,
    Segoe UI, Roboto, sans-serif; margin:0; padding:2rem; max-width:1100px;
    margin-inline:auto; }
  h1 { color:#5a7a6a; font-weight:600; }
  h2 { color:#5a7a6a; border-bottom:1px solid #d8d2c2; padding-bottom:.3rem;
    margin-top:2.5rem; }
  .meta { color:#7a857d; font-size:.9rem; }
  .note { background:#fbf9f3; border:1px solid #d8d2c2; border-radius:8px;
    padding:1rem; color:#7a6a4a; }
  .grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(320px,1fr));
    gap:1.2rem; }
  .card { background:#fbf9f3; border:1px solid #d8d2c2; border-radius:10px;
    overflow:hidden; }
  .card img { width:100%; display:block; background:#eee; }
  .card .body { padding:.8rem 1rem; }
  .card .name { color:#5a7a6a; font-weight:600; }
  .seed { font-size:.85rem; color:#7a857d; margin:.4rem 0; }
  .tag { display:inline-block; font-size:.75rem; padding:.1rem .5rem;
    border-radius:999px; background:#e8efe9; color:#5a7a6a; }
  .npc { background:#fbf9f3; border:1px solid #d8d2c2; border-radius:10px;
    padding:1rem 1.2rem; margin-bottom:1.2rem; }
  .npc .name { color:#5a7a6a; font-weight:600; font-size:1.1rem; }
  blockquote { border-left:3px solid #c8a06e; margin:.5rem 0; padding:.2rem 1rem;
    color:#3a4a44; }
  .you { color:#7a857d; font-style:italic; }
  ol li { margin:.4rem 0; }
  code { background:#efece3; padding:.1rem .3rem; border-radius:4px; }
"""


def _e(text: str) -> str:
    return html.escape(str(text))


def _compose_html(
    images: list[dict],
    voices: list[dict],
    image_note: str | None,
    voice_note: str | None,
) -> str:
    when = datetime.now().strftime("%Y-%m-%d %H:%M")
    p: list[str] = []
    p.append("<!doctype html><html lang=en><head><meta charset=utf-8>")
    p.append("<meta name=viewport content='width=device-width,initial-scale=1'>")
    p.append("<title>daydream — review sheet</title>")
    p.append(f"<style>{_CSS}</style></head><body>")
    p.append("<h1>daydream — review sheet</h1>")
    p.append(
        f"<p class=meta>Generated {_e(when)} from <code>worlds/bunny.json</code> "
        "into a throwaway temp DB. No live server, no live.db touch. One glance "
        "covers the qualitative checks this turn would otherwise eyeball "
        "separately.</p>"
    )

    # The one irreducible live glance, batched in alongside the renders.
    p.append("<h2>Browser checklist — the one live glance</h2>")
    p.append(
        "<p class=meta>The connection-state overlay is the only check that needs "
        "a running server + browser (its logic is source-scan tested; the visual "
        "is irreducibly human). Do these once:</p>"
    )
    p.append("<ol>")
    p.append(
        "<li>With the game up and a tab open, run <code>bin/game deploy</code> "
        "(or a <code>down</code>/<code>up</code> cycle). Confirm a single calm "
        "<em>“the dream is sleeping…”</em> overlay appears (not a growing pile of "
        "disconnect lines) and the view restores itself when the server returns, "
        "no manual refresh.</li>"
    )
    p.append(
        "<li>Run <code>bin/game world swap &lt;target.db&gt;</code>. Confirm a "
        "brief <em>“the dream shifts…”</em> beat resolves into the new world's "
        "fresh snapshot.</li>"
    )
    p.append("</ol>")

    # Images.
    p.append("<h2>Image aesthetics</h2>")
    if image_note:
        p.append(f"<p class=note>{_e(image_note)}</p>")
    else:
        p.append("<div class=grid>")
        for im in images:
            tracked = (
                '<span class="tag">perceptual golden ✓</span>'
                if im["tracked"]
                else '<span class="tag">no golden yet — ratify to track</span>'
            )
            p.append("<div class=card>")
            p.append(f'<img src="{_e(im["file"])}" alt="{_e(im["name"])}">')
            p.append("<div class=body>")
            p.append(f'<div class=name>{_e(im["name"])}</div>')
            p.append(f"<div class=seed>{_e(im['prompt'])}</div>")
            p.append(f"<div>{tracked}</div>")
            p.append("</div></div>")
        p.append("</div>")

    # Voices.
    p.append("<h2>NPC voices</h2>")
    p.append(
        "<p class=meta>Same two inputs to each NPC, so distinctness reads at a "
        "glance: Rook laconic, Iris bookish, Bram gentle.</p>"
    )
    if voice_note:
        p.append(f"<p class=note>{_e(voice_note)}</p>")
    else:
        for npc in voices:
            p.append("<div class=npc>")
            p.append(f'<div class=name>{_e(npc["name"])}</div>')
            p.append(f"<div class=seed>{_e(npc['seed'])}</div>")
            for s in npc["samples"]:
                p.append(f'<p class=you>you: {_e(s["input"])}</p>')
                for line in s["narrate"].splitlines() or [""]:
                    p.append(f"<blockquote>{_e(line)}</blockquote>")
            p.append("</div>")

    p.append("<h2>The aesthetic review (agent, in the TUI)</h2>")
    p.append(
        "<p class=meta>No cloud API grades these. The Claude Code agent Reads each "
        "PNG in this directory and grades it against <code>WHIMSY.md</code> "
        "(cozy soft watercolor; anvil/bellows actually legible for the forge; no "
        "banned moods), recording the verdict. Ratify a perceptual golden only "
        "once its render reads right: <code>bin/game test long -k &lt;name&gt;</code> "
        "writes the latest, then <code>mv tests/baselines/image_&lt;name&gt;.latest.json "
        "tests/baselines/image_&lt;name&gt;.golden.json</code>. Keep a sheet worth "
        "keeping by copying it under <code>docs/pretty/</code>.</p>"
    )
    p.append("</body></html>")
    return "\n".join(p)


# ---- orchestration ------------------------------------------------------


async def _main_async(out_dir: Path) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    comfy = _comfyui_reachable()
    vllm = _vllm_reachable()

    images: list[dict] = []
    voices: list[dict] = []
    image_note: str | None = None
    voice_note: str | None = None

    if comfy:
        images = await _render_anchors(out_dir)
    else:
        image_note = (
            "ComfyUI unreachable; anchor renders skipped. "
            "Start it with `bin/game comfyui-up`."
        )

    if vllm:
        # Hermetic tmp world: the voice capture reflects the CHECKED-IN
        # worlds/bunny.json, never the operator's live DB.
        saved_data_dir = os.environ.get("DAYDREAM_DATA_DIR")
        with tempfile.TemporaryDirectory(prefix="review-") as tmp:
            tmp_path = Path(tmp)
            os.environ["DAYDREAM_DATA_DIR"] = str(tmp_path)
            world_dir = tmp_path / f"worlds-{config.env()}"
            world_dir.mkdir(parents=True, exist_ok=True)
            out_db = world_dir / "live.db"
            try:
                db.close_db()
                events.reset_subscribers()
                rc = admin.main(["load", str(BUNNY_JSON), "--output", str(out_db)])
                if rc != 0:
                    voice_note = f"world load failed (rc={rc}); voice samples skipped."
                else:
                    db.close_db()
                    events.reset_subscribers()
                    db.init_live(path=out_db, migrations_dir=config.MIGRATIONS_DIR)
                    voices = await _render_voices()
            finally:
                db.close_db()
                events.reset_subscribers()
                if saved_data_dir is None:
                    os.environ.pop("DAYDREAM_DATA_DIR", None)
                else:
                    os.environ["DAYDREAM_DATA_DIR"] = saved_data_dir
    else:
        voice_note = (
            "vLLM unreachable; voice samples skipped. "
            "Start it with `bin/game vllm-up`."
        )

    (out_dir / "index.html").write_text(_compose_html(images, voices, image_note, voice_note))
    out_path = out_dir / "index.html"
    print(f"[review] wrote {out_path}")
    if image_note:
        print(f"[review] {image_note}", file=sys.stderr)
    if voice_note:
        print(f"[review] {voice_note}", file=sys.stderr)
    return 0


def _default_out_dir() -> Path:
    ts = datetime.now().strftime("%Y-%m-%dT%H%M%S")
    return config.data_dir() / "reviews" / ts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="daydream.review")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="output dir for the review artifact (default: "
        "~/data/daydream/reviews/<timestamp>/)",
    )
    args = parser.parse_args(argv)
    out_dir = args.out_dir or _default_out_dir()
    return asyncio.run(_main_async(out_dir))


if __name__ == "__main__":
    sys.exit(main())
