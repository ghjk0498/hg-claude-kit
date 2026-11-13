import pytest
import render
from .conftest import agent, TIERS, CLASSIFICATION


def test_inserts_before_closing():
    out = render.render_agent(agent("a"), "haiku", "low")
    assert out == "---\nname: a\ndescription: 설명\nmodel: haiku\neffort: low\n---\n\n# 본문\n"


def test_replaces_existing_in_place():
    src = agent("a", extra="model: opus\ntools: Read, Grep\neffort: max\n")
    out = render.render_agent(src, "haiku", "low")
    assert out == "---\nname: a\ndescription: 설명\nmodel: haiku\ntools: Read, Grep\neffort: low\n---\n\n# 본문\n"


def test_body_untouched():
    src = agent("a", body="# 본문\n\nmodel: opus\neffort: max\n---\n")
    out = render.render_agent(src, "haiku", "low")
    assert out.endswith("# 본문\n\nmodel: opus\neffort: max\n---\n")


def test_idempotent():
    once = render.render_agent(agent("a"), "haiku", "low")
    assert render.render_agent(once, "haiku", "low") == once


@pytest.mark.parametrize("src", [
    "# 제목\n\n본문\n",                                   # ---로 시작하지 않음
    "---\nname: a\ndescription: 설명\n\n# 본문\n",        # 닫는 --- 없음
    agent("a").replace("\n", "\r\n"),                     # CRLF
    agent("a", extra="model: opus\nmodel: haiku\n"),      # model: 줄이 둘
    agent("a", extra="effort: low\neffort: high\n"),      # effort: 줄이 둘
])
def test_rejects_bad_format(src):
    with pytest.raises(ValueError):
        render.render_agent(src, "haiku", "low")


def test_frontmatter_reads_single_line_values():
    fm = render.frontmatter(agent("a", description="찾기를 맡는다", extra="tools: Read, Grep\n"))
    assert fm == {"name": "a", "description": "찾기를 맡는다", "tools": "Read, Grep"}


def test_compensation_versions():
    body = "# 본문\n\n## 모델 보정 (Haiku 5.5)\n\n- 규칙\n\n## 규칙\n\n## 모델 보정 (Sonnet 5.5)\n"
    assert render.compensation_versions(agent("a", body=body)) == ["Haiku 5.5", "Sonnet 5.5"]


def test_compensation_ignores_frontmatter_and_none():
    assert render.compensation_versions(agent("a")) == []


BLOCK = """<!-- tiers:begin -->
| 에이전트 | model | effort | 확인한 버전 |
|---|---|---|---|
| `finder-low` | `haiku` | `low` | Haiku 5.5 |
| `judge-high` | `opus` | `high` | Opus 5.5 |

확인한 날: 2026-11-11
<!-- tiers:end -->"""


def test_block(make_root):
    t, _ = render.load_tiers(make_root())
    assert render.render_block(t) == BLOCK


def test_build_ok(make_root):
    root = make_root()
    files, problems = render.build(root)
    assert problems == []
    assert set(files) == {root / "agents/finder-low.md", root / "agents/judge-high.md", root / "docs/classification.md"}
    assert "model: haiku\neffort: low\n---" in files[root / "agents/finder-low.md"]
    assert files[root / "docs/classification.md"] == "# 기준표\n\n앞\n\n" + BLOCK + "\n\n뒤\n"


def problems_of(root):
    files, problems = render.build(root)
    assert problems
    return "\n".join(problems)


def test_check1_extra_file(make_root):
    root = make_root()
    (root / "agents/extra.md").write_bytes(agent("extra").encode())
    assert "짝" in problems_of(root)


def test_check1_missing_file(make_root):
    root = make_root()
    (root / "agents/finder-low.md").unlink()
    assert "짝" in problems_of(root)


def test_check1_name_mismatch(make_root):
    root = make_root(agents={"finder-low": agent("finder"),
                             "judge-high": agent("judge-high", description="판단을 맡는다")})
    assert "name" in problems_of(root)


def test_check4_stale_compensation(make_root):
    root = make_root(tiers=TIERS.replace('haiku = "Haiku 5.5"', 'haiku = "Haiku 6"'))
    out = problems_of(root)
    assert "다시 볼 것" in out and "finder-low" in out and "Haiku 5.5" in out


@pytest.mark.parametrize("text", [
    "# 기준표\n",                                                        # 표시 없음
    "<!-- tiers:end -->\n<!-- tiers:begin -->\n",                        # 순서 뒤집힘
    CLASSIFICATION + "<!-- tiers:begin -->\n<!-- tiers:end -->\n",       # 둘씩
    None,                                                                # 파일 없음
])
def test_check5_markers(make_root, text):
    assert "tiers:begin" in problems_of(make_root(classification=text))


def test_bad_agent_format_is_a_problem(make_root):
    root = make_root(agents={"finder-low": "# 제목\n",
                             "judge-high": agent("judge-high", description="판단을 맡는다")})
    assert "finder-low" in problems_of(root)


def snapshot(root):
    return {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_main_writes(make_root):
    root = make_root()
    assert render.main([], root) == 0
    assert "model: opus\neffort: high\n---" in (root / "agents/judge-high.md").read_text()
    assert BLOCK in (root / "docs/classification.md").read_text()
    assert render.main(["--check"], root) == 0


def test_main_all_or_nothing(make_root, capsys):
    root = make_root(tiers=TIERS.replace('haiku = "Haiku 5.5"', 'haiku = "Haiku 6"'))
    before = snapshot(root)
    assert render.main([], root) == 1
    assert snapshot(root) == before
    assert "다시 볼 것" in capsys.readouterr().out


def test_main_bad_tiers_no_traceback(make_root, capsys):
    root = make_root(tiers="checked = [")
    before = snapshot(root)
    assert render.main([], root) == 1
    assert snapshot(root) == before
    assert "tiers.toml" in capsys.readouterr().out


def test_check_reports_drift_without_writing(make_root, capsys):
    root = make_root()
    before = snapshot(root)
    assert render.main(["--check"], root) == 1
    assert snapshot(root) == before
    assert "finder-low.md" in capsys.readouterr().out


def test_main_twice_same(make_root):
    root = make_root()
    render.main([], root)
    once = snapshot(root)
    assert render.main([], root) == 0
    assert snapshot(root) == once


def test_main_warns_but_succeeds(make_root, capsys):
    root = make_root(tiers='subagent_default = "sonnet"\n' + TIERS)
    assert render.main([], root) == 0
    assert "subagent_default" in capsys.readouterr().err
