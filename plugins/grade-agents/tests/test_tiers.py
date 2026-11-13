import render
from .conftest import TIERS


def test_valid(make_root):
    t, problems = render.load_tiers(make_root())
    assert problems == []
    assert t.checked == "2026-11-11"
    assert not hasattr(t, "gated") and not hasattr(t, "subagent_default")
    assert t.models["haiku"] == "Haiku 5.5"
    assert list(t.tiers.items()) == [("finder-low", ("haiku", "low")), ("judge-high", ("opus", "high"))]


def bad(make_root, old, new):
    t, problems = render.load_tiers(make_root(tiers=TIERS.replace(old, new)))
    assert t is None
    return "\n".join(problems)


def test_unknown_model(make_root):
    assert "[models]에 없" in bad(make_root, 'model = "haiku"', 'model = "best"')


def test_fable_tier_allowed(make_root):
    root = make_root(tiers=TIERS.replace('model = "opus"', 'model = "fable"'))
    t, problems = render.load_tiers(root)
    assert problems == [] and t.tiers["judge-high"] == ("fable", "high")


def test_leftover_gate_keys_ignored(make_root):
    root = make_root(tiers='gated = ["fable"]\nsubagent_default = "sonnet"\n' + TIERS)
    t, problems = render.load_tiers(root)
    assert problems == [] and set(t.tiers) == {"finder-low", "judge-high"}


def test_bad_effort(make_root):
    assert "effort" in bad(make_root, 'effort = "low"', 'effort = "ultra"')


def test_toml_syntax_error(make_root):
    assert "tiers.toml" in bad(make_root, 'checked = "2026-11-11"', 'checked = [')


def test_missing_models_table(make_root):
    t, problems = render.load_tiers(make_root(tiers=TIERS.split("[models]")[0] + "[tiers.a]\nmodel = \"x\"\neffort = \"low\"\n"))
    assert t is None and problems


def test_missing_file(tmp_path):
    t, problems = render.load_tiers(tmp_path)
    assert t is None and "tiers.toml" in "\n".join(problems)


def test_unknown_keys_warned(make_root):
    root = make_root(tiers='gated = ["fable"]\n' + TIERS.replace('effort = "low"', 'effort = "low"\nmdoel = "opus"'))
    warns = render.unknown_keys(root)
    assert warns == [
        "경고: tiers.toml의 gated는 쓰지 않는 키다",
        "경고: tiers.toml의 tiers.finder-low.mdoel는 쓰지 않는 키다",
    ]


def test_no_warnings_for_known_keys(make_root):
    assert render.unknown_keys(make_root()) == []
