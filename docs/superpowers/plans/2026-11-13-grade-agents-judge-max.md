# grade-agents judge-max 개정 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fable 승인 장치(`gated`, `subagent_default`, `gate.py`)를 걷어 내고, Fable 등급 서브에이전트 `judge-max`를 더한다.

**Architecture:** `render.py`의 `Tiers`에서 두 필드와 검사 둘을 지우고, 기준표 생성 구간에서 「승인이 필요한 모델」 줄을 뺀다. `judge-max`는 `tiers.toml`의 여섯 번째 등급과 `agents/judge-max.md`로 더하고, `judge-high`와 같은 규칙 문장을 저장소 시험으로 묶는다. 실제 `~/.claude/settings.json` 정리와 실제 세션 확인은 마지막에 메인 세션이 사용자에게 물으며 한다.

**Tech Stack:** Python 3.12(uv), pytest, 표준 라이브러리만. Claude Code 플러그인(로컬 경로 마켓플레이스).

**Spec:** `docs/superpowers/specs/2026-11-11-grade-agents-design.md` (개정 2026-11-13, 커밋 `6f4774e`)

## Global Constraints

- 스크립트는 플러그인 폴더(`plugins/grade-agents`)에서 `uv run python scripts/<이름>.py`로 돌린다. 시험은 `uv run pytest -q -p no:cacheprovider`.
- `render.py`는 전부 쓰거나 아무것도 쓰지 않는다. 검사에 걸리면 걸린 항목을 모두 찍고 종료 코드 1.
- `agents/*.md`의 frontmatter `model:`·`effort:` 두 줄만 `render.py`가 쓴다. 나머지는 사람이 쓴다.
- 에이전트 본문(frontmatter 뒤, `## 모델 보정` 앞)과 `docs/classification.md`의 생성 구간 밖에는 `[models]`의 별칭(`haiku` · `sonnet` · `opus` · `fable`)을 쓰지 않는다(기존 `test_no_model_names_outside_allowed_places`).
- description 값은 한 줄이고 `: `와 ` #`를 담지 않으며 `[{>|*&!%@`"'#-`로 시작하지 않는다(기존 `test_frontmatter_values_are_yaml_safe`).
- 여섯 정의 모두 `Agent` 도구가 없다.
- 실제 `~/.claude/settings.json`은 사용자에게 물은 뒤에만 고친다. 실제 세션 확인은 서브에이전트에 맡기지 않는다.
- 커밋 메시지는 `grade-agents: …` 꼴이고 끝에 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

- 0.1.0의 `tiers.toml`처럼 `gated`·`subagent_default` 키가 남아 있는 파일 → 오류 없이 무시한다(`test_leftover_gate_keys_ignored`, Task 1).
- 등급 `model`이 `fable`인 표 → 이제 통과해야 한다(`test_fable_tier_allowed`, Task 1).
- `judge-high`의 규칙을 고치고 `judge-max`를 안 고침 → 저장소 시험이 붉어진다(`test_judge_rules_stay_in_sync`, Task 2).
- `judge-max` 본문에 모델 이름을 적음 → 기존 별칭 검사가 잡는다(`NAMES`에 `judge-max`를 더해 Task 2에서 걸리게 한다).
- 문서에 `gate.py`·`gated`·`subagent_default`가 남음 → Task 3 마지막 `grep` 단계가 잡는다.

---

### Task 1: render.py에서 승인 장치 걷어 내기, gate.py 지우기

**Files:**
- Modify: `plugins/grade-agents/scripts/render.py` (`Tiers`, `load_tiers`, `render_block`, `build`)
- Modify: `plugins/grade-agents/tests/conftest.py` (`TIERS`, 기본 `judge-high` description)
- Modify: `plugins/grade-agents/tests/test_tiers.py`, `plugins/grade-agents/tests/test_render.py`
- Delete: `plugins/grade-agents/scripts/gate.py`, `plugins/grade-agents/tests/test_gate.py`
- Modify (생성 결과): `plugins/grade-agents/docs/classification.md`

**Interfaces:**
- Produces: `Tiers(checked: str, models: dict[str, str], tiers: dict[str, tuple[str, str]])` — `gated`·`subagent_default` 필드 없음. `load_tiers(root) -> tuple[Tiers | None, list[str]]`, `render_block(t: Tiers) -> str`, `build(root) -> tuple[dict[Path, str], list[str]]`의 시그니처는 그대로.

- [ ] **Step 1: 시험을 먼저 고친다**

`conftest.py`의 `TIERS`에서 `gated`·`subagent_default` 두 줄을 지우고, 기본 `judge-high`의 description을 `"판단을 맡는다"`로 바꾼다. `test_check1_name_mismatch`·`test_bad_agent_format_is_a_problem`의 `description="fable로 올린다"`도 `"판단을 맡는다"`로.

`test_tiers.py`:
- `test_valid`에서 `t.gated`·`t.subagent_default` 단언을 지우고 `assert not hasattr(t, "gated") and not hasattr(t, "subagent_default")`를 넣는다.
- `test_gated_tier`·`test_gated_default`·`test_gated_not_in_models`를 지운다.
- `test_toml_syntax_error`의 바꿀 글자를 `'checked = "2026-11-11"'` → `'checked = ['`로.
- 새 시험 둘:

```python
def test_fable_tier_allowed(make_root):
    root = make_root(tiers=TIERS.replace('model = "opus"', 'model = "fable"'))
    t, problems = render.load_tiers(root)
    assert problems == [] and t.tiers["judge-high"] == ("fable", "high")


def test_leftover_gate_keys_ignored(make_root):
    root = make_root(tiers='gated = ["fable"]\nsubagent_default = "sonnet"\n' + TIERS)
    t, problems = render.load_tiers(root)
    assert problems == [] and set(t.tiers) == {"finder-low", "judge-high"}
```

`test_render.py`:
- `BLOCK`에서 빈 줄 하나와 `승인이 필요한 모델: …` 줄을 지운다. 결과는 `확인한 날: 2026-11-11` 다음 줄이 바로 `<!-- tiers:end -->`.
- `test_block_without_gated`, `test_check6_gated_missing_from_judge_description`을 지운다.
- `test_check5_stale_compensation` → `test_check4_stale_compensation`, `test_check7_markers` → `test_check5_markers`로 이름만 바꾼다.
- `test_main_bad_tiers_no_traceback`의 `make_root(tiers="gated = [")`를 `make_root(tiers="checked = [")`로.

- [ ] **Step 2: 시험이 실패하는지 본다**

Run: `uv run pytest -q -p no:cacheprovider tests/test_tiers.py tests/test_render.py`
Expected: `test_valid`, `test_block`, `test_build_ok`, `test_fable_tier_allowed`, `test_leftover_gate_keys_ignored` 등이 FAIL(`gated가 없거나…` 문제 또는 블록 불일치).

- [ ] **Step 3: render.py를 고친다**

- `Tiers`에서 `gated`·`subagent_default`를 지운다.
- `load_tiers`에서 `gated`·`subagent_default`를 읽는 부분, `[models]`와 맞추는 블록, 등급 루프의 `elif gated is not None and model in gated` 갈래를 지운다. 알 수 없는 최상위 키는 읽지 않는다(무시).
- `render_block`은 `확인한 날: {checked}` 줄 다음에 바로 `END`를 붙인다. 바꾼 뒤 출력 끝은 `"\n\n확인한 날: {checked}\n" + END` 꼴.
- `build`에서 `if name == "judge-high" and t.gated:` 블록을 지운다.

- [ ] **Step 4: gate.py와 그 시험을 지운다**

Run: `git rm scripts/gate.py tests/test_gate.py`

- [ ] **Step 5: 기준표를 다시 만들고 전체 시험을 돌린다**

Run: `uv run python scripts/render.py && uv run python scripts/render.py --check; echo "exit=$?"`
Expected: 첫 실행이 `docs/classification.md` 한 줄을 찍고, `--check`는 `exit=0`. 생성 구간에서 `승인이 필요한 모델` 줄이 사라진다. (`tiers.toml`의 `gated`·`subagent_default`는 아직 남아 있어도 무시된다.)

Run: `uv run pytest -q -p no:cacheprovider`
Expected: 모두 통과.

- [ ] **Step 6: 커밋**

```bash
git add -A scripts tests docs/classification.md
git commit -m "grade-agents: render.py에서 gated·subagent_default를 걷어 내고 gate.py 삭제"
```

---

### Task 2: judge-max 등급 더하기

**Files:**
- Modify: `plugins/grade-agents/tiers.toml`
- Create: `plugins/grade-agents/agents/judge-max.md`
- Modify: `plugins/grade-agents/agents/judge-high.md` (description, 「더 무거운 모델이 필요하면」 절, `## 규칙` 끝 한 줄)
- Modify: `plugins/grade-agents/docs/classification.md` (사람이 쓰는 표·절)
- Modify: `plugins/grade-agents/tests/test_repo.py`

**Interfaces:**
- Consumes: Task 1의 `render.build`, `render.frontmatter`(시그니처 그대로).
- Produces: 등급 이름 `judge-max`, 플러그인 에이전트 이름 `grade-agents:judge-max`.

- [ ] **Step 1: 저장소 시험을 먼저 고친다**

`test_repo.py`의 `NAMES` 끝에 `"judge-max"`를 더한다. 새 시험:

```python
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
```

- [ ] **Step 2: 시험이 실패하는지 본다**

Run: `uv run pytest -q -p no:cacheprovider tests/test_repo.py`
Expected: FAIL(`agents/judge-max.md` 없음).

- [ ] **Step 3: tiers.toml을 고친다**

`gated`·`subagent_default` 두 줄을 지우고 `checked = "2026-11-13"`로. 끝에:

```toml
[tiers.judge-max]
model = "fable"
effort = "high"
```

- [ ] **Step 4: judge-high.md를 고친다**

- description을 이 글로 바꾼다(spec 「description」):
  `아키텍처·보안·고위험 변경의 판단, 설계 분해, 처음 보는 눈으로 하는 마지막 교차검토, 심각도 높은 지적의 반박 검증을 맡는다. 코드를 고치지 않는다. 되돌리기 어려운 아키텍처·보안 결정과 판정이 엇갈려 풀리지 않는 일은 judge-max에 맡긴다.`
- `## 더 무거운 모델이 필요하면` 절(제목과 한 줄)을 지운다.
- `## 규칙` 목록 끝에 한 줄을 더한다:
  `- 맡은 일이 \`judge-max\`의 일(되돌리기 어려운 아키텍처·보안 결정, 판정이 엇갈려 풀리지 않는 일)이면 그 까닭을 적어 돌려준다. 올릴지는 부른 쪽이 정한다.`

- [ ] **Step 5: judge-max.md를 만든다**

frontmatter(이 순서):

```
---
name: judge-max
description: 되돌리기 어려운 아키텍처·보안 결정, judge-high 판정이 엇갈리거나 같은 문제를 두 번 맡겨도 풀리지 않는 일만 맡는다. 부를 때 무엇을 왜 올리는지 사용자에게 한 줄로 알린다. 그 밖의 판단·검토는 judge-high에 맡긴다. 코드를 고치지 않는다.
tools: Read, Grep, Glob, Bash, WebFetch
model: fable
effort: high
---
```

본문:
- `# 결정·재판정 담당` 아래에 맡는 일 두 줄(spec 「Fable 등급」의 두 항목).
- `## 규칙`: `judge-high`의 `## 규칙` 줄을 마지막 `judge-max` 줄만 빼고 그대로 옮기고, 끝에 두 줄을 더한다:
  - `- 판정이 엇갈린 일을 받으면 엇갈린 판정마다 무엇을 근거로 했는지 먼저 적고, 어느 근거가 맞는지 코드 자리로 가린다.`
  - `- 맡은 일이 위 두 가지가 아니면(보통 판단·검토) 멈추고 \`judge-high\`에 다시 맡기라고 돌려준다.`
- `## 출력`: `judge-high`의 절을 그대로 옮긴다.
- 본문에 모델 이름을 쓰지 않는다.

- [ ] **Step 6: classification.md의 사람이 쓰는 부분을 고친다**

- 「어떤 일을 누구에게」 표 끝에 `| 되돌리기 어려운 아키텍처·보안 결정, 판정이 엇갈려 풀리지 않는 일 | \`judge-max\` |`.
- `## 승인이 필요한 모델로 올리기` 절 전체를 이 절로 바꾼다:

```markdown
## `judge-max`로 올리기

올릴 수 있는 일은 둘이다.

- 되돌리기 어려운 아키텍처·보안 결정
- `judge-high` 판정이 서로 엇갈리거나, 같은 문제를 두 번 맡겨도 풀리지 않을 때

메인 세션은 이 일이면 사용자에게 묻지 않고 `judge-max`를 부른다. 부를 때 무엇을 왜 올리는지 한 줄로 알린다. 그 밖의 일에는 쓰지 않는다.
```

- [ ] **Step 7: 생성하고 전체 시험을 돌린다**

Run: `uv run python scripts/render.py && uv run python scripts/render.py --check; echo "exit=$?"`
Expected: `exit=0`. 생성 구간 표에 `| \`judge-max\` | \`fable\` | \`high\` | Fable 5.2 |` 행, `확인한 날: 2026-11-13`.

Run: `uv run pytest -q -p no:cacheprovider`
Expected: 모두 통과(`test_judge_rules_stay_in_sync`, `judge-max`의 `test_no_agent_tool`·yaml·별칭 검사 포함).

- [ ] **Step 8: 커밋**

```bash
git add tiers.toml agents docs/classification.md tests/test_repo.py
git commit -m "grade-agents: Fable 등급 judge-max 추가"
```

---

### Task 3: 문서·버전 맞추기

**Files:**
- Modify: `plugins/grade-agents/README.md`
- Modify: `plugins/grade-agents/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`
- Modify: `CATALOG.md`

- [ ] **Step 1: 플러그인 README를 고친다**

- 첫 단락: 「5종」 → 「6종」, 목록에 `judge-max`, 마지막 문장(「사용자 승인이 필요한 모델은 … ask 규칙으로 막는다」)을 「Fable은 `judge-max` 한 등급에만 배정한다」로.
- 「설치」: `gate.py` 코드 블록과 그 아래 문단을 지우고, spec 「설치」의 0.1.0 정리 문단(`Agent(model:fable)`과 `CLAUDE_CODE_SUBAGENT_MODEL`을 손으로 지운다)을 넣는다. `프로젝트 고유 규칙은 …` 문장은 남긴다.
- `## 승인이 필요한 모델`부터 `### 즉석 기본값의 부작용` 절 끝까지를 spec 「Fable 등급」 절(본문과 「알고 열어 두는 것」)로 바꾼다. 제목은 `## Fable 등급`.
- 「모델이 바뀔 때」: 1단계의 「승인이 필요한 새 계열이면 … 이름을 넣는다」를 「새 계열이면 `[models]`에 더한다」로, 4단계(`gate.py`)를 지우고 5단계를 4단계로.
- 「실제 확인」 표: 3·4번 결과 칸 끝에 「→ 0.2.0에서 승인 장치를 없애 해당 없음」, 5번을 「해당 없음(0.2.0에서 즉석 기본값을 없앰)」. 7·8번 행은 Task 4가 채운다.

- [ ] **Step 2: 버전과 설명을 올린다**

- `plugin.json`: `"version": "0.2.0"`, description `작업량 등급 서브에이전트 6종(finder-low, routine-medium, worker-medium, worker-high, judge-high, judge-max). 모델 배정은 tiers.toml에서 생성한다. 외부 전송 없음.`
- `marketplace.json`의 grade-agents: `"version": "0.2.0"`, description `작업량 등급 서브에이전트 6종. 모델 배정은 tiers.toml 하나에서 생성하고, Fable은 judge-max 등급으로만 쓴다`.

- [ ] **Step 3: CATALOG를 고친다**

- grade-agents 행 효과 측정 칸은 Task 4가 채우니 그대로 두고, 마지막 칸의 「Desktop·Workflow의 Fable 승인, 즉석 기본값(항목 5).」를 지운다.
- 「바뀐 기록」에 한 줄: `- 2026-11-13: grade-agents 0.2.0. Fable 승인 장치(ask 규칙, gate.py, 즉석 기본값)를 걷어 내고 Fable 등급 judge-max를 더했다. 승인 규칙이 Desktop과 Workflow에서 걸리지 않아서다.`

- [ ] **Step 4: 남은 글자를 찾는다**

Run: `grep -rn "gate.py\|gated\|subagent_default\|승인이 필요한\|5종" plugins/grade-agents --include='*.md' --include='*.toml' --include='*.json' --include='*.py'; grep -n "grade-agents" README.md CATALOG.md`
Expected: 첫 `grep`은 README 「설치」의 0.1.0 정리 문단과 「실제 확인」 표의 옛 결과 말고는 아무것도 없다. 루트 README에 grade-agents 고유 문구가 있으면 맞춘다.

Run: `uv run pytest -q -p no:cacheprovider && uv run python scripts/render.py --check && (cd ../.. && claude plugin validate .)`
Expected: 모두 통과, `✔ Validation passed`.

- [ ] **Step 5: 커밋**

```bash
git add plugins/grade-agents/README.md plugins/grade-agents/.claude-plugin/plugin.json .claude-plugin/marketplace.json CATALOG.md
git commit -m "grade-agents: 0.2.0 문서와 버전"
```

---

### Task 4: 실제 settings 정리와 실제 세션 확인 (메인 세션이 사용자와 함께)

서브에이전트에 맡기지 않는다. 단계마다 먼저 묻는다.

**Files:**
- Modify: `plugins/grade-agents/README.md` (「실제 확인」 7·8번 행), `CATALOG.md` (효과 측정 칸)

- [ ] **Step 1: 사용자에게 묻고 실제 settings에서 두 항목을 지운다 (항목 8)**

먼저 `~/.claude/settings.json`을 scratchpad에 복사해 둔다. `permissions.ask`에서 `Agent(model:fable)`을, `env`에서 `CLAUDE_CODE_SUBAGENT_MODEL`을 지우고, 빈 `ask`·`permissions`·`env`가 되면 그 키도 지운다. 나머지 키·순서·들여쓰기 2칸·끝 줄바꿈은 그대로. 바꾼 뒤 `diff`로 원본과 비교해 보여 준다.
Expected: `diff`에 그 두 항목(과 빈 키)만 빠진다.

- [ ] **Step 2: 사용자에게 묻고 judge-max가 Fable로 도는지 본다 (항목 7)**

Fable 한 번 호출 비용이 든다. scratchpad에서:

Run: `claude -p 'Agent 도구로 subagent_type "grade-agents:judge-max"를 불러 "OK 한 단어만 답해"라고 시켜. 다른 일은 하지 마.' --output-format stream-json --verbose --model sonnet < /dev/null > jm.jsonl`
`result` 이벤트의 `modelUsage`를 읽는다.
Expected: `claude-fable-5-2` 키가 있다.

- [ ] **Step 3: 결과를 적고 커밋한다**

README 「실제 확인」 표에 7·8번 행을 날짜·버전과 함께 적고, CATALOG 효과 측정 칸을 `실제 세션 확인 n/5 (날짜)`(남은 항목 1·2·6·7·8 중 통과 수)로 바꾼다. 기대와 다르면 사용자에게 알리고 spec 해당 절로 돌아간다.

```bash
git add plugins/grade-agents/README.md CATALOG.md
git commit -m "grade-agents: 0.2.0 실제 세션 확인 결과"
```
