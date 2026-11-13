# grade-agents

작업량 등급 서브에이전트 6종(`finder-low` · `routine-medium` · `worker-medium` · `worker-high` · `judge-high` · `judge-max`)과 작업량 분류 기준을 담은 플러그인이다. 모델 배정은 `tiers.toml` 하나에서 고치고 `render.py`가 에이전트와 기준표에 반영한다. Fable은 `judge-max` 한 등급에만 배정한다.

> **전송:** 없음.

## 등급

어떤 일을 어느 에이전트에 맡기는지는 [docs/classification.md](docs/classification.md#어떤-일을-누구에게)의 표에 있다. 지금 배정은 `tiers.toml`과 기준표의 생성 구간에 있다.

## 설치

Claude Code v2.1.321 이상이 필요하다. 2.1.296에서는 `fable`이 Fable 5.1을 가리키고 `best`가 `fable`과 같은 모델을 가리킨다.

```bash
claude update
```

```bash
claude plugin install grade-agents@hg-claude-kit --scope user
```

0.1.0에서 `gate.py`를 돌렸다면 `~/.claude/settings.json`에서 `permissions.ask`의 `Agent(model:fable)`과 `env.CLAUDE_CODE_SUBAGENT_MODEL`을 손으로 지운다. 지워서 빈 배열·빈 객체가 되면 그 키도 지운다.

프로젝트 고유 규칙은 그 프로젝트의 `CLAUDE.md`에 둔다.

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

## 모델이 바뀔 때

1. `tiers.toml`을 고친다. 등급의 `model` · `effort`, `[models]`의 버전 이름, `checked` 날짜. 새 계열이면 `[models]`에 더한다.
2. `render.py`를 돌린다. 「다시 볼 것」으로 나온 모델 보정 블록을 손보고 다시 돌린다. `tiers.toml`에 쓰지 않는 키(0.1.0의 `gated` 같은 것이나 오타)가 있으면 경고만 띄우고 진행한다.
3. 테스트를 돌리고 커밋한다. CATALOG.md의 바뀐 기록에 한 줄 적는다.
4. 새 세션(또는 `/reload-plugins`)부터 걸린다. 로컬 경로 마켓플레이스라 플러그인을 이 저장소에서 바로 읽으므로 버전을 올리거나 업데이트할 필요가 없다(아래 「실제 확인」 6번). `installed_plugins.json`의 `installPath`가 캐시를 가리켜도 그 복사본은 쓰이지 않는다.

## 개발

플러그인 폴더에서:

```bash
uv run pytest -q
```

```bash
uv run python scripts/render.py --check
```

## 실제 확인

| 항목 | 결과 | 날짜·버전 |
|---|---|---|
| 1. 버전 2.1.321 이상 | 통과. `claude update`로 2.1.296 → 2.1.322. Desktop 앱은 자기가 묶은 2.1.321을 쓴다 | 2026-11-12, CLI 2.1.322 |
| 2. 등급 에이전트가 표의 모델로 돎 | 통과. 메인 sonnet에서 `grade-agents:finder-low`를 부르자 `claude-haiku-5-5` 사용량이 따로 잡혔다. `worker-medium`도 불렸지만 메인과 같은 sonnet이라 구별되지 않는다 | 2026-11-12, CLI 2.1.322 (`claude -p`) |
| 3. `model: "fable"` 호출에 승인 창 | CLI만 통과. `claude -p`(default 모드)에서 `judge-high` + `model: "fable"`은 거부되고, `model` 없는 같은 호출은 opus로 돌았다. Desktop에서는 승인 창 없이 `claude-fable-5-2`로 돌았다 → 0.2.0에서 승인 장치를 없애 해당 없음 | 2026-11-12, CLI 2.1.322 / Desktop 2.1.321 |
| 4. Workflow `agent()`에 같은 규칙 | 실패. CLI 대화형 세션과 Desktop 모두 `agent(…, { agentType: 'grade-agents:judge-high', model: 'fable' })`이 승인 창 없이 `claude-fable-5-2`로 돌았다 → 0.2.0에서 승인 장치를 없애 해당 없음 | 2026-11-12, CLI 2.1.322 / Desktop 2.1.321 |
| 5. 메인이 Fable일 때 즉석 서브에이전트가 sonnet | 해당 없음 (0.2.0에서 즉석 기본값을 없앰) | — |
| 6. 이 저장소에서 바로 읽음 | 통과. 세션 시작 정보(`system/init`의 `plugins`)에 `path`가 이 저장소의 `plugins/grade-agents`로 나온다. `claude plugin update`도 「read from its folder: nothing to update」라고 답한다. `installed_plugins.json`의 `installPath`는 `~/.claude/plugins/cache/hg-claude-kit/grade-agents/0.1.0`(설치 때 복사본)을 가리키지만 쓰이지 않는다. Desktop도 같다. 캐시의 0.1.0 복사본에는 `judge-max.md`가 없는데 Desktop 세션에 `grade-agents:judge-max`와 0.2.0의 judge-high 설명이 올라왔다 | 2026-11-12, CLI 2.1.322 / 2026-11-13, Desktop 2.1.321 |
| 7. `judge-max`가 Fable로 돎 | 통과. 메인 sonnet에서 `grade-agents:judge-max`를 부르자 `claude-fable-5-2` 사용량($0.054)이 따로 잡혔다. 승인 창이나 거부는 없었다 | 2026-11-13, CLI 2.1.323 (`claude -p`) |
| 8. 실제 settings에 0.1.0 항목이 없음 | 통과. `~/.claude/settings.json`에서 `Agent(model:fable)`과 `CLAUDE_CODE_SUBAGENT_MODEL`을 지웠다. 병합 전과 같은 590바이트, 권한 0600 | 2026-11-13 |
