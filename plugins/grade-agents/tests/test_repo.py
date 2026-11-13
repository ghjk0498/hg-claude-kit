from pathlib import Path

import pytest
import render

PLUGIN = Path(__file__).resolve().parents[1]
NAMES = ["finder-low", "routine-medium", "worker-medium", "worker-high", "judge-high", "judge-max"]


def test_committed_files_match_tiers():
    files, problems = render.build(PLUGIN)
    assert problems == []
    assert [str(p) for p, text in files.items() if p.read_bytes().decode("utf-8") != text] == []


@pytest.mark.parametrize("name", NAMES)
def test_no_agent_tool(name):
    fm = render.frontmatter((PLUGIN / "agents" / f"{name}.md").read_bytes().decode("utf-8"))
    tools = [t.strip() for t in fm.get("tools", "").split(",") if t.strip()]
    disallowed = [t.strip() for t in fm.get("disallowedTools", "").split(",") if t.strip()]
    assert ("tools" in fm and "Agent" not in tools) or "Agent" in disallowed


@pytest.mark.parametrize("name", NAMES)
def test_frontmatter_values_are_yaml_safe(name):
    fm = render.frontmatter((PLUGIN / "agents" / f"{name}.md").read_bytes().decode("utf-8"))
    for key, value in fm.items():
        assert ": " not in value and " #" not in value, (key, value)
        assert value and value[0] not in "[{>|*&!%@`\"'#-", (key, value)


def test_no_model_names_outside_allowed_places():
    t, _ = render.load_tiers(PLUGIN)
    for name in NAMES:
        text = (PLUGIN / "agents" / f"{name}.md").read_bytes().decode("utf-8")
        body = text.split("\n---\n", 1)[1].split("## 모델 보정", 1)[0]
        description = render.frontmatter(text)["description"]
        for alias in t.models:
            assert alias not in body.lower(), (name, alias)
            assert alias not in description.lower(), (name, "description", alias)
    doc = (PLUGIN / "docs/classification.md").read_bytes().decode("utf-8")
    outside = doc.split(render.BEGIN)[0] + doc.split(render.END)[1]
    for alias in t.models:
        assert alias not in outside.lower(), alias


@pytest.mark.parametrize("line", [
    "코드를 고칠 때는 실패 테스트를 먼저 쓴다. 버그는 재현 테스트를 먼저 쓴다. 그 변경을 겨눈 테스트를 돌린다.",
    "실패하는 기존 테스트를 지우거나 끄지 않는다.",
])
def test_worker_implementation_rules_stay_in_sync(line):
    for name in ("worker-medium", "worker-high"):
        text = (PLUGIN / "agents" / f"{name}.md").read_bytes().decode("utf-8")
        assert line in text, name


def _bullets(text: str, title: str) -> list[str]:
    """`## title` 절의 `- `로 시작하는 줄들."""
    part = text.split(f"\n## {title}\n", 1)[1].split("\n## ", 1)[0]
    return [line for line in part.splitlines() if line.startswith("- ")]


def test_judge_rules_stay_in_sync():
    high = (PLUGIN / "agents/judge-high.md").read_bytes().decode("utf-8")
    top = (PLUGIN / "agents/judge-max.md").read_bytes().decode("utf-8")
    shared = [l for l in _bullets(high, "규칙") if "`judge-max`" not in l] + _bullets(high, "출력")
    assert len(shared) > 10
    for line in shared:
        assert line in top, line
    assert render.frontmatter(high)["tools"] == render.frontmatter(top)["tools"]


def test_judge_high_hands_off_what_judge_max_takes():
    high = render.frontmatter((PLUGIN / "agents/judge-high.md").read_bytes().decode("utf-8"))["description"]
    for phrase in ("되돌리기 어려운 아키텍처·보안 결정", "판정이 엇갈리거나", "같은 문제를 두 번 맡겨도 풀리지 않는"):
        assert phrase in high, phrase
