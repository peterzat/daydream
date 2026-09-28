"""The playbooks name real commands (docs/runbooks/README.md "Conventions").

An agent follows docs/runbooks/, docs/CLOUDFLARE-SETUP.md, the operator skills
and CLAUDE.md literally, so a verb that was renamed or never existed is a
broken step. This reads every `bin/game prod ...` / `bin/game edge ...` they
mention and checks it against the argument parsers in the code."""

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.tier_short

REPO = Path(__file__).resolve().parent.parent
DOCS = sorted([*(REPO / "docs" / "runbooks").glob("*.md"),
               REPO / "docs" / "CLOUDFLARE-SETUP.md", REPO / "docs" / "GOING-LIVE.md",
               REPO / "README.md", REPO / "CLAUDE.md",
               *(REPO / ".claude" / "skills").glob("*/SKILL.md")])


def _parser_names(path: Path) -> set[str]:
    """Subcommand names a module registers: `add_parser("x")` and the
    `for <var> in ("a", "b"):` loops that register several at once."""
    src = path.read_text()
    names = set(re.findall(r'add_parser\(\s*"([a-z][a-z-]*)"', src))
    for tup in re.findall(r"for \w+ in \(([^)]*)\):", src):
        names |= set(re.findall(r'"([a-z][a-z-]*)"', tup))
    return names


def _prod_verbs() -> set[str]:
    from daydream import prodctl

    return _parser_names(REPO / "daydream" / "prodctl.py") | set(prodctl.PASSTHROUGH)


def _mentions(pattern: str) -> list[tuple[str, str]]:
    out = []
    for doc in DOCS:
        for m in re.finditer(pattern, doc.read_text()):
            out.append((doc.relative_to(REPO).as_posix(), m.group(1)))
    return out


def test_the_runbooks_exist():
    assert (REPO / "docs" / "runbooks" / "README.md").exists()
    assert len(list((REPO / "docs" / "runbooks").glob("*.md"))) >= 8


def test_every_prod_verb_the_docs_name_exists():
    verbs = _prod_verbs()
    bad = [(d, v) for d, v in _mentions(r"bin/game prod ([a-z][a-z-]*)") if v not in verbs]
    # `--instance NAME` goes after the verb (the permission rules read the
    # verb first); a doc that puts it first teaches a form prodctl refuses.
    bad += [(d, "--instance first") for d, _ in _mentions(r"bin/game prod (--instance)")]
    assert not bad, f"unknown `bin/game prod` verbs: {bad}"


def test_every_edge_verb_the_docs_name_exists():
    verbs = _parser_names(REPO / "daydream" / "edge.py")
    bad = [(d, v) for d, v in _mentions(r"bin/game edge ([a-z][a-z-]*)") if v not in verbs]
    assert not bad, f"unknown `bin/game edge` verbs: {bad}"


def test_every_prod_world_account_and_invite_subverb_exists():
    world = _parser_names(REPO / "daydream" / "admin.py") | {"reset", "refresh", "patch"}
    people = _parser_names(REPO / "daydream" / "accounts_cli.py")
    bad = [(d, v) for d, v in _mentions(r"bin/game prod world ([a-z][a-z-]*)") if v not in world]
    bad += [(d, v) for d, v in _mentions(r"bin/game prod (?:account|invite) ([a-z][a-z-]*)")
            if v not in people]
    assert not bad, f"unknown sub-verbs: {bad}"


def test_the_runbooks_links_resolve():
    broken = []
    for doc in [*(REPO / "docs" / "runbooks").glob("*.md"), REPO / "docs" / "CLOUDFLARE-SETUP.md"]:
        for link in re.findall(r"\]\(([^)#\s]+)", doc.read_text()):
            if link.startswith(("http://", "https://", "mailto:")):
                continue
            if not (doc.parent / link).exists():
                broken.append((doc.name, link))
    assert not broken, broken


def test_the_parsers_are_read_correctly():
    """Guard the guard: known verbs are found, so an empty set can't pass."""
    assert {"status", "check", "deploy", "sleep", "wake", "world", "invite"} <= _prod_verbs()
    assert {"status", "deploy", "sleep", "wake", "secrets"} <= _parser_names(
        REPO / "daydream" / "edge.py")


def test_the_permission_template_asks_before_every_dangerous_verb():
    """docs/claude-settings.local.example.json is what a fork copies to give
    the agent its standing grant; it must ask before each verb the docs say
    always prompts, and match verbs first (prodctl refuses a leading
    --instance, so a prefix rule cannot be walked around)."""
    import json

    rules = json.loads((REPO / "docs" / "claude-settings.local.example.json").read_text())
    allow, ask = rules["permissions"]["allow"], rules["permissions"]["ask"]
    assert "Bash(bin/game prod *)" in allow and "Bash(bin/game edge *)" in allow
    for verb in ("invite reset", "account role", "account create", "account cli-cookie",
                 "account delete", "world reset", "world delete", "world restore",
                 "world snapshot-restore", "world restore-backup", "world load",
                 "root units --apply", "root env set"):
        assert any(r.startswith(f"Bash(bin/game prod {verb}") for r in ask), verb
    assert not any("--instance" in r for r in allow + ask)
