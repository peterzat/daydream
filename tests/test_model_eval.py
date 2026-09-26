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
