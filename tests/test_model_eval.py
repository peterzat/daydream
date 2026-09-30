"""Unit tests for daydream/model_eval.py (the model bake-off harness).

The harness's live suites need a real endpoint and run on demand; these
tests cover the pure scoring rules and the compare/blind-sheet plumbing so a
refactor can't silently change what a bake-off measures."""

import json

import pytest

from daydream import model_eval

pytestmark = pytest.mark.tier_short


@pytest.mark.parametrize("text,slip", [
    ('Bell grins. "Did you see it?"', False),
    ("Bell laughs. ‘You found it!’", False),
    ("Mott's broom pauses. 'Your gear's here,' he says.", False),
    ("You lean on the broom. 'Hello.'", True),
    ("Tace looks at your hands.", True),
    ("I'm well, thank you. The clock still keeps time.", True),
])
def test_pov_slip_flags_second_person_outside_quotes(text, slip):
    assert model_eval._pov_slip(text) is slip


def test_sentence_count():
    assert model_eval._sentences("One. Two! Three?") == 3
    assert model_eval._sentences("'Hello,' she says. The lamp hums.") == 2


def test_parser_schema_enumerates_vocab_and_scope_ids():
    vocab = [{"name": "take"}, {"name": "look"}]
    scope = [{"id": "o-gear"}, {"id": "t-tace"}]
    schema = model_eval.parser_schema(vocab, scope)["json_schema"]["schema"]
    assert schema["properties"]["verb"]["enum"] == ["take", "look", "none"]
    ids = schema["properties"]["dobj_id"]["anyOf"][0]["enum"]
    assert ids == ["o-gear", "t-tace"]
    assert schema["additionalProperties"] is False


def test_parser_corpus_expectations_are_in_scope():
    """Every expected id in the corpus must exist in its scope, or the case
    can never pass and silently lowers every model's score."""
    scopes = {"bunny": model_eval.SCOPES["bunny"], "loft": model_eval.SCOPES["loft"],
              "wide": model_eval.SCOPES["wide"]}
    for text, _verb, dobj, iobj, scope in model_eval.PARSER_CASES:
        ids = {e["id"] for e in scopes[scope]}
        for want in (dobj, iobj):
            assert want is None or want in ids, (text, want)


def _fake_run(label: str, narrate: str) -> dict:
    return {
        "label": label,
        "suites": {
            "parser": {"score": 1.0, "cases": []},
            "dialogue": {"score": 1.0, "fallback_layers": {}, "runs": [
                {"npc": "Bell", "input": "hello", "ok": True, "narrate": narrate,
                 "layer": None},
            ]},
        },
        "latency": {"dialogue": {"p50_ms": 10, "p95_ms": 20, "mean_out_tokens": 5}},
    }


def test_compare_writes_a_consistent_blind_sheet(tmp_path):
    dirs = []
    for label, text in (("model-a", "Bell waves. 'Evening!'"),
                        ("model-b", "Bell nods. 'Hello.'")):
        d = tmp_path / label
        d.mkdir()
        (d / "results.json").write_text(json.dumps(_fake_run(label, text)))
        dirs.append(str(d))
    out = tmp_path / "cmp"
    rc = model_eval.main(["compare", *dirs, "--out", str(out)])
    assert rc == 0
    sheet = (out / "blind.md").read_text()
    key = json.loads((out / "blind_key.json").read_text())
    item = "dialogue | Bell | hello"
    assert f"### {item}" in sheet
    # The key maps each letter back to the run whose text sits beside it.
    for letter, label in key[item].items():
        text = "Bell waves. 'Evening!'" if label == "model-a" else "Bell nods. 'Hello.'"
        assert f"- **{letter}**: {text}" in sheet
    # Labels never leak into the sheet itself.
    assert "model-a" not in sheet and "model-b" not in sheet
    assert "| model-a |" in (out / "compare.md").read_text()


def test_subset_rerun_refuses_to_merge_a_different_model(tmp_path, monkeypatch, capsys):
    """A --suites re-run under a label holding another model's results would
    merge two models into one results.json. It must refuse before any endpoint
    work and leave the old file intact; the same model passes the check."""
    import httpx

    prior = tmp_path / "x" / "results.json"
    prior.parent.mkdir()
    prior.write_text(json.dumps({"label": "x", "model": "hosted_vllm/a", "suites": {}}))
    before = prior.read_bytes()
    probes = []

    def no_endpoint(url, **kw):
        probes.append(url)
        raise ConnectionError("no endpoint in tests")

    monkeypatch.setattr(httpx, "get", no_endpoint)
    # main() writes DAYDREAM_LLM_MODEL from --model; setenv restores it after.
    monkeypatch.setenv("DAYDREAM_LLM_MODEL", "hosted_vllm/a")
    run = ["run", "--label", "x", "--suites", "dialogue", "--out", str(tmp_path)]

    assert model_eval.main([*run, "--model", "hosted_vllm/b"]) == 2
    err = capsys.readouterr().err
    assert "refusing to merge" in err and "hosted_vllm/a" in err and "hosted_vllm/b" in err
    assert probes == [] and prior.read_bytes() == before

    assert model_eval.main([*run, "--model", "hosted_vllm/a"]) == 2
    err = capsys.readouterr().err
    assert "refusing" not in err and "endpoint unreachable" in err
    assert len(probes) == 1


# ---- canon suite + opener metric (SPEC 2026-09-26 criterion 10) -----------


def _item(item_id: str) -> dict:
    return next(i for i in model_eval.CANON["items"] if i["id"] == item_id)


@pytest.mark.parametrize("item_id,reply,bad", [
    # Real 2026-09-26 shipped-model replies (model-eval q35-9b-shipped).
    ("gear-seen", "Tace pauses. 'I found one tucked beneath the pendulum, waiting "
     "for the right hands,' they say.", True),
    ("gear-seen", "Bell tilts their head. 'I saw a small bright thing roll south, "
     "down toward the old well.'", False),
    ("gear-seen", "Mott leans on the broom. 'It isn't in the tin, friend. I've not "
     "seen it.'", False),
    # Scenery is not a claim: no gear referent in the sentence.
    ("gear-where", "Tace traces a line of brass dust on the workbench. 'It slipped "
     "away south, toward the well.'", False),
    ("gear-where", "Mott smiles. 'It slipped into the tin, little one.'", True),
    ("neighbors", "Tace smiles. 'The baker's daughter keeps bees in the garden.'", True),
    ("neighbors", "Bell smiles. 'Tace up in the loft, and Mott in the workshop.'", False),
    ("baker-trap", "Mott blinks. 'Oh yes, her bees hum all afternoon.'", True),
    ("baker-trap", "Mott tilts his head. 'There's no baker here, friend.'", False),
    ("well-where", "Bell points with the pole. 'South, past the last lantern.'", False),
    ("well-where", "Bell points. 'Just north of the square, love.'", True),
    ("tin", "Mott rattles it. 'Buttons, a bent key, a thimble.'", False),
    ("tin", "Mott opens the tin. 'And the escapement gear, of course.'", True),
])
def test_canon_contradiction_rules(item_id, reply, bad):
    item = _item(item_id)
    hits = model_eval.canon_contradictions(
        reply, item["contradicts"], sentence_must=item.get("sentence_must"))
    assert bool(hits) is bad, hits


def test_canon_pronoun_rule_reads_only_narration():
    they = model_eval.CANON["pronouns"]["Tace"]
    assert model_eval.canon_contradictions(
        "Tace sets down her loupe. 'Hello.'", [], they) == ["pronoun"]
    assert model_eval.canon_contradictions(
        "Tace sets down their loupe. 'She was here, he said.'", [], they) == []


def test_every_canon_item_names_a_known_npc_and_compiles():
    import re

    for item in model_eval.CANON["items"]:
        assert item["npcs"] and set(item["npcs"]) <= set(model_eval.DIALOGUE_NPCS)
        for pat in item["contradicts"]:
            re.compile(pat)


def test_opener_max_share():
    same = "Tace pauses, the scent of cedar oil and dust hanging soft."
    texts = [same, same + " More.", same, "Tace looks up from the bench, smiling now."]
    assert model_eval.opener_key(same) == "tace pauses the scent of cedar"
    assert model_eval.opener_max_share(texts) == 3
    assert model_eval.opener_max_share(["short one"]) == 0


def test_canon_scorer_judges_the_model_not_the_authored_gesture():
    """The gesture swap may splice in one of the NPC's authored drift lines;
    authored text is canon by construction and is not scored (the real
    2026-09-26 AFTER-run false positive), while the model's own words are."""
    item = _item("gear-seen")
    reply = ("Mott sets the tin back on the shelf and straightens it by a hair, so it "
             "sits just so. 'I have never seen the escapement gear at all.'")
    authored = model_eval.authored_lines("Mott")
    assert "Mott sets the tin back on the shelf and straightens it by a hair, so it sits just so." in authored
    assert model_eval.canon_contradictions(
        reply, item["contradicts"], sentence_must=item.get("sentence_must"))
    assert not model_eval.canon_contradictions(
        reply, item["contradicts"], sentence_must=item.get("sentence_must"), authored=authored)
    # A model-written claim still counts even beside an authored gesture.
    bad = ("Mott sets the tin back on the shelf and straightens it by a hair, so it "
           "sits just so. 'I found one tucked in my pocket.'")
    assert model_eval.canon_contradictions(
        bad, item["contradicts"], sentence_must=item.get("sentence_must"), authored=authored)


def test_a_run_measures_the_local_path_with_jev_off(monkeypatch, tmp_path):
    """Codereview 2026-09-30d: `bin/game` loads `.env`, so a dev key turned
    Jev on under model-eval and a local-model comparison was partly Jev's."""
    import os

    from daydream.jev import settings

    monkeypatch.setenv("DAYDREAM_JEV_API_KEY", "test-key")
    # Codereview 2026-09-30f: litellm's first import re-reads `.env` unless
    # LITELLM_MODE says production (conftest sets it; a real run does not).
    monkeypatch.delenv("LITELLM_MODE", raising=False)
    assert settings.enabled()
    seen = {}

    async def run(args):
        seen["jev"] = settings.enabled()
        seen["litellm_mode"] = os.environ.get("LITELLM_MODE")
        return 0

    monkeypatch.setattr(model_eval, "_run", run)
    assert model_eval.main(["run", "--label", "t", "--out", str(tmp_path)]) == 0
    assert seen == {"jev": False, "litellm_mode": "PRODUCTION"}
