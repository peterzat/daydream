"""Regression: web/assets/main.js linkifyEntities must not nest spans or leak
object ids when one in-scope alias overlaps another. The 'forge-rook' bug:
Rook's aliases 'the forge-keeper' + 'keeper' made the per-alias iterative
replace re-match 'keeper' INSIDE the span it had inserted for 'the
forge-keeper', nesting spans whose markup surfaced `rook-<id>">` in the
rendered text. This runs the REAL function from main.js under node; skipped
where node is unavailable."""

import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.tier_short

MAIN_JS = Path(__file__).resolve().parent.parent / "web" / "assets" / "main.js"

_NODE_HARNESS = r"""
const fs = require("fs");
const src = fs.readFileSync(process.argv[2], "utf8");  // argv: [node, script, MAIN_JS]
// \b after the name so "escape" doesn't also match "escapeRegex".
function grab(name){
  const m = src.match(new RegExp("function " + name + "\\b[\\s\\S]*?\\n}"));
  if (!m) throw new Error("function not found in main.js: " + name);
  return m[0];
}
const ctx = grab("escape") + "\n" + grab("escapeRegex") + "\n" + grab("linkifyEntities");
// Overlapping aliases: the shorter ("keeper") is a substring of the longer
// ("the forge-keeper"), and the text leads with the longer one.
const text = "You see Rook: hair in a kerchief. the forge-keeper; quiet; keeps sketches.";
const ents = [
  {alias: "the forge-keeper", object_id: "rook-44210a17"},
  {alias: "keeper", object_id: "rook-44210a17"},
];
// IIFE so main.js's `function escape` shadows node's legacy global escape().
const out = eval("(function(){" + ctx + "\nreturn linkifyEntities(" +
  JSON.stringify(text) + "," + JSON.stringify(ents) + ");})()");
const visible = out.replace(/<[^>]+>/g, "");
const fail = [];
if (/entity-link[^>]*>[^<]*<span[^>]*entity-link/.test(out)) fail.push("nested entity-link spans");
if (visible !== text) fail.push("visible text altered: " + JSON.stringify(visible));
if (visible.includes("rook-44210a17") || visible.includes('">')) fail.push("id/markup leaked into visible text");
// Playtest 2026-09-28b/c: a person's alias links only as a name, and half of
// a hyphened word is not an alias ("case" in "case-key").
const run = (t, e) => eval("(function(){" + ctx + "\nreturn linkifyEntities(" +
  JSON.stringify(t) + "," + JSON.stringify(e) + ");})()");
const hy = run("The case-key turns in the case.", [{alias: "case", object_id: "o-case"}]);
if ((hy.match(/entity-link/g) || []).length !== 1 || !/case-key/.test(hy.replace(/<[^>]+>/g, "")))
  fail.push("hyphened word linked: " + hy);
if (/entity-link/.test(run("the way an hour waits", [{alias: "hour", object_id: "t-x", kind: "toon"}])))
  fail.push("a person's alias linked as a common word");
if (!/entity-link/.test(run("The Hour waits", [{alias: "hour", object_id: "t-x", kind: "toon"}])))
  fail.push("a person's alias did not link as a name");
// The boundary before a word is matched, not looked behind: back-to-back
// mentions sharing one space both link, and the space survives.
const two = run("case case", [{alias: "case", object_id: "o-case"}]);
if ((two.match(/entity-link/g) || []).length !== 2 || two.replace(/<[^>]+>/g, "") !== "case case")
  fail.push("back-to-back mentions: " + two);
if (fail.length) { console.error("FAIL: " + fail.join("; ")); process.exit(1); }
console.log("OK");
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_linkify_no_nested_spans_or_id_leak_for_overlapping_aliases(tmp_path):
    script = tmp_path / "linkify_check.js"
    script.write_text(_NODE_HARNESS)
    r = subprocess.run(
        ["node", str(script), str(MAIN_JS)],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert r.returncode == 0, f"linkify regression:\nstdout={r.stdout}\nstderr={r.stderr}"
    assert "OK" in r.stdout


def test_browser_js_has_no_regex_lookbehind():
    # Safari before 16.4 (iOS/iPadOS 15 and older) cannot parse a regex
    # lookbehind: the RegExp constructor throws, and a throw in linkifying
    # stops the reading column rendering (codereview 2026-09-28i). Named
    # groups, "(?<name>", are fine there and are not flagged.
    for js in sorted(MAIN_JS.parent.glob("*.js")):
        src = js.read_text()
        for token in ("(?<=", "(?<!"):
            assert token not in src, f"{js.name} uses a regex lookbehind ({token})"
