# grade-agents 설계

날짜: 2026-11-11 · 개정: 2026-11-13 (Fable 승인 장치를 걷어 내고 `judge-max` 등급을 더함) · 상태: 개정 검토 대기

## 목적

작업량 등급 서브에이전트 6종과 작업량 분류 기준을 hg-claude-kit에서 원본으로 관리한다. 모델 배정은 표 파일 하나(`tiers.toml`)에서만 고친다. 새 모델이나 새 계열이 나오면 그 파일을 고치고 `render.py`를 돌린다.

출발점은 사내 프로젝트의 `.claude/agents/` 등급 에이전트와 `docs/conventions/workspace.md` 「서브에이전트 모델 선택」이다. 거기서는 모델 이름이 에이전트 frontmatter, README 표, 기준표, 워크플로 스크립트, Codex 변환 스크립트 다섯 군데에 박혀 있고, 같은 5종이 FE(`fe-*`)·Docs(`docs-*`)·워크스페이스 루트에 사본으로 따로 있다.

## 정한 것

| 물음 | 결정 |
|---|---|
| 원본 범위 | 등급 6종과 분류 기준표만. 단계 에이전트 4종은 넣지 않는다 |
| 적용 대상 | 팀 저장소와 개인 프로젝트 둘 다. 이번에는 개인 갈래만 만든다 |
| 적용 방식 | 원본 하나를 두 갈래로: 개인은 플러그인 설치, 팀 저장소는 파일을 생성해 커밋 |
| 팀 갈래 시점 | 사내 프로젝트에 실제로 적용할 때 만든다. 설계 메모만 이 문서 끝에 남긴다 |
| 이름 | `finder-low` · `routine-medium` · `worker-medium` · `worker-high` · `judge-high` 유지, Fable 등급은 `judge-max`. 접미어는 effort 값이 아니라 작업 등급(일의 무게)이다 |
| Fable | 등급 `judge-max`에 배정한다. 맡는 일은 되돌리기 어려운 아키텍처·보안 결정과 `judge-high`로 풀리지 않는 판정뿐이다. 승인 장치는 두지 않고, 메인 세션이 그 일이면 알아서 부른다 |
| 즉석 서브에이전트 기본값 | 정하지 않는다. `model` 없는 즉석 서브에이전트는 메인 세션 모델을 물려받는다 |

### 이름과 effort의 관계

같은 유형의 일에서 effort가 달라지는 경우는 셋이고, 다루는 자리가 다르다.

| 경우 | 다루는 자리 |
|---|---|
| 같은 유형인데 일의 무게가 다르다 (보통 구현과 고위험 구현) | 이름. 본문 규칙도 다르므로 정의를 따로 둔다 |
| 보통 일인데 이번 한 건만 까다롭다 | 호출 인자 `effort` |
| 같은 무게인데 모델이 바뀌어 맞는 effort가 달라졌다 | `tiers.toml` |

### 개정 (2026-11-13)

처음 설계는 Fable을 등급에 넣지 않고, 권한 ask 규칙 `Agent(model:fable)`로 호출마다 사용자 승인을 받았다. 2026-11-12 실제 확인에서 이 규칙은 터미널 CLI의 Agent 도구 호출에만 걸렸다. Desktop 앱(2.1.321)의 Agent 호출과 Workflow `agent()`는 CLI와 Desktop 모두에서 승인 창 없이 Fable로 돌았다. 사용자는 승인을 요구하지 않기로 정했다. 그래서 다음을 걷어 냈다.

- `tiers.toml`의 `gated`와 `subagent_default`
- `render.py` 검사 「등급 model이 gated에 없다」와 「gated 이름이 `judge-high` description에 있다」
- `scripts/gate.py`와 그 시험
- 설치 단계의 settings 병합, 즉석 기본값 `CLAUDE_CODE_SUBAGENT_MODEL`

대신 Fable 등급 `judge-max`를 더했다. Fable을 핵심 작업에만 쓰는 것은 `judge-max`와 `judge-high`의 description, 그리고 메인 세션의 지시로만 지켜진다.

## 문서로 확인한 사실

2026-11-11에 받은 공식 문서 기준이다. 문서는 Claude Code v2.1.321 이후의 동작을 적고 있다.

**전제: Claude Code v2.1.321 이상.** 이 컴퓨터의 CLI는 2.1.296이라 올려야 한다. 2.1.296에서는 `fable`이 Fable 5.1을 가리키고 `best`가 `fable`과 같은 모델을 가리킨다. ([model-config](https://code.claude.com/docs/en/model-config.md) 「Version history」)

모델과 effort:

- frontmatter `model`은 `sonnet` · `opus` · `haiku` · `fable` · 전체 모델 ID · `inherit`을 받는다. 호출 인자 `model`은 네 별칭만 받는다. ([sub-agents](https://code.claude.com/docs/en/sub-agents.md))
- 별칭은 제공자가 권하는 버전을 가리키고 시간이 지나면 바뀐다. 계열과 무관하게 가장 좋은 모델을 뜻하는 별칭은 없다(v2.1.321부터 `best`는 `opus`다).
- 모델 결정 순서: 호출 인자 `model` → frontmatter `model` → `CLAUDE_CODE_SUBAGENT_MODEL` → 메인 세션 모델.
- `CLAUDE_CODE_SUBAGENT_MODEL`은 내장 Explore·Plan의 모델을 바꾸지 않는다. fork는 메인 세션의 모델로 돈다. `inherit`으로 두면 설정하지 않은 것과 같다.
- effort 결정 순서: `CLAUDE_CODE_EFFORT_LEVEL` → 호출 인자 `effort` → frontmatter `effort` → 세션. 값은 `low` · `medium` · `high` · `xhigh` · `max`다. 모델이 받지 않는 값은 그 아래에서 받는 가장 높은 값으로 내려간다.
- frontmatter에 변수를 쓰는 방법은 문서에 없다. 그래서 표를 읽어 두 줄을 채우는 생성 단계를 둔다.
- 서브에이전트는 기본으로 자기 서브에이전트를 부를 수 있다(메인 아래 세 층까지). 막으려면 `tools`에서 `Agent`를 빼거나 `disallowedTools`에 넣는다.
- 호출 인자 `model`은 그 서브에이전트를 `SendMessage`로 다시 깨울 때도 유지되고, 그때는 새 `Agent` 호출이 생기지 않는다.

플러그인:

- 플러그인 에이전트는 `플러그인:에이전트`로 등록된다. frontmatter에서 `model` · `effort` · `tools` · `disallowedTools`를 쓸 수 있고 `hooks` · `mcpServers` · `permissionMode` · `initialPrompt`는 무시된다. ([plugins/components](https://code.claude.com/docs/en/plugins/components.md))
- 플러그인은 권한 규칙을 실을 수 없다. 플러그인 `settings.json`에서 살아남는 키는 `agent`와 `subagentStatusLine`뿐이다.
- 로컬 경로로 더한 마켓플레이스의 플러그인은 캐시로 복사되지 않고 그 자리에서 읽힌다. 고친 내용은 다음 세션이나 `/reload-plugins`부터 걸린다. ([plugins/loading](https://code.claude.com/docs/en/plugins/loading.md)) (실제 확인 6번)


### 실제 세션으로 확인할 것

구현 끝에 확인하고 결과를 플러그인 README에 적는다. 하나라도 기대와 다르면 그 항목을 사용자에게 알리고 이 문서로 돌아와 해당 절을 다시 정한다. 번호는 처음 설계 때 것을 그대로 둔다.

1. `claude --version`이 2.1.321 이상이다.
2. `subagent_type`에 `grade-agents:worker-medium`을 써서 부를 수 있고, 표의 모델로 돈다.
3. 메인 세션에서 `model: "fable"` 호출에 승인 창이 뜬다. 승인 창이 뜨는 것만 보고 거부한다. → 2026-11-12: CLI 2.1.322에서만 성립. Desktop 2.1.321에서는 승인 창 없이 Fable로 돌았다. 2026-11-13 개정으로 없앴다.
4. Workflow 스크립트의 `agent()` 호출에 `model: 'fable'`을 주면 같은 규칙이 걸린다. 문서에는 워크플로가 띄운 서브에이전트가 권한 규칙을 쓴다고만 나온다. → 2026-11-12: 성립 안 함. CLI 2.1.322와 Desktop 2.1.321 모두 승인 창 없이 Fable로 돌았다. 2026-11-13 개정으로 없앴다.
5. 메인 세션이 Fable일 때 `model` 없는 즉석 서브에이전트가 `subagent_default`의 모델로 돈다. → 확인 안 함. 2026-11-13 개정으로 없앴다.
6. 설치한 뒤 `~/.claude/plugins/installed_plugins.json`에서 `grade-agents@hg-claude-kit`의 `installPath`가 이 저장소를 가리킨다. 캐시 경로를 가리키면 「모델이 바뀔 때」 5단계를 버전 올리기·`marketplace update`·업데이트로 바꾼다. → 2026-11-12: `installPath`는 캐시를 가리켰지만 세션 시작 정보의 `plugins[].path`는 이 저장소였다. 판정은 실제로 읽는 경로로 하므로 성립. 5단계는 그대로 둔다.
7. `grade-agents:judge-max`를 부르면 Fable로 돈다. 메인을 sonnet으로 둔 `claude -p` 실행의 `modelUsage`에 `claude-fable-5-2`가 따로 잡히면 성립.
8. 실제 `~/.claude/settings.json`에 `Agent(model:fable)`과 `CLAUDE_CODE_SUBAGENT_MODEL`이 남아 있지 않다.

## 구조

```
plugins/grade-agents/
  .claude-plugin/plugin.json
  tiers.toml               등급 → model·effort
  agents/
    finder-low.md
    routine-medium.md
    worker-medium.md
    worker-high.md
    judge-high.md
    judge-max.md
  docs/classification.md   작업량 분류 기준표
  scripts/render.py        tiers.toml → agents·기준표
  tests/
  pyproject.toml           uv · pytest. 스크립트는 표준 라이브러리만 쓴다
  .python-version          3.12
  README.md
```

- `agents/*.md`는 원본이면서 플러그인이 읽는 파일이다. `render.py`는 그 안에서 `model:`과 `effort:` 두 줄만 고친다. 나머지는 사람이 쓴다.
- 스크립트는 플러그인 폴더에서 `uv run python scripts/<이름>.py`로 돌린다. `tomllib`가 필요해 Python 3.11 미만이면 안내하고 끝난다(`/usr/bin/python3`는 3.9.6이다).
- 이 마켓플레이스는 로컬 경로로 더해져 있어 플러그인 파일이 그 자리에서 읽힌다. 커밋하지 않은 편집도 다음 세션부터 걸린다. `render.py`를 전부 쓰거나 아무것도 안 쓰게 만드는 까닭이다. 2026-11-12에 CLI 2.1.322에서 실제 확인 6번으로 확인했다(`installed_plugins.json`의 `installPath`는 캐시를 가리키지만 쓰이지 않는다).

## tiers.toml

```toml
checked = "2026-11-13"       # 아래 버전을 마지막으로 확인한 날

[models]                     # 쓸 수 있는 별칭과, 확인한 날 Anthropic API에서 가리키던 버전
haiku = "Haiku 5.5"
sonnet = "Sonnet 5.5"
opus = "Opus 5.5"
fable = "Fable 5.2"

[tiers.finder-low]
model = "haiku"
effort = "low"

[tiers.routine-medium]
model = "haiku"
effort = "medium"

[tiers.worker-medium]
model = "sonnet"
effort = "medium"

[tiers.worker-high]
model = "sonnet"
effort = "high"

[tiers.judge-high]
model = "opus"
effort = "high"

[tiers.judge-max]
model = "fable"
effort = "high"
```

- `model`은 `[models]`에 적은 별칭만 쓴다. 같은 계열의 새 버전은 손대지 않아도 따라간다. `best` · `opusplan` · `inherit` · 전체 모델 ID는 `[models]`에 넣지 않는다. 어느 모델로 풀릴지가 버전이나 세션에 따라 달라져 모델 보정 검사와 기준표의 「확인한 버전」이 맞지 않게 되기 때문이다.
- `[models]`의 버전 이름은 사람이 적는 기록이다. 별칭이 조용히 새 버전을 가리키게 돼도 이 저장소는 알 수 없다. 사람이 이 표를 고쳐야 아래의 모델 보정 검사가 움직인다.

## render.py

`uv run python scripts/render.py [--check]`

전부 쓰거나 아무것도 쓰지 않는다. 쓸 내용을 메모리에서 다 만들고 아래 검사를 모두 통과했을 때만 쓴다. 검사에 걸리면 걸린 항목을 모두 찍고 종료 코드 1로 끝난다.

검사:

1. `[tiers]`의 이름과 `agents/*.md`의 파일 이름(확장자 제외)이 하나씩 짝이 맞는다. 각 파일 frontmatter의 `name`이 파일 이름과 같다.
2. 등급의 `model`이 모두 `[models]`에 있다.
3. `effort`가 `low` · `medium` · `high` · `xhigh` · `max` 중 하나다. 모델별로 받는 값이 다른지는 검사하지 않는다.
4. 에이전트 본문의 `## 모델 보정 (버전 이름)` 제목마다 괄호 안 이름이 `models[그 등급의 model]`과 같다. 다르면 그 블록을 「다시 볼 것」으로 찍는다.
5. `docs/classification.md`에 `<!-- tiers:begin -->`과 `<!-- tiers:end -->`가 이 순서로 하나씩 있다.

쓰기:

- frontmatter는 첫 줄 `---`부터 다음 `---` 줄까지다. 파일이 `---`로 시작하지 않으면 실패한다.
- 그 안에서 `model:`로 시작하는 줄과 `effort:`로 시작하는 줄을 `model: <값>` · `effort: <값>`으로 바꾼다. 줄이 없으면 닫는 `---` 바로 앞에 넣는다. 본문과 다른 frontmatter 줄은 건드리지 않는다.
- 줄 끝은 LF다. CRLF가 든 파일은 실패한다.
- `docs/classification.md`의 두 표시 사이를 생성한 내용으로 바꾼다. 내용은 에이전트 · model · effort · 확인한 버전 표와 `checked` 날짜다.

`--check`는 쓰지 않는다. 검사에 걸리거나 쓸 내용이 지금 파일과 다르면 종료 코드 1이다.

## 에이전트

BE의 5종에서 프로젝트 전용 규칙을 걷어 내고 범용 규칙만 남긴다. 여기에 Fable 등급 `judge-max`를 더한다. 한국어로 쓴다.

| 에이전트 | 도구 제한 (frontmatter) | 맡는 일 |
|---|---|---|
| `finder-low` | `tools: Read, Grep, Glob, Bash` | 파일·심볼 찾기, 목록, 상태 확인, 로그 분류. 읽기만 한다 |
| `routine-medium` | `disallowedTools: Agent` | 정형 추출·집계, 바꿀 자리와 모양이 다 정해진 기계적 수정 |
| `worker-medium` | `disallowedTools: Agent` | 일반 분석·구현·디버깅·테스트, 분류·정찰, 지적 하나의 반박 검증, 문서·요약 |
| `worker-high` | `disallowedTools: Agent` | 고위험 변경(트랜잭션·잠금·보안·핵심 경로 구조)의 구현, 앞선 판정을 뒤집는 판정 |
| `judge-high` | `tools: Read, Grep, Glob, Bash, WebFetch` | 판단, 설계 분해, 처음 보는 눈의 마지막 교차검토, 심각도 높은 지적의 반박 검증. 고치지 않는다 |
| `judge-max` | `tools: Read, Grep, Glob, Bash, WebFetch` | 되돌리기 어려운 아키텍처·보안 결정, `judge-high` 판정이 엇갈리거나 같은 문제를 두 번 맡겨도 풀리지 않는 일. 고치지 않는다 |

여섯 모두 `Agent` 도구가 없다. 「다른 에이전트를 부르지 않는다」를 지시가 아니라 도구 제한으로 막는다. 등급 에이전트가 스스로 다른 모델의 서브에이전트를 띄우는 길도 함께 닫힌다.

### 여섯에 공통인 규칙

- 한 줄 결론을 먼저 쓰고 근거를 `파일:줄`이나 실행한 명령으로 댄다.
- 돌린 것과 안 돌린 것을 갈라 적는다.
- 등급을 넘는 일이면 멈추고, 왜 넘는지 한 줄과 근거 자리, 다시 맡길 에이전트 이름을 돌려준다.
- 「못 찾았다」에는 찾은 범위를 붙인다. 추측으로 채우지 않는다. 확신이 없으면 그렇게 적는다.
- 받지 않은 일은 하지 않는다. 도움이 될 것 같으면 끝에 한 줄로 적는다.
- 명령의 성패를 파이프 뒤 종료 코드로 판정하지 않는다. 출력을 파일로 받고 종료 코드를 따로 찍는다.
- 비밀값을 로그·커밋·출력에 남기지 않는다. push·PR·기본 브랜치 변경은 하지 않는다.

### 에이전트별 규칙

`finder-low`

- 파일을 만들거나 고치지 않는다. `git` · `gh`는 조회 명령만 쓴다. 빌드·테스트를 돌리지 않는다.
- 결론만 돌려준다. 파일 내용을 통째로 붙이지 않는다.

`routine-medium`

- 목록의 자리를 끝까지 돈다. 등급을 넘는 자리는 모아 두고 나머지를 마친 뒤 함께 돌려준다.
- 뽑은 값은 원문 그대로 옮긴다. 수는 직접 센 것만 쓰고 센 명령을 함께 적는다.
- 고쳤으면 실제 검사를 돌린 뒤에만 끝났다고 한다. 검사를 못 돌렸으면 무엇을 왜 못 돌렸는지 적는다.
- 판단, 고위험 경로, 문서·PR 본문처럼 남는 글은 맡지 않는다.

`worker-medium`

- 코드를 고칠 때는 실패 테스트를 먼저 쓴다. 버그는 재현 테스트를 먼저 쓴다. 그 변경을 겨눈 테스트를 돌린다.
- 실패하는 기존 테스트를 지우거나 끄지 않는다.
- 반박 검증은 「성립 / 성립 안 함 / 일부 성립」 중 하나로 답하고 근거를 코드 자리로 보인다.
- 문서·요약은 원문에 있는 사실만 옮긴다. 수는 직접 셀 수 있을 때만 쓴다.

`worker-high`

- `worker-medium`의 구현 규칙을 그대로 따른다.
- 설계 판단은 하지 않는다. 어떻게 만들지가 정해지지 않았으면 멈추고 무엇이 안 정해졌는지 돌려준다.
- 고친 한 곳만 되돌려 새 검사가 붉어지는지 잰다.
- 거절만 재는 검사에는 통과해야 하는 표본을 하나 붙인다.
- 잠금·경합은 「기다리는가」가 아니라 「어느 값을 읽었나」로 잰다.
- 앞선 판정을 뒤집을 때는 전에 무엇이 막았고 지금 무엇이 그것을 풀었는지를 코드 자리로 보인다.
- 보고에 「이 변경분에 `judge-high` 리뷰가 필요하다」를 적는다.

`judge-high`

- 파일을 만들거나 고치지 않는다. `git` · `gh`는 조회 명령만 쓴다.
- 원저자의 가정을 그대로 받지 않고 인용된 자리를 직접 연다.
- 지적을 성질로 다시 써서 같은 성질을 가진 형제 자리를 훑는다.
- 반박 검증은 세 값 중 하나로 답한다. 안 쓰기로 할 때도 코드로 보인다.
- 설계 분해는 갈래마다 범위·순서·서로 부딪히는 자리를 적고, 합친 자리에서 한 번 재는 단계를 넣는다.
- 판단은 권하는 안 하나와 까닭, 택하지 않은 안마다 까닭 한 줄로 낸다. 검토는 심각도순으로 내고 끝에 **GO / GO-with-fixes / NO-GO**를 적는다.
- 맡은 일이 `judge-max`의 일(되돌리기 어려운 아키텍처·보안 결정, 판정이 엇갈려 풀리지 않는 일)이면 그 까닭을 적어 돌려준다. 올릴지는 부른 쪽이 정한다. 본문의 「더 무거운 모델이 필요하면」 절은 이 규칙으로 바꾼다.

`judge-max`

- `judge-high`의 규칙을 그대로 따른다. 서브에이전트는 형제 정의를 보지 못하므로, `judge-high`의 규칙 문장(위 목록에서 마지막 한 줄을 뺀 것)과 `## 출력` 절을 그대로 옮겨 적는다. 두 파일에 같은 문장이 있는지 저장소 시험이 본다.
- 판정이 엇갈린 일을 받으면 엇갈린 판정마다 무엇을 근거로 했는지 먼저 적고, 어느 근거가 맞는지 코드 자리로 가린다.
- 맡은 일이 `judge-max`의 일이 아니면(보통 판단·검토) 멈추고 `judge-high`에 다시 맡기라고 돌려준다.

### 걷어 내는 것

gradle·detekt 명령, `git show origin/main:<경로>`로 정본 읽기, 이슈 크기 L·XL과 `gh issue view`, `workspace.md` 참조, 커밋 메시지 서명 규칙. 필요한 프로젝트는 자기 `CLAUDE.md`에 적는다.

본문은 형제 에이전트를 접두어 없는 이름으로 가리킨다. 플러그인으로 설치하면 실제 이름은 `grade-agents:worker-high`다.

### 모델 보정 블록

특정 모델의 버릇이나 제약을 메우는 규칙은 `## 모델 보정 (Haiku 5.5)`처럼 버전 이름을 단 블록에 따로 둔다. 처음에는 두 개다.

- `finder-low`: low에서 긴 지시를 받으면 찾기를 건너뛰거나 일찍 멈춘다. 찾기 명령을 실제로 돌리기 전에는 「없다」고 쓰지 않는다.
- `routine-medium`: 검사 없이 「끝났다」고 하는 일이 있다. 큰 파일은 통째로 읽지 않는다.

두 블록에 제공자 주의도 적는다: Amazon Bedrock·Google Cloud·Microsoft Foundry에서는 `haiku`가 Haiku 4.5를 가리켜 이 등급이 표대로 돌지 않는다.

등급의 모델이나 `[models]`의 버전 이름을 바꾸면 `render.py`가 이 블록들을 「다시 볼 것」으로 찍고 멈춘다. 블록을 고치거나 지우거나, 그대로 유효하면 제목의 버전 이름만 새 이름으로 바꾼다.

### description

description은 항상 메인 세션 컨텍스트에 실린다. 플러그인으로 설치한 프로젝트에는 기준표가 따라가지 않으므로, 언제 부르고 언제 부르지 않는지를 description에 적는다.

모델 이름은 사람이 쓰는 부분에 적지 않는다. 예외는 없다. `judge-high`의 description에는 「되돌리기 어려운 아키텍처·보안 결정과 판정이 엇갈려 풀리지 않는 일은 `judge-max`에 맡긴다」를, `judge-max`의 description에는 그 두 일만 맡고 그 밖의 판단·검토는 `judge-high`라는 것을 적는다. 이 두 문장이 메인 세션이 Fable을 언제 쓸지 정하는 유일한 안내다.

## docs/classification.md

- 작업 유형 → 에이전트 표 (사람이 씀, 모델 이름 없음)
- 에이전트 → model · effort · 확인한 버전 표 (생성)
- 원칙 (사람이 씀)
  - 충분한 가장 작은 등급을 고른다. 병렬로 부를 때도 일마다 따로 고른다.
  - 가장 높은 등급은 구현이 아니라 판단·설계 분해·교차검토에 쓴다. 결함을 잡는 값은 구현 모델의 등급보다 처음 보는 눈의 리뷰에서 나온다.
  - `worker-high`가 고친 변경분에는 `judge-high` 리뷰를 붙인다.
  - 비용은 «넣는 문맥 크기 × 턴 수»가 좌우한다. 여러 단계가 같은 사실을 쓰면 전문을 붙이지 않고 파일 경로로 가리킨다.
  - 자리만 채운 부실한 출력은 등급을 올리지 않고, 필수 칸을 기계로 검사해 그 건만 다시 돌린다.
- 한 건만 올리기: 호출 인자 `effort`를 쓰고, 왜 올리는지 한 줄을 적는다.
- `judge-max`로 올리기: 올릴 수 있는 일 (사람이 씀, 모델 이름 없음)

## Fable 등급

Fable은 `judge-max` 하나에만 배정한다. 승인 장치는 없다. 메인 세션이 아래 일이면 사용자에게 묻지 않고 `judge-max`를 부른다.

- 되돌리기 어려운 아키텍처·보안 결정
- `judge-high` 판정이 서로 엇갈리거나, 같은 문제를 두 번 맡겨도 풀리지 않을 때

부를 때 무엇을 왜 올리는지 사용자에게 한 줄로 알린다. 알리기만 하고 답을 기다리지 않는다.

### 알고 열어 두는 것

비용이 드는 Fable이 의도하지 않게 쓰일 수 있는 길이다. 막는 장치를 두지 않는다.

- **메인 세션이 Fable일 때** `model` 없는 즉석 서브에이전트, 내장 Plan, fork, `model: inherit`인 정의, `context: fork` 스킬이 Fable로 돈다.
- **호출 인자 `model: "fable"`** 은 어느 에이전트에 주어도 그대로 돈다. Workflow `agent()`도 같다.
- **다른 플러그인이나 프로젝트가 frontmatter에 `fable`을 적은 정의**는 그 모델로 돈다.
- 등급 에이전트는 `Agent` 도구가 없어 스스로 다른 서브에이전트를 띄우지 못한다. 이것만은 도구 제한으로 막힌다.

## 설치

```bash
claude update
```

```bash
claude plugin install grade-agents@hg-claude-kit --scope user
```

0.1.0에서 `gate.py`를 돌렸다면 `~/.claude/settings.json`에서 `permissions.ask`의 `Agent(model:fable)`과 `env.CLAUDE_CODE_SUBAGENT_MODEL`을 손으로 지운다. 지워서 빈 배열·빈 객체가 되면 그 키도 지운다. 이 저장소에서는 구현 끝에 사용자에게 물은 뒤 지운다.

프로젝트 고유 규칙은 그 프로젝트의 `CLAUDE.md`에 둔다.

## 모델이 바뀔 때

1. `tiers.toml`을 고친다. 등급의 `model` · `effort`, `[models]`의 버전 이름, `checked` 날짜. 새 계열이면 `[models]`에 더한다.
2. `render.py`를 돌린다. 「다시 볼 것」으로 나온 모델 보정 블록을 손보고 다시 돌린다.
3. 테스트를 돌리고 커밋한다. CATALOG.md의 바뀐 기록에 한 줄 적는다.
4. 새 세션부터 걸린다. 로컬 경로 마켓플레이스라 `marketplace update`는 필요 없다. 2026-11-12에 CLI 2.1.322에서 실제 확인 6번으로 확인했다(`installed_plugins.json`의 `installPath`는 캐시를 가리키지만 쓰이지 않는다).

## 시험

pytest로 자동 확인하는 것. 시험은 임시 폴더에 복사한 원본으로 돌린다.

render:

- 표대로 두 줄이 채워진다. 줄이 없던 파일에는 닫는 `---` 앞에 들어간다. 본문과 다른 frontmatter 줄은 바뀌지 않는다.
- 본문에 있는 `model:` 글자는 바뀌지 않는다.
- 기준표의 두 표시 사이가 생성한 내용으로 바뀌고, 표시 밖은 바뀌지 않는다.
- 검사 1~5가 각각 걸리는 입력에서 실패하고 아무 파일도 바뀌지 않는다. `---`로 시작하지 않는 파일과 CRLF 파일도 같다.
- `--check`: 맞으면 0, 어긋나면 1이고 파일을 건드리지 않는다.
- 두 번 돌린 결과가 같다.

저장소:

- 커밋된 `agents/*.md`와 `docs/classification.md`가 `tiers.toml`과 맞는다(`render.py --check`와 같은 검사).
- 여섯 정의 모두 `Agent` 도구를 쓸 수 없다(`tools`에 없거나 `disallowedTools`에 있다).
- `worker-medium`의 구현 규칙 두 문장이 `worker-high`에, `judge-high`의 규칙 문장과 `## 출력` 절이 `judge-max`에 그대로 있다.

그 밖에 `claude plugin validate .`로 형식을 확인하고, 「실제 세션으로 확인할 것」의 남은 항목(1·2·6·7·8)을 한 번 확인한다.

## 저장소의 다른 파일

- `.claude-plugin/marketplace.json`에 `grade-agents` 항목을 넣는다. 버전은 처음 `0.1.0`, 이번 개정으로 `0.2.0`이다(`plugin.json`도 같이).
- `CATALOG.md`에 한 줄을 넣는다. 종류는 서브에이전트, 상태는 `trial`, 외부 전송은 없음, 효과 측정 칸에는 실제 세션 확인 결과, harness-test 칸에는 「안 함」을 적는다.
- `README.md`의 「새 도구 추가」 1번에 서브에이전트는 `agents/`에 둔다는 말을 넣는다.

## 범위 밖

- 팀 저장소 갈래. 아래 메모 참조.
- 단계 에이전트 4종(`spec-reviewer` · `plan-reviewer` · `review-reviewer` · `build-engineer`).
- Codex TOML 생성. BE의 `sync_codex_agents.py`가 `.claude/agents/*.md`를 읽는다.
- harness-test로 등급별 효과를 재는 일.

## 팀 저장소 갈래 메모 (나중에)

사내 프로젝트에 실제로 적용할 때 그 저장소의 기존 파일을 보면서 만든다. 지금 정해 둔 방향과 그때 정할 것을 적어 둔다.

방향:

- `apply.py <프로젝트 경로>`가 `.claude/agents/<이름>.md` 6종을 접두어 없는 이름으로 생성한다. 그 프로젝트의 워크플로 스크립트는 `agentType`에 이 이름을 그대로 쓰고 있다.
- 생성 파일에는 생성물 표시를 넣고, 프로젝트의 덧붙임 파일(`.claude/grade-agents/overlays/<이름>.md`)을 본문 끝에 붙인다. gradle·detekt 같은 규칙은 여기로 옮긴다.

그때 정할 것:

- 플러그인을 사용자 범위로 설치한 채 팀 저장소에서 일하면 `grade-agents:worker-medium`과 `worker-medium`이 이름이 달라 둘 다 보인다. 그 프로젝트에서 플러그인을 끄는 절차(`claude plugin disable grade-agents@hg-claude-kit --scope local`)를 넣을지 실제로 보고 정한다.
- 생성물 표시가 없는 기존 파일을 덮어쓰는 조건, 표에서 빠진 등급의 생성물 처리, 적용한 프로젝트 목록을 어디에 둘지.
- 팀 저장소에 `judge-max`를 넣으면 팀원 모두가 승인 없이 Fable을 쓰게 된다. 넣을지, 팀에서는 승인 장치를 다시 둘지.
- `workspace.md` 기준표와 워크플로 스크립트에 박힌 모델 이름 정리.
