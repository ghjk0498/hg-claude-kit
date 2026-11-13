import pytest

TIERS = '''checked = "2026-11-11"

[models]
haiku = "Haiku 5.5"
sonnet = "Sonnet 5.5"
opus = "Opus 5.5"
fable = "Fable 5.2"

[tiers.finder-low]
model = "haiku"
effort = "low"

[tiers.judge-high]
model = "opus"
effort = "high"
'''

CLASSIFICATION = "# 기준표\n\n앞\n\n<!-- tiers:begin -->\n옛 내용\n<!-- tiers:end -->\n\n뒤\n"


def agent(name, description="설명", extra="", body="# 본문\n"):
    return f"---\nname: {name}\ndescription: {description}\n{extra}---\n\n{body}"


@pytest.fixture
def make_root(tmp_path):
    def _make(tiers=TIERS, agents=None, classification=CLASSIFICATION):
        root = tmp_path / "plugin"
        (root / "agents").mkdir(parents=True)
        (root / "docs").mkdir()
        (root / "tiers.toml").write_bytes(tiers.encode("utf-8"))
        if agents is None:
            agents = {
                "finder-low": agent("finder-low", body="# 찾기\n\n## 모델 보정 (Haiku 5.5)\n\n- 규칙\n"),
                "judge-high": agent("judge-high", description="판단을 맡는다"),
            }
        for name, text in agents.items():
            (root / "agents" / f"{name}.md").write_bytes(text.encode("utf-8"))
        if classification is not None:
            (root / "docs" / "classification.md").write_bytes(classification.encode("utf-8"))
        return root
    return _make
