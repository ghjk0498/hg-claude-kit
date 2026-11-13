# grade-agents Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 작업량 등급 서브에이전트 5종을 `plugins/grade-agents/` 플러그인으로 만들고, 모델 배정을 `tiers.toml` 하나에서 생성하며, 승인이 필요한 모델(Fable)을 권한 ask 규칙으로 막는다.

**Architecture:** `tiers.toml`이 등급 → model·effort의 유일한 원본이다. `scripts/render.py`가 그 표를 읽어 `agents/*.md`의 frontmatter 두 줄과 `docs/classification.md`의 표 구간을 채운다(전부 쓰거나 아무것도 안 씀). `scripts/gate.py`가 settings.json 하나에 ask 규칙과 `CLAUDE_CODE_SUBAGENT_MODEL`을 병합한다.

**Tech Stack:** Python 3.12(`uv`), 표준 라이브러리만(`tomllib`, `json`, `argparse`), pytest.

**Spec:** `docs/superpowers/specs/2026-11-11-grade-agents-design.md` — 실행자는 이 계획과 함께 읽는다. 에이전트 본문의 규칙 문장은 spec의 「에이전트」 절이 원문이다.

## Global Constraints

- 모든 경로는 저장소 루트(`hg-claude-kit/`) 기준이다. 명령은 따로 적지 않으면 `plugins/grade-agents/`에서 돌린다.
- 스크립트는 표준 라이브러리만 쓴다. `pyproject.toml`의 `dependencies`는 비운다.
- 스크립트는 `uv run python scripts/<이름>.py`로 돌린다. Python 3.11 미만으로 돌리면 `Python 3.11 이상이 필요하다. uv run python scripts/<이름>.py 로 돌린다.`를 stderr에 찍고 종료 코드 2로 끝난다. 이 안내가 3.9에서 찍히려면 파일이 3.9에서 구문 분석돼야 한다: 맨 위에 `from __future__ import annotations`를 두고, 버전 검사를 `import tomllib`보다 앞에 두고, `match` 문을 쓰지 않는다.
- 파일은 `read_bytes().decode("utf-8")`로 읽고 `write_bytes`로 쓴다. 줄 끝을 바꾸지 않는다.
- effort 값은 `low` · `medium` · `high` · `xhigh` · `max`뿐이다.
- 생성 구간 표시는 정확히 `<!-- tiers:begin -->`과 `<!-- tiers:end -->`다.
- 사람이 쓰는 글(에이전트 본문, 기준표의 생성 구간 밖)에는 모델 이름을 적지 않는다. 예외는 `judge-high`의 description과 `## 모델 보정 (…)` 블록이다.
- 에이전트 본문과 문서는 한국어 평서문(「~다」)으로 쓴다.
- 테스트는 임시 폴더에 만든 가짜 플러그인 트리로 돌린다. 실제 `~/.claude/settings.json`을 읽거나 쓰는 테스트는 없다.
- 커밋은 `grade-agents` 브랜치에 한다. `main`에 직접 커밋하지 않고 push하지 않는다. 메시지는 기존 관례(`grade-agents: 한 줄 요약`, 한국어)를 따르고 끝에 실제로 돌고 있는 모델 이름으로 `Co-Authored-By: Claude <모델 이름> <noreply@anthropic.com>`을 붙인다.

## Review Focus

spec이 말하지 않았지만 쓰는 사람이 부딪힐 입력이다. 각 줄의 테스트는 괄호 안 Task에 있다.

1. `tiers.toml`이 TOML 문법 오류이거나 `[models]`·`[tiers]`·`gated`가 빠졌다 → traceback 없이 문제 한 줄을 찍고 종료 코드 1, 아무 파일도 안 바뀐다. (Task 1, 3)
2. frontmatter 값에 `: `(콜론+공백)나 ` #`이 들어가 YAML이 깨진다 → 저장소 테스트가 잡는다. `judge-high` description의 승격 안내가 여기에 걸리기 쉽다. (Task 4)
3. settings.json이 0바이트이거나 최상위가 객체가 아니다(배열, 문자열) → 멈추고 파일을 건드리지 않는다. (Task 5)
4. `--settings` 경로의 부모 폴더가 없다 → 폴더를 만들고 쓴다. (Task 5)
5. settings.json을 쓰다가 실패한다 → 원래 파일이 반쯤 쓰인 채 남지 않는다. (Task 5)

---

## File Structure

| 파일 | 책임 |
|---|---|
| `plugins/grade-agents/.claude-plugin/plugin.json` | 플러그인 매니페스트 |
| `plugins/grade-agents/pyproject.toml`, `.python-version`, `uv.lock` | 개발·테스트 설정 |
| `plugins/grade-agents/tiers.toml` | 등급 → model·effort, `gated`, `subagent_default`, `[models]` |
| `plugins/grade-agents/scripts/render.py` | 표 읽기·검사, frontmatter 두 줄과 기준표 구간 생성 |
| `plugins/grade-agents/scripts/gate.py` | settings.json 병합 |
| `plugins/grade-agents/agents/{finder-low,routine-medium,worker-medium,worker-high,judge-high}.md` | 등급 에이전트 5종 |
| `plugins/grade-agents/docs/classification.md` | 작업량 분류 기준표 |
| `plugins/grade-agents/tests/conftest.py` | 가짜 플러그인 트리 fixture |
| `plugins/grade-agents/tests/test_tiers.py`, `test_render.py`, `test_gate.py`, `test_repo.py` | 테스트 |
| `plugins/grade-agents/README.md` | 설치, 모델 교체 절차, 승인 장치, 실제 확인 결과 |
| `.claude-plugin/marketplace.json`, `CATALOG.md`, `README.md` | 저장소 등록 |

---

### Task 1: 뼈대와 tiers.toml 읽기·검사

**Files:**
- Create: `plugins/grade-agents/.claude-plugin/plugin.json`, `pyproject.toml`, `.python-version`, `tiers.toml`, `scripts/render.py`, `tests/__init__.py`, `tests/conftest.py`, `tests/test_tiers.py`

**Interfaces:**
- Produces (`scripts/render.py`):

```python
EFFORTS: tuple[str, ...] = ("low", "medium", "high", "xhigh", "max")

@dataclass(frozen=True)
class Tiers:
    checked: str
    gated: tuple[str, ...]
    subagent_default: str
    models: dict[str, str]             # 별칭 -> 확인한 버전 이름
    tiers: dict[str, tuple[str, str]]  # 등급 이름 -> (model, effort), tiers.toml에 적힌 순서

def load_tiers(root: Path) -> tuple[Tiers | None, list[str]]
# root/"tiers.toml"을 읽는다. 문제가 하나라도 있으면 (None, 문제 목록), 없으면 (Tiers, []).
```

- Produces (`tests/conftest.py`): `TIERS`, `CLASSIFICATION`, `agent(name, description="설명", extra="", body="# 본문\n") -> str`, fixture `make_root(tiers=TIERS, agents=None, classification=CLASSIFICATION) -> Path`.

- [ ] **Step 1: 브랜치를 만들고 설계·계획 문서를 커밋한다**

```bash
git switch -c grade-agents
git add docs/superpowers/specs/2026-11-11-grade-agents-design.md docs/superpowers/plans/2026-11-11-grade-agents.md
git commit -m "grade-agents: 설계와 구현 계획"
```

- [ ] **Step 2: 뼈대 파일을 만든다**

`plugin.json`:

```json
{
  "name": "grade-agents",
  "version": "0.1.0",
  "description": "작업량 등급 서브에이전트 5종(finder-low, routine-medium, worker-medium, worker-high, judge-high). 모델 배정은 tiers.toml에서 생성한다. 외부 전송 없음.",
  "author": {"name": "hg"}
}
```

`pyproject.toml`은 `plugins/torchcast-stop-check/pyproject.toml`과 같은 모양으로 쓴다. 다른 곳은 `name = "grade-agents"`, `description = "등급 에이전트 생성 스크립트 (개발·테스트용 설정. 스크립트는 표준 라이브러리만 쓴다)"`, `pythonpath = ["scripts"]`다. `.python-version`은 `3.12`다.

`tiers.toml`은 spec 「tiers.toml」 절의 코드 블록을 그대로 쓴다(등급 5개, 주석 포함).

- [ ] **Step 3: 빈 `tests/__init__.py`와 `tests/conftest.py`를 쓴다**

```python
import pytest

TIERS = '''checked = "2026-11-11"
gated = ["fable"]
subagent_default = "sonnet"

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
                "judge-high": agent("judge-high", description="판단을 맡는다. 핵심 판단은 fable로 올린다"),
            }
        for name, text in agents.items():
            (root / "agents" / f"{name}.md").write_bytes(text.encode("utf-8"))
        if classification is not None:
            (root / "docs" / "classification.md").write_bytes(classification.encode("utf-8"))
        return root
    return _make
```

- [ ] **Step 4: 실패하는 테스트를 쓴다 (`tests/test_tiers.py`)**

```python
import render
from .conftest import TIERS


def test_valid(make_root):
    t, problems = render.load_tiers(make_root())
    assert problems == []
    assert t.checked == "2026-11-11"
    assert t.gated == ("fable",)
    assert t.subagent_default == "sonnet"
    assert t.models["haiku"] == "Haiku 5.5"
    assert list(t.tiers.items()) == [("finder-low", ("haiku", "low")), ("judge-high", ("opus", "high"))]


def bad(make_root, old, new):
    t, problems = render.load_tiers(make_root(tiers=TIERS.replace(old, new)))
    assert t is None
    return "\n".join(problems)


def test_unknown_model(make_root):
    assert "[models]에 없" in bad(make_root, 'model = "haiku"', 'model = "best"')


def test_gated_tier(make_root):
    assert "gated" in bad(make_root, 'model = "opus"', 'model = "fable"')


def test_gated_default(make_root):
    assert "gated" in bad(make_root, 'subagent_default = "sonnet"', 'subagent_default = "fable"')


def test_gated_not_in_models(make_root):
    assert "[models]에 없" in bad(make_root, 'gated = ["fable"]', 'gated = ["mythos"]')


def test_bad_effort(make_root):
    assert "effort" in bad(make_root, 'effort = "low"', 'effort = "ultra"')


def test_toml_syntax_error(make_root):
    assert "tiers.toml" in bad(make_root, 'gated = ["fable"]', 'gated = [')


def test_missing_models_table(make_root):
    t, problems = render.load_tiers(make_root(tiers=TIERS.split("[models]")[0] + "[tiers.a]\nmodel = \"x\"\neffort = \"low\"\n"))
    assert t is None and problems


def test_missing_file(tmp_path):
    t, problems = render.load_tiers(tmp_path)
    assert t is None and "tiers.toml" in "\n".join(problems)
```

- [ ] **Step 5: 실패를 확인한다**

Run: `uv run pytest tests/test_tiers.py -q`
Expected: `ModuleNotFoundError: No module named 'render'`

- [ ] **Step 6: `scripts/render.py`에 `EFFORTS`, `Tiers`, `load_tiers`를 구현한다**

문제는 처음 하나에서 멈추지 않고 전부 모아 돌려준다. 검사하는 것: 파일 없음·TOML 문법 오류·최상위 키(`checked`, `gated`, `subagent_default`, `models`, `tiers`) 누락이나 형이 다름(`tiers.toml:`로 시작하는 문제), 등급의 `model`·`subagent_default`·`gated` 항목이 `[models]`에 없음(`[models]에 없`이 든 문제), 등급의 `model`·`subagent_default`가 `gated`에 있음(`gated`가 든 문제), `effort`가 `EFFORTS`에 없음(`effort`가 든 문제). 등급에 `model`이나 `effort` 키가 없어도 문제다.

- [ ] **Step 7: 통과를 확인한다**

Run: `uv run pytest tests/test_tiers.py -q`
Expected: `9 passed`

- [ ] **Step 8: 커밋한다**

```bash
git add plugins/grade-agents
git commit -m "grade-agents: 뼈대와 tiers.toml 읽기·검사"
```

---

### Task 2: 에이전트 한 파일 다시 쓰기

**Files:**
- Modify: `plugins/grade-agents/scripts/render.py`
- Create: `plugins/grade-agents/tests/test_render.py`

**Interfaces:**
- Produces:

```python
def render_agent(text: str, model: str, effort: str) -> str
# frontmatter의 model:·effort: 줄을 주어진 값으로 맞춘 새 본문. 형식이 틀리면 ValueError(이유).

def frontmatter(text: str) -> dict[str, str]
# 첫 줄 --- 부터 다음 --- 줄 사이의 한 줄짜리 `key: value`를 읽는다. 형식이 틀리면 ValueError(이유).

def compensation_versions(text: str) -> list[str]
# frontmatter 뒤 본문에서 `## 모델 보정 (이름)` 제목의 괄호 안 이름들.
```

- [ ] **Step 1: 실패하는 테스트를 쓴다 (`tests/test_render.py`)**

```python
import pytest
import render
from .conftest import agent


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
```

- [ ] **Step 2: 실패를 확인한다**

Run: `uv run pytest tests/test_render.py -q`
Expected: `AttributeError: module 'render' has no attribute 'render_agent'`

- [ ] **Step 3: 세 함수를 구현한다**

- 닫는 `---`는 둘째 줄부터 처음 만나는, 내용이 정확히 `---`인 줄이다.
- `model:` 줄은 frontmatter 안에서 `model:`로 시작하는 줄이다(`effort:`도 같다). 있으면 그 자리에서 `model: <값>`으로 바꾸고, 없으면 닫는 `---` 바로 앞에 `model`, `effort` 순서로 넣는다.
- `\r`이 하나라도 있으면 `ValueError`다.
- 모델 보정 제목은 정규식 `^## 모델 보정 \((.+)\)\s*$`(여러 줄 모드)로 본문에서만 찾는다.

- [ ] **Step 4: 통과를 확인한다**

Run: `uv run pytest tests/test_render.py -q`
Expected: `12 passed`

- [ ] **Step 5: 커밋한다**

```bash
git add plugins/grade-agents
git commit -m "grade-agents: 에이전트 frontmatter 두 줄 다시 쓰기"
```

---

### Task 3: 기준표 구간, 전체 검사, render 명령

**Files:**
- Modify: `plugins/grade-agents/scripts/render.py`, `plugins/grade-agents/tests/test_render.py`

**Interfaces:**
- Consumes: Task 1의 `Tiers`, `load_tiers`; Task 2의 `render_agent`, `frontmatter`, `compensation_versions`.
- Produces:

```python
BEGIN = "<!-- tiers:begin -->"
END = "<!-- tiers:end -->"

def render_block(t: Tiers) -> str
# BEGIN 줄부터 END 줄까지(두 표시 포함, 끝에 줄바꿈 없음).

def build(root: Path) -> tuple[dict[Path, str], list[str]]
# (파일 경로 -> 있어야 할 전체 내용, 문제 목록). 문제가 있으면 첫 값은 쓰지 않는다.
# 경로는 root/"agents"/"<이름>.md" 전부와 root/"docs"/"classification.md"다.

def main(argv: list[str] | None = None, root: Path | None = None) -> int
# root 기본값은 Path(__file__).resolve().parents[1]. 인자는 --check 하나.
```

- [ ] **Step 1: 실패하는 테스트를 `tests/test_render.py`에 더한다**

```python
from .conftest import TIERS, CLASSIFICATION

BLOCK = """<!-- tiers:begin -->
| 에이전트 | model | effort | 확인한 버전 |
|---|---|---|---|
| `finder-low` | `haiku` | `low` | Haiku 5.5 |
| `judge-high` | `opus` | `high` | Opus 5.5 |

확인한 날: 2026-11-11

승인이 필요한 모델: `fable` (Fable 5.2). `judge-high`를 호출 인자 `model: "fable"`로 부른다.
<!-- tiers:end -->"""


def test_block(make_root):
    t, _ = render.load_tiers(make_root())
    assert render.render_block(t) == BLOCK


def test_block_without_gated(make_root):
    t, _ = render.load_tiers(make_root(tiers=TIERS.replace('gated = ["fable"]', "gated = []")))
    assert "승인이 필요한 모델: 없음" in render.render_block(t)


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
                             "judge-high": agent("judge-high", description="fable로 올린다")})
    assert "name" in problems_of(root)


def test_check5_stale_compensation(make_root):
    root = make_root(tiers=TIERS.replace('haiku = "Haiku 5.5"', 'haiku = "Haiku 6"'))
    out = problems_of(root)
    assert "다시 볼 것" in out and "finder-low" in out and "Haiku 5.5" in out


def test_check6_gated_missing_from_judge_description(make_root):
    root = make_root(agents={"finder-low": agent("finder-low"), "judge-high": agent("judge-high")})
    assert "description" in problems_of(root)


@pytest.mark.parametrize("text", [
    "# 기준표\n",                                                        # 표시 없음
    "<!-- tiers:end -->\n<!-- tiers:begin -->\n",                        # 순서 뒤집힘
    CLASSIFICATION + "<!-- tiers:begin -->\n<!-- tiers:end -->\n",       # 둘씩
    None,                                                                # 파일 없음
])
def test_check7_markers(make_root, text):
    assert "tiers:begin" in problems_of(make_root(classification=text))


def test_bad_agent_format_is_a_problem(make_root):
    root = make_root(agents={"finder-low": "# 제목\n",
                             "judge-high": agent("judge-high", description="fable로 올린다")})
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
    root = make_root(tiers="gated = [")
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
```

- [ ] **Step 2: 실패를 확인한다**

Run: `uv run pytest tests/test_render.py -q`
Expected: 새 테스트가 `AttributeError: module 'render' has no attribute 'render_block'`로 실패

- [ ] **Step 3: `render_block`, `build`, `main`을 구현한다**

`build`가 모으는 문제(spec 「render.py」 검사 번호):

- `load_tiers`의 문제. 있으면 거기서 돌려준다.
- 1: `[tiers]`의 이름 집합과 `agents/*.md`의 파일 이름 집합이 다르면 `짝`이 든 문제, frontmatter `name`이 파일 이름과 다르면 `name`이 든 문제.
- `render_agent`·`frontmatter`의 `ValueError`는 그 에이전트 이름을 붙인 문제로 바꾼다.
- 5: `compensation_versions`의 이름이 `models[그 등급의 model]`과 다르면 `다시 볼 것: <에이전트> — 모델 보정 (<적힌 이름>), 지금은 <새 이름>`.
- 6: `gated`의 이름이 `judge-high`의 description에 없으면 `description`이 든 문제. `gated`가 비어 있으면 검사하지 않는다.
- 7: 기준표 파일이 없거나 두 표시가 각각 정확히 하나씩, BEGIN이 앞에 있지 않으면 `tiers:begin`이 든 문제.

기준표의 새 내용은 BEGIN의 시작부터 END의 끝까지를 `render_block`의 결과로 바꾼 것이다.

`render_block`의 승인 줄은 `gated`의 모델마다 한 줄이고, 비어 있으면 `승인이 필요한 모델: 없음` 한 줄이다.

`main`: 문제가 있으면 한 줄에 하나씩 stdout에 찍고 1. 없으면 지금 내용과 다른 파일만 추린다. `--check`면 그 경로를 찍고 다른 파일이 있으면 1, 없으면 0. 아니면 그 파일들을 쓰고 경로를 찍고 0. 파일 끝에 `if __name__ == "__main__": sys.exit(main())`.

- [ ] **Step 4: 통과를 확인한다**

Run: `uv run pytest -q`
Expected: 전부 통과(`tests/test_tiers.py` 9개 포함)

- [ ] **Step 5: 버전 안내를 확인한다**

Run: `/usr/bin/python3 scripts/render.py --check; echo EXIT=$?`
Expected: `Python 3.11 이상이 필요하다. uv run python scripts/render.py 로 돌린다.` 다음에 `EXIT=2`

- [ ] **Step 6: 커밋한다**

```bash
git add plugins/grade-agents
git commit -m "grade-agents: 기준표 구간 생성과 render 명령"
```

---

### Task 4: 에이전트 5종과 분류 기준표

**Files:**
- Create: `plugins/grade-agents/agents/finder-low.md`, `routine-medium.md`, `worker-medium.md`, `worker-high.md`, `judge-high.md`, `plugins/grade-agents/docs/classification.md`, `plugins/grade-agents/tests/test_repo.py`

**Interfaces:**
- Consumes: `render.build`, `render.frontmatter`.

참고할 원본은 사내 프로젝트 저장소 `.claude/agents/`의 같은 이름 파일이다. 구조와 말투를 따르되, 규칙은 spec 「에이전트」 절의 목록만 넣는다. 원본의 gradle·detekt·`origin/main`·이슈 크기·`workspace.md`·커밋 서명 문장은 옮기지 않는다.

- [ ] **Step 1: 실패하는 테스트를 쓴다 (`tests/test_repo.py`)**

```python
from pathlib import Path

import pytest
import render

PLUGIN = Path(__file__).resolve().parents[1]
NAMES = ["finder-low", "routine-medium", "worker-medium", "worker-high", "judge-high"]


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
        for alias in t.models:
            assert alias not in body.lower(), (name, alias)
    doc = (PLUGIN / "docs/classification.md").read_bytes().decode("utf-8")
    outside = doc.split(render.BEGIN)[0] + doc.split(render.END)[1]
    for alias in t.models:
        assert alias not in outside.lower(), alias
```

- [ ] **Step 2: 실패를 확인한다**

Run: `uv run pytest tests/test_repo.py -q`
Expected: `짝`이 든 문제로 `test_committed_files_match_tiers` 실패, 나머지는 `FileNotFoundError`

- [ ] **Step 3: 에이전트 다섯 파일을 쓴다**

frontmatter는 아래를 그대로 쓴다(`model:`·`effort:` 줄은 쓰지 않는다. Step 5의 render가 넣는다).

| 파일 | `description` | 도구 줄 |
|---|---|---|
| `finder-low` | `파일·심볼 찾기, 목록 뽑기, 상태 확인, 로그 분류처럼 판단이 거의 없는 읽기 일을 맡는다. 결론만 필요하고 파일 내용은 필요 없을 때 부른다. 파일을 고치지 않는다. 판단이 드는 일과 문서·요약 작성에는 쓰지 않는다.` | `tools: Read, Grep, Glob, Bash` |
| `routine-medium` | `판단이 들지 않는 정형 일을 맡는다. 정해진 칸을 여러 파일·로그에서 뽑아 모으는 추출·집계, 바꿀 자리와 모양이 다 정해진 기계적 수정(이름 바꾸기, import 정리, 경고를 지적대로 고치기)이다. 판단·분류·반박 검증, 고위험 경로, 문서·PR 본문처럼 남는 글에는 쓰지 않는다.` | `disallowedTools: Agent` |
| `worker-medium` | `보통 난도의 코드 분석·구현·디버깅·테스트 쓰기, 분류·정찰, 지적 하나의 반박 검증, 문서·요약 작성을 맡는다. 고위험 변경(트랜잭션·잠금·보안·핵심 경로 구조)의 구현은 worker-high에, 설계 판단은 judge-high에 맡긴다.` | `disallowedTools: Agent` |
| `worker-high` | `고위험 변경(트랜잭션·잠금·보안·핵심 경로 구조)의 구현과 앞선 판정을 뒤집는 판정을 맡는다. 설계 판단은 하지 않는다. 이 에이전트가 고친 변경분에는 judge-high 리뷰를 붙인다.` | `disallowedTools: Agent` |
| `judge-high` | `아키텍처·보안·고위험 변경의 판단, 설계 분해, 처음 보는 눈으로 하는 마지막 교차검토, 심각도 높은 지적의 반박 검증을 맡는다. 코드를 고치지 않는다. 되돌리기 어려운 아키텍처·보안 결정이나 이 에이전트의 판정이 엇갈려 풀리지 않는 일은 사용자에게 이유를 한 줄로 알린 뒤 호출 인자 model을 fable로 주어 부른다. 그 호출에는 승인 창이 뜬다.` | `tools: Read, Grep, Glob, Bash, WebFetch` |

본문은 다섯 모두 이 순서의 절로 쓴다.

1. `# <역할 이름>` 과 맡는 일 두세 줄 (spec 「에이전트」 표의 「맡는 일」)
2. `## 이 등급을 넘는 일이면 멈춘다` — 넘는 일마다 다시 맡길 에이전트 이름을 괄호로 적는다. `judge-high`에는 이 절 대신 승격 절차 한 줄(「더 무거운 모델이 필요하다고 보면 그 까닭을 적어 돌려준다. 올릴지는 부른 쪽과 사용자가 정한다」)을 쓴다.
3. `## 규칙` — spec 「다섯에 공통인 규칙」 전부와 그 에이전트의 「에이전트별 규칙」 전부. 문장을 줄이거나 합치지 않는다.
4. `## 출력` — 한 줄 결론, 근거, 돌린 것과 안 돌린 것. `judge-high`는 spec의 판단·검토 출력 형식.
5. `finder-low`와 `routine-medium`만: `## 모델 보정 (Haiku 5.5)` — spec 「모델 보정 블록」의 해당 규칙과 제공자 주의.

- [ ] **Step 4: `docs/classification.md`를 쓴다**

절 순서와 고정 내용:

```markdown
# 작업량 분류 기준

## 어떤 일을 누구에게

| 작업 유형 | 에이전트 |
|---|---|
| 파일·심볼 찾기, 목록, 상태 확인, 로그 분류 | `finder-low` |
| 정형 추출·집계, 바꿀 자리와 모양이 정해진 기계적 수정 | `routine-medium` |
| 일반 코드 분석·구현·디버깅·테스트 쓰기 | `worker-medium` |
| 분류·정찰 | `worker-medium`. 앞선 판정을 뒤집을 때는 `worker-high` |
| 지적 하나의 반박 검증 | `worker-medium`. 심각도 높은 지적은 `judge-high` |
| 문서·요약 작성 | `worker-medium` |
| 고위험 변경(트랜잭션·잠금·보안·핵심 경로 구조)의 구현 | `worker-high`, 그리고 그 변경분에 `judge-high` 리뷰 |
| 판단, 설계 분해, 마지막 교차검토 | `judge-high` |

## 지금 배정

<!-- tiers:begin -->
<!-- tiers:end -->

## 원칙
## 한 건만 올리기
## 승인이 필요한 모델로 올리기
```

`## 원칙`은 spec 「docs/classification.md」의 원칙 다섯 줄, `## 한 건만 올리기`는 호출 인자 `effort`와 이유 한 줄, `## 승인이 필요한 모델로 올리기`는 spec 「승인이 필요한 모델」의 올릴 수 있는 일 두 가지와 절차 네 단계다. 이 세 절에는 모델 이름을 적지 않는다(절차 2·3번은 「위 표의 승인이 필요한 모델」로 가리킨다).

- [ ] **Step 5: 생성한다**

Run: `uv run python scripts/render.py; echo EXIT=$?`
Expected: 여섯 파일 경로가 찍히고 `EXIT=0`

- [ ] **Step 6: 통과를 확인한다**

Run: `uv run pytest -q`
Expected: 전부 통과

Run: `uv run python scripts/render.py --check; echo EXIT=$?`
Expected: `EXIT=0`

- [ ] **Step 7: 커밋한다**

```bash
git add plugins/grade-agents
git commit -m "grade-agents: 등급 에이전트 5종과 분류 기준표"
```

---

### Task 5: gate.py

**Files:**
- Create: `plugins/grade-agents/scripts/gate.py`, `plugins/grade-agents/tests/test_gate.py`

**Interfaces:**
- Consumes: `render.build(root)`, `render.load_tiers(root)`, `render.Tiers`.
- Produces:

```python
class GateError(Exception): ...

def merge(settings: object, tiers: render.Tiers) -> tuple[dict, list[str]]
# (병합한 새 설정, 알림 목록). 입력을 고치지 않는다.
# settings가 객체가 아니거나, permissions·env가 객체가 아니거나, permissions.ask가 배열이 아니거나,
# env.CLAUDE_CODE_SUBAGENT_MODEL이 gated 모델이면 GateError.

def main(argv: list[str] | None = None, root: Path | None = None) -> int
# 인자: --settings <경로> (기본 Path.home()/".claude"/"settings.json"), --check
```

- [ ] **Step 1: 실패하는 테스트를 쓴다 (`tests/test_gate.py`)**

```python
import json
import os

import pytest
import gate
import render
from .conftest import TIERS

RULE = "Agent(model:fable)"
KEY = "CLAUDE_CODE_SUBAGENT_MODEL"


@pytest.fixture
def tiers(make_root):
    return render.load_tiers(make_root())[0]


def test_merge_empty(tiers):
    new, notes = gate.merge({}, tiers)
    assert new == {"permissions": {"ask": [RULE]}, "env": {KEY: "sonnet"}}


def test_merge_preserves_everything_else(tiers):
    old = {"model": "opus", "permissions": {"allow": ["Bash(ls)"], "ask": ["Bash(rm *)"]}, "env": {"X": "1"}}
    new, _ = gate.merge(old, tiers)
    assert new["model"] == "opus"
    assert new["permissions"] == {"allow": ["Bash(ls)"], "ask": ["Bash(rm *)", RULE]}
    assert new["env"] == {"X": "1", KEY: "sonnet"}
    assert list(new) == ["model", "permissions", "env"]
    assert old["permissions"]["ask"] == ["Bash(rm *)"]


def test_merge_no_duplicate_and_same_value(tiers):
    old = {"permissions": {"ask": [RULE]}, "env": {KEY: "sonnet"}}
    assert gate.merge(old, tiers) == (old, [])


def test_merge_keeps_other_default_and_notes(tiers):
    new, notes = gate.merge({"env": {KEY: "opus"}}, tiers)
    assert new["env"][KEY] == "opus"
    assert any(KEY in n for n in notes)


def test_merge_gated_default_is_error(tiers):
    with pytest.raises(gate.GateError):
        gate.merge({"env": {KEY: "fable"}}, tiers)


def test_merge_keeps_rule_for_removed_gated(make_root):
    t = render.load_tiers(make_root(tiers=TIERS.replace('gated = ["fable"]', "gated = []")))[0]
    new, _ = gate.merge({"permissions": {"ask": [RULE]}}, t)
    assert new["permissions"]["ask"] == [RULE]


@pytest.mark.parametrize("bad", [
    [], "x", {"permissions": []}, {"permissions": {"ask": "x"}}, {"env": []},
])
def test_merge_bad_shapes(tiers, bad):
    with pytest.raises(gate.GateError):
        gate.merge(bad, tiers)


@pytest.fixture
def root(make_root):
    r = make_root()
    assert render.main([], r) == 0   # gate는 원본이 맞아 있을 때만 돈다
    return r


def run(root, path, *flags):
    return gate.main(["--settings", str(path), *flags], root)


def test_main_creates_file_and_parents(root, tmp_path):
    path = tmp_path / "home" / ".claude" / "settings.json"
    assert run(root, path) == 0
    assert json.loads(path.read_text()) == {"permissions": {"ask": [RULE]}, "env": {KEY: "sonnet"}}
    assert path.read_text().endswith("}\n")


def test_main_writes_indent_and_unicode(root, tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"메모": "한글"}', encoding="utf-8")
    assert run(root, path) == 0
    text = path.read_text(encoding="utf-8")
    assert '  "메모": "한글"' in text


def test_main_no_change_does_not_rewrite(root, tmp_path):
    path = tmp_path / "settings.json"
    raw = '{"permissions":{"ask":["Agent(model:fable)"]},"env":{"CLAUDE_CODE_SUBAGENT_MODEL":"sonnet"}}'
    path.write_text(raw)
    assert run(root, path) == 0
    assert path.read_text() == raw


def test_main_twice_same(root, tmp_path):
    path = tmp_path / "settings.json"
    run(root, path)
    once = path.read_bytes()
    assert run(root, path) == 0
    assert path.read_bytes() == once


@pytest.mark.parametrize("raw", ["", "{", "[]", '"x"', '{"permissions": []}',
                                 '{"env": {"CLAUDE_CODE_SUBAGENT_MODEL": "fable"}}'])
def test_main_stops_without_touching(root, tmp_path, raw):
    path = tmp_path / "settings.json"
    path.write_text(raw)
    assert run(root, path) == 1
    assert path.read_text() == raw


def test_main_refuses_when_source_has_problems(make_root, tmp_path):
    stale = make_root(tiers=TIERS.replace('haiku = "Haiku 5.5"', 'haiku = "Haiku 6"'))
    path = tmp_path / "settings.json"
    assert run(stale, path) == 1
    assert not path.exists()


def test_main_refuses_when_source_not_rendered(make_root, tmp_path):
    path = tmp_path / "settings.json"
    assert run(make_root(), path) == 1   # 문제는 없지만 render를 안 돌린 트리
    assert not path.exists()


def test_check(root, tmp_path):
    path = tmp_path / "settings.json"
    assert run(root, path, "--check") == 1
    assert not path.exists()
    run(root, path)
    assert run(root, path, "--check") == 0


def test_check_gated_default_is_1(root, tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"permissions":{"ask":["Agent(model:fable)"]},"env":{"CLAUDE_CODE_SUBAGENT_MODEL":"fable"}}')
    assert run(root, path, "--check") == 1


def test_failed_write_leaves_original(root, tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    path.write_text('{"model": "opus"}')
    def boom(*a, **k):
        raise OSError("disk")
    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        run(root, path)
    assert path.read_text() == '{"model": "opus"}'
```

- [ ] **Step 2: 실패를 확인한다**

Run: `uv run pytest tests/test_gate.py -q`
Expected: `ModuleNotFoundError: No module named 'gate'`

- [ ] **Step 3: `scripts/gate.py`를 구현한다**

- 맨 위에 render.py와 같은 버전 검사를 둔다(파일 이름만 `gate.py`).
- `main`은 먼저 `render.build(root)`를 부른다. 문제가 있거나, 문제는 없어도 지금 파일과 다른 것이 있으면(원본이 어긋남) 그 내용을 찍고 1이다.
- 설정 파일이 없으면 `{}`로 본다. 있으면 `json.loads`한다. 읽기 실패(`JSONDecodeError`, 0바이트 포함)와 `GateError`는 이유를 찍고 1이다.
- 병합한 결과가 읽은 값과 같으면 알림만 찍고 0이다. 파일을 다시 쓰지 않는다.
- 다르면 `--check`일 때 1, 아니면 쓴다. 쓰기는 부모 폴더를 만들고, 같은 폴더의 임시 파일에 `json.dumps(new, indent=2, ensure_ascii=False) + "\n"`을 쓴 뒤 `os.replace`로 바꾼다. `os.replace`가 실패하면 임시 파일을 지우고 예외를 그대로 올린다.
- 쓴 뒤에는 더한 규칙과 넣은 값을 한 줄씩 찍는다.

- [ ] **Step 4: 통과를 확인한다**

Run: `uv run pytest -q`
Expected: 전부 통과

- [ ] **Step 5: 실제 원본으로 임시 경로에 돌려 본다**

Run: `d=$(mktemp -d) && uv run python scripts/gate.py --settings "$d/settings.json" && cat "$d/settings.json"`
Expected: `permissions.ask`에 `Agent(model:fable)`, `env.CLAUDE_CODE_SUBAGENT_MODEL`이 `sonnet`인 JSON. `--settings` 없이 돌리지 않는다(실제 사용자 설정을 고친다).

- [ ] **Step 6: 커밋한다**

```bash
git add plugins/grade-agents
git commit -m "grade-agents: settings.json에 승인 규칙과 즉석 기본값 병합"
```

---

### Task 6: README와 저장소 등록

**Files:**
- Create: `plugins/grade-agents/README.md`
- Modify: `.claude-plugin/marketplace.json`, `CATALOG.md`, `README.md`

- [ ] **Step 1: `plugins/grade-agents/README.md`를 쓴다**

절 순서:

1. `# grade-agents` — 한 문단 소개. 첫 문단 바로 아래에 `> **전송:** 없음.`
2. `## 등급` — `docs/classification.md`의 「어떤 일을 누구에게」 표로 가는 링크와, 지금 배정은 `tiers.toml`과 기준표의 생성 구간에 있다는 한 줄.
3. `## 설치` — 최소 버전(Claude Code v2.1.321), spec 「설치」의 세 명령.
4. `## 승인이 필요한 모델` — spec 「막는 것」 표와 「알고 열어 두는 것」 목록, 「즉석 기본값의 부작용」 세 줄.
5. `## 모델이 바뀔 때` — spec의 다섯 단계.
6. `## 개발` — `uv run pytest -q`, `uv run python scripts/render.py --check`.
7. `## 실제 확인` — 표 머리만 둔다(`| 항목 | 결과 | 날짜·버전 |`). Task 7이 채운다.

- [ ] **Step 2: `.claude-plugin/marketplace.json`의 `plugins` 끝에 더한다**

```json
{
  "name": "grade-agents",
  "description": "작업량 등급 서브에이전트 5종. 모델 배정은 tiers.toml 하나에서 생성하고, 승인이 필요한 모델은 권한 ask 규칙으로 막는다",
  "version": "0.1.0",
  "source": "./plugins/grade-agents",
  "category": "development"
}
```

- [ ] **Step 3: `CATALOG.md`에 더한다**

표에 한 줄:

```markdown
| [grade-agents](plugins/grade-agents/README.md) | 서브에이전트 | 작업량 등급별로 모델·노력 수준을 고정해 맡기기. 배정은 `tiers.toml` 하나 | trial (2026-11-11) | 없음 | 실제 세션 확인 전 | 안 함 | 실제 세션 확인 5항목. 새 모델이 나오면 `tiers.toml`과 모델 보정 블록 |
```

「바뀐 기록」에 한 줄: `- 2026-11-11: grade-agents 0.1.0. 사내 프로젝트의 등급 에이전트 5종을 범용으로 옮겼다. 모델 배정을 tiers.toml에서 생성하고, Fable은 호출 인자로만 올리며 ask 규칙으로 승인을 받는다. 팀 저장소로 내보내는 갈래는 아직 없다.`

- [ ] **Step 4: 루트 `README.md` 「새 도구 추가」 1번을 고친다**

`스킬이면 \`skills/\`.` 를 `스킬이면 \`skills/\`, 서브에이전트면 \`agents/\`.` 로 바꾼다.

- [ ] **Step 5: 형식을 확인한다**

Run (저장소 루트): `claude plugin validate .; echo EXIT=$?`
Expected: 오류 없이 `EXIT=0`

Run (저장소 루트): `python3 -c "import json;json.load(open('.claude-plugin/marketplace.json'))" && echo OK`
Expected: `OK`

- [ ] **Step 6: 커밋한다**

```bash
git add plugins/grade-agents/README.md .claude-plugin/marketplace.json CATALOG.md README.md
git commit -m "grade-agents: README와 마켓플레이스·CATALOG 등록"
```

---

### Task 7: 실제 세션 확인 (메인 세션이 사용자와 함께)

서브에이전트에 맡기지 않는다. 사용자 컴퓨터의 설정을 바꾸는 단계마다 먼저 묻는다.

**Files:**
- Modify: `plugins/grade-agents/README.md` (「실제 확인」 표), `CATALOG.md` (효과 측정 칸)

- [ ] **Step 1: 사용자에게 묻고 Claude Code를 올린다**

Run: `claude update && claude --version`
Expected: `2.1.321` 이상. 못 올리면 여기서 멈추고 알린다.

- [ ] **Step 2: 사용자에게 묻고 플러그인을 설치한다**

Run: `claude plugin install grade-agents@hg-claude-kit --scope user`
Expected: 설치 성공. `claude plugin details grade-agents@hg-claude-kit`에 에이전트 5개가 보인다.

- [ ] **Step 3: 설치 경로를 본다 (항목 6)**

`~/.claude/plugins/installed_plugins.json`에서 `grade-agents@hg-claude-kit`의 `installPath`를 읽는다. 이 저장소를 가리키면 통과다. `~/.claude/plugins/cache/`를 가리키면 플러그인 README 「모델이 바뀔 때」 5단계와 루트 `README.md`의 업데이트 문구를 버전 올리기·`marketplace update`·업데이트 절차에 맞게 고치고 사용자에게 알린다.

- [ ] **Step 4: 등급 에이전트가 표의 모델로 도는지 본다 (항목 2)**

새 `claude -p` 실행에서 `grade-agents:worker-medium`을 `subagent_type`으로 불러 한 줄짜리 일을 시키고, `--output-format stream-json --verbose` 출력에서 서브에이전트 메시지의 `model` 값을 읽는다. 값이 Sonnet 계열이면 통과다. 출력에 모델이 안 보이면 그 실행의 transcript(`~/.claude/projects/` 아래 JSONL)에서 읽는다.

- [ ] **Step 5: 사용자에게 묻고 `gate.py`를 실제 설정에 돌린다**

먼저 `uv run python scripts/gate.py --check`의 출력을 사용자에게 보여 주고, 동의하면 `uv run python scripts/gate.py`를 돌린다.

- [ ] **Step 6: 승인 창을 확인한다 (항목 3, 4)**

새 대화형 세션에서 사용자가 지켜보는 가운데:
- `judge-high`를 `model: "fable"`로 부르게 한다 → 승인 창이 뜨면 거부한다.
- `agent()` 한 번에 `model: 'fable'`을 준 한 줄짜리 Workflow를 돌린다 → 승인 창이 뜨면 거부한다. 창 없이 돌기 시작하면 바로 멈추고 결과를 「열어 두는 것」에 더한다.

- [ ] **Step 7: 즉석 기본값을 확인한다 (항목 5)**

메인 세션을 Fable로 여는 일이라 비용이 든다. 사용자에게 묻고, 동의하면 메인이 Fable인 세션에서 `model` 없이 `general-purpose`를 한 번 불러 Step 4와 같은 방법으로 모델을 읽는다. Sonnet 계열이면 통과다. 동의하지 않으면 「확인 안 함」으로 적는다.

- [ ] **Step 8: 결과를 적고 커밋한다**

README 「실제 확인」 표에 여섯 항목의 결과와 날짜·Claude Code 버전을 적는다. CATALOG의 효과 측정 칸을 `실제 세션 확인 n/6 (날짜)`로 바꾼다. 기대와 다른 항목이 있으면 사용자에게 알리고 spec의 해당 절을 다시 정한다.

```bash
git add plugins/grade-agents/README.md CATALOG.md README.md
git commit -m "grade-agents: 실제 세션 확인 결과"
```
