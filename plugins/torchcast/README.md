# torchcast-mcp

판단 전용 모델 API인 torchcast(`torchcast-decision-4b-v1.3`)를 Claude Code에서 쓰는 MCP 도구로 감싼다.
로그 수천 줄, 이슈·PR 목록, 테스트 실패, 리뷰 지적처럼 항목이 많을 때 Claude가 전부 읽지 않고 먼저 거르거나 분류하게 해서 토큰과 시간을 줄이는 것이 목적이다.

언제 쓰나: 의미를 읽어야 갈리는 판단이 항목 수십~수천 개에 필요할 때 쓴다. 키워드나 예외 이름만으로는 안 갈리는 일이다. 정확한 개수 세기, 합계, 정해진 문자열이나 형식(상태 코드, 레벨 이름)으로 갈리는 일은 grep/awk가 더 빠르고 정확하다.

언어와 SDK는 Python + 공식 `mcp` SDK(2.x, FastMCP의 후속인 `MCPServer`) + uv로 정했다. 공식 SDK 중 데코레이터 한 줄로 도구를 만들 수 있어 코드가 가장 짧고, uv를 쓰면 등록 명령 하나로 의존성까지 잡힌다.

> **보안:** 항목 내용은 NordVPN Meshnet의 다른 PC(`100.112.79.59:8011`)로 인증 없는 평문 HTTP로 간다. 비밀값(API key, 토큰, `.env`)이나 고객 개인정보는 보내지 않는다. 도구 설명문에도 같은 내용을 넣었다.
> 보내기 전에 흔한 비밀값 형식을 `[MASKED]`로 바꾼다. 대상은 `sk-ant-`·`sk-`·`ghp_`·`github_pat_`·`AKIA`·`xox?-`·`AIza` 키, JWT, PEM 개인 키, `Bearer` 토큰, `password=`·`token:`·`api_key=` 같은 키-값, URL 안의 비밀번호, 객체의 민감한 키 이름(`password`, `token`, `authorization` 등)이다. 최선 노력일 뿐이므로 이것을 믿고 민감한 파일을 보내지 않는다.

## 도구

| 도구 | 용도 |
|---|---|
| `classify` | 항목을 같은 질문으로 하나씩 판단한다. 항목마다 요청 하나를 순서대로 보낸다. 항목은 파일 경로(`path`)나 배열(`items`)로 준다. `out`을 주면 모든 행을 TSV/JSONL 파일로 쓰고 도구 출력에는 집계와 확인할 행만 온다. |
| `ask` | `/v1/systemone`을 원형 그대로 호출한다. 상황 하나에 질문 여러 개. |
| `health` | 서버 상태, 모델 이름, 왕복 지연. |

### 왜 파일 모드가 기본인가

항목을 `items` 인자로 주려면 Claude가 먼저 내용을 읽고(입력 토큰), 그것을 다시 도구 인자로 써야 한다(출력 토큰, 더 비싸고 느리다). 대량 항목에서는 직접 읽는 것보다 비용이 커진다. `path`를 주면 MCP 서버가 파일을 직접 읽으므로 항목 내용이 Claude의 컨텍스트를 지나가지 않는다. Claude가 받는 것은 `keep`으로 고른 행과 집계뿐이다. 명령 출력이라면 먼저 파일로 저장해서(`pytest ... > /tmp/out.txt`) 넘긴다.

`classify` 입력

| 인자 | 설명 |
|---|---|
| `question` | 짧고 분명한 질문(필수) |
| `type` | `choice`(선택지 2~26개), `score`(단계 2~10개, 낮은 단계부터), `noul`(예/아니오)(필수) |
| `path` | 항목을 읽을 파일. `items`와 둘 중 하나만 준다 |
| `split` | `lines`(한 줄이 한 항목, 기본), `jsonl`(줄마다 JSON, 파싱에 실패하면 문자열), `blank`(빈 줄로 나뉜 블록). 빈 줄과 빈 블록은 버린다 |
| `grep` | 보내기 전에 항목을 거르는 정규식(파이썬 `re.search`) |
| `offset` | grep 뒤 항목 중 몇 번째부터 처리할지. 상한이나 시간 예산에 걸리면 출력 맨 위의 `⚠ 아직 끝나지 않음` 줄이 다음 값을 알려 준다 |
| `out` | 결과 파일 절대 경로(`.tsv` 또는 `.jsonl`, 확장자로 형식을 정함). 주면 모든 항목의 행을 이 파일에 쓴다. `offset=0`이면 덮어쓰고, `offset>0`이면 이어 붙인다. 아래 "결과 파일" 참고 |
| `id_key` | 객체 항목(`jsonl`, `items`)에서 id로 쓸 키(예: `number`, `test_id`). 표와 결과 파일의 `id` 열에 들어간다 |
| `keep` | 답 id 목록. 주면 그 답과 uncertain·요청 실패 항목만 행으로 보이고, 나머지는 집계에만 남는다 |
| `excerpt_chars` | 파일 모드에서 행마다 붙일 앞부분 길이(기본 100자, 가린 뒤의 내용) |
| `items` | 문자열 또는 객체 배열. 최대 200개(`TORCHCAST_MAX_ITEMS`). 이미 손에 든 짧은 항목에만 쓴다 |
| `options` | `{id: 설명}` 권장. 배열도 된다. `noul`은 생략 가능 |
| `context` | 모든 항목에 공통으로 붙일 배경(선택). 문자열 항목이면 `[배경]…[항목]…`, 객체 항목이면 `{"context":…, "item":…}`로 보낸다 |
| `min_confidence` | 이보다 낮으면 `uncertain`. 기본 0.5(`TORCHCAST_MIN_CONFIDENCE`) |
| `verbose` | 참이면 줄마다 전체 확률을 붙인다 |

`classify` 출력(탭 구분). 파일 모드는 `i, line, answer, confidence, flags, excerpt` 열이고, `items` 모드는 `line`과 `excerpt`가 없다.

```
i	line	answer	confidence	flags	excerpt
319	320	incident	0.96		2026-11-11 10:05:19 ERROR [payments] upstream 503 after 199 retries
371	372	normal	0.31	uncertain	2026-11-11 10:06:11 WARN [db] connection pool 27% used
---
집계: 처리 600/600 | normal 525, watch 55, incident 20 | uncertain 2 | 요청 실패 0 | 44811ms
표시: keep=['incident']와 uncertain·요청 실패 22행, 나머지 578행은 집계에만 있음
파일 항목: grep 뒤 600개 중 0~599번 처리
```

- 요청 실패 행은 `answer` 자리에 `ERROR`, `excerpt` 앞 칸에 오류 메시지가 온다.
- 처리가 끝나지 않았으면(상한, 시간 예산, 연결 끊김) 표 위 맨 첫 줄에 `⚠`로 알리고, 같은 내용을 끝에도 한 번 더 적는다.
- `out` 없이 표시 행이 100개를 넘으면 100행까지만 보인다. 대신 전체 결과를 임시 디렉터리(`$TMPDIR/torchcast/classify-*.tsv`)에 TSV로 쓰고 그 경로를 알려 준다.
- 비밀값을 가린 곳이 있으면 개수를 알려 준다.

- 확신도는 `choice`·`score`에서는 서버의 `confidence`다. `noul`에는 서버가 확신도를 주지 않으므로 `|p - 0.5| × 2`로 계산한다.
- `noul` 답이 정확히 0.801이나 0.199이면 서버가 "확신 약함"을 경계값으로 바꿔 준 것이다. 확신도와 상관없이 `uncertain`으로 표시한다.
- `score`의 답은 기댓값을 반올림한 단계의 원래 이름이다. 기댓값은 `score=`로 함께 준다.

### 결과 파일(`out`)

항목이 수백 개를 넘거나 결과로 목록(이슈 번호, test id)을 만들어야 할 때 쓴다. 도구 출력을 Claude Code가 tool-results 파일로 돌리는 일이 없어지고, Claude는 awk·jq·python으로 답을 뽑으면 된다.

- 열(TSV 머리줄, JSONL 키): `i, line, id, answer, confidence, uncertain, score, error, excerpt`. 값이 없으면 TSV는 빈 칸, JSONL은 `null`이다. TSV의 `uncertain`은 `1`/`0`이다. `verbose=true`면 JSONL에 `probabilities`가 붙는다.
- `excerpt`는 비밀값을 가린 뒤의 앞부분(`excerpt_chars`)이다. 탭과 줄바꿈은 공백으로 바꾼다.
- 도구 출력에는 집계, 파일 경로, uncertain·요청 실패 행, 답마다 무작위 표본 3개(`flags=sample`, 고정 시드)만 온다.
- 경로 제한: 절대 경로만 받는다. MCP 서버는 `uv run --directory`로 플러그인 디렉터리에서 돌기 때문에, 상대 경로를 받으면 프로젝트가 아니라 플러그인 디렉터리를 기준으로 풀리게 된다. 확장자는 `.tsv`/`.jsonl`만 받는다. 디렉터리가 이미 있어야 하고, 입력 파일(`path`)과 같은 파일은 거절한다. 이미 있는 비어 있지 않은 파일은 첫 줄이 torchcast 결과 형식일 때만 덮어쓰거나 이어 붙인다. TSV는 머리줄이 같아야 하고, JSONL은 첫 줄에 위 열 키가 모두 있어야 한다. 그렇지 않으면 서버에 보내기 전에 `ERROR`로 거절한다. MCP 서버는 Claude Code 샌드박스 밖에서 쓰기 때문에 이 검사를 둔다. 그 밖의 위치 제한은 없어서 작업 디렉터리 안에도 쓸 수 있다.

```
i	line	id	answer	confidence	flags	excerpt
14	15	1014	bug	0.94	sample	{"number": 1014, "title": "다크모드에서 글자가 안 보여요"}
...
---
집계: 처리 40/40 | feature 16, bug 14, question 10 | uncertain 0 | 요청 실패 0 | 2640ms
전체 결과 40행을 /…/result.tsv에 TSV로 씀. 열: i, line, id, answer, confidence, uncertain, score, error, excerpt(uncertain은 1/0). 스크립트로 이 파일을 읽어 답을 만든다.
표시: uncertain·요청 실패와 답마다 표본 3개(flags=sample) 총 9행. 이것만 직접 확인하면 된다
```

### 결과를 어떻게 쓰게 하나

harness-test 2단계 시험 실행에서 Claude가 classify 결과를 버리고 같은 일을 다시 하는 것을 관찰했다(기록용). `test-triage` 과제에서 classify가 코드 결함 180건을 정확히 골랐는데도 정규식으로 다시 풀었다. 평가 과제의 성적이므로 도구 문구에는 넣지 않는다. 도구 문구에는 자체 라벨 표본(`measure/samples.json`) 수치만 적는다. 설명문이 결과를 "거친 1차 분류"라 부르며 직접 다시 확인하라고 했기 때문으로 본다. 0.3.0부터 서버 `instructions`와 `classify` 설명은 이렇게 지시한다. uncertain·요청 실패 항목과 답별 표본(합쳐 10~20개)만 직접 확인한다. 표본이 맞으면 나머지는 결과를 그대로 쓴다. 표본에서 틀린 것이 여럿 나올 때만 질문을 고쳐 다시 돌린다. 개인정보 경고는 바꾸지 않았다.

## 실패 처리

| 상황 | 동작 |
|---|---|
| 연결 거부, 연결 시간 초과(Meshnet 끊김) | 바로 멈추고 `⚠ torchcast에 연결할 수 없음`을 알린다. 그때까지 처리한 결과와 처리하지 못한 항목 번호를 돌려준다 |
| 요청 도중 연결이 끊김 | 한 번 다시 시도한다. 또 실패하면 위와 같이 처리한다 |
| 읽기 시간 초과(요청당 10초, `TORCHCAST_TIMEOUT`) | 그 항목에 오류를 남기고 계속한다. 3번 연속이면 연결 불가로 보고 멈춘다 |
| 422·400·500 | 항목별 `ERROR <코드> <메시지>`로 남기고 계속한다 |
| 503(GPU 메모리 부족) | 0.5초 뒤 한 번 다시 시도한다. 또 503이면 항목별 오류로 남긴다 |
| 시간 예산(호출당 240초, `TORCHCAST_MAX_SECONDS`) 초과 | 멈추고 그때까지 결과와 이어 할 `offset`을 출력 맨 위에 알려 준다 |
| 파일 모드 상한(호출당 5000개, `TORCHCAST_MAX_FILE_ITEMS`) 초과 | 앞 5000개만 처리하고 다음 `offset`을 출력 맨 위에 알려 준다. 항목당 약 50ms라 보통은 시간 예산(약 4,000개)에 먼저 걸린다 |
| `items` 상한 초과, 선택지 개수 오류, id 중복, 없는 파일, 정규식 오류, 50MB 넘는 파일, 잘못된 `out` | 서버에 보내지 않고 바로 `ERROR`를 돌려준다 |
| `out` 파일 쓰기 실패 | 맨 위에 `ERROR 결과 파일을 쓰지 못함`을 붙이고 표 출력을 그대로 돌려준다 |

긴 호출에서는 20개마다 MCP 진행률 알림을 보낸다. 시간 예산은 Claude Code의 MCP 도구 시간 제한(`MCP_TOOL_TIMEOUT`)보다 짧게 둔다.

환경 변수: `TORCHCAST_URL`(기본 `http://100.112.79.59:8011`), `TORCHCAST_TIMEOUT`(10), `TORCHCAST_CONNECT_TIMEOUT`(3), `TORCHCAST_MAX_ITEMS`(200), `TORCHCAST_MAX_FILE_ITEMS`(5000), `TORCHCAST_MAX_SECONDS`(240), `TORCHCAST_MIN_CONFIDENCE`(0.5).

## 설치

[hg-claude-kit](../../README.md) 마켓플레이스의 플러그인이다.

```bash
claude plugin install torchcast@hg-claude-kit --scope user
```

- MCP 서버는 `.mcp.json`이 `uv run --frozen --directory ${CLAUDE_PLUGIN_ROOT} torchcast-mcp`로 띄운다. venv는 `${CLAUDE_PLUGIN_DATA}/venv`에 만들어져 플러그인 업데이트 뒤에도 남는다.
- uv가 필요하다(`brew install uv`). 경로는 `/opt/homebrew/bin/uv`로 고정했다.
- 끄기: `claude plugin disable torchcast@hg-claude-kit`. 특정 프로젝트에서만 끄려면 그 프로젝트에서 `--scope local`(나만) 또는 `--scope project`(팀 공유)를 붙인다.

### 확인

1. `claude mcp list`에 `plugin:torchcast:torchcast ... ✔ Connected`가 보인다.
2. 새 세션에서 `/mcp`를 입력해 `plugin:torchcast:torchcast`의 도구 3개(`classify`, `ask`, `health`)를 본다.
3. "torchcast health 도구로 서버 상태 확인해 줘"라고 요청해 `"ok": true`를 본다.

### 개발

```bash
cd plugins/torchcast && uv run pytest -q
```

실측: `uv run python measure/run.py`(라벨 표본 26개).

## 사용 예

Claude에게 이렇게 요청한다.

- "`build.log`를 읽지 말고 torchcast classify에 경로로 넘겨서 ERROR·WARN 줄의 원인 종류를 나누고, `config` 범주와 uncertain만 직접 읽어 줘."
- "`gh issue list --limit 500 --json number,title > /tmp/issues.json`을 JSONL로 바꿔 classify로 `bug / feature / question`을 나누고 bug만 보여 줘."
- "pytest 출력을 파일로 저장하고, 실패 블록마다 '환경·인프라 문제인가?'를 `noul`로 물어서 아닌 것부터 고쳐 줘."
- "`issues.jsonl` 2,500개를 classify로 `bug / feature / question`으로 나누고 `out`에 TSV로 받아서, bug 번호 목록을 awk로 뽑아 줘."

도구 호출 예:

```json
{"path": "/tmp/app.log", "grep": "ERROR|WARN",
 "question": "이 로그 줄은 즉시 조치가 필요한 장애인가?",
 "type": "choice",
 "options": {"incident": "요청·작업이 실제로 실패함", "watch": "주의할 징후", "normal": "정상"},
 "keep": ["incident"]}
```

```json
{"path": "/work/issues.jsonl", "split": "jsonl", "id_key": "number",
 "question": "이 이슈의 종류는?", "type": "choice",
 "options": {"bug": "기존 기능이 잘못 동작함", "feature": "새 기능 요청", "question": "사용법 질문"},
 "out": "/work/issues-classified.tsv"}
```

`uncertain` 항목과 답별 표본만 직접 확인하고, 표본이 맞으면 나머지는 결과를 그대로 쓴다. 확신 있는 오답도 있으므로(아래 측정 참고) 표본 확인은 건너뛰지 않는다.

## 측정 결과 (2026-11-11, 실서버)

`measure/samples.json`에 라벨을 단 표본 26개(직접 작성)를 넣고 `uv run python measure/run.py`로 쟀다. `classify`와 같은 코드 경로를 쓴다. 같은 표본을 두 번 돌렸고 답은 두 번 모두 같았다.

| 과제 | 유형 | 정답 | 비고 |
|---|---|---|---|
| 로그 줄 성격(error/warning/info) | choice 3 | 9/10 | `retrying ... after 503`(warning)을 error로 답함, 확신도 0.70이라 uncertain으로 걸러지지 않음 |
| 테스트 실패가 환경 문제인가 | noul | 8/8 | 1건(e2e TimeoutError)은 0.801로 와서 uncertain, 답은 맞음 |
| 리뷰 지적 종류(bug/style/question) | choice 3 | 8/8 | |
| **합계** | | **25/26 (96%)** | uncertain 1건(오답 0), 확신 있는 오답 1건 |

지연:

| 측정 | 값 |
|---|---|
| 측정 | 서버 HTTP/1.0 (11-11 오전) | 서버 HTTP/1.1 keep-alive (11-11 오후) |
|---|---|---|
| 서버 응답만(`/v1/systemone`, noul 1문항, 20회) | 중앙값 41~48ms, p90 124ms | 중앙값 32~39ms, p90 100ms |
| `classify` 항목당(연결 포함) | 53~159ms, 8~10개 묶음 0.4~1.6초 | 41~53ms, 8~10개 묶음 0.34~0.51초 |

- 처음에는 서버가 HTTP/1.0으로 답해 항목마다 새 TCP 연결이 열렸다. 서버가 HTTP/1.1 keep-alive(유휴 30초 뒤 닫음)로 바뀐 뒤 `classify`는 한 호출 안에서 연결 하나를 재사용한다. 클라이언트 코드는 바꾸지 않았다. 200개면 대략 10초다.
- 두 번 모두 정답은 같았다(25/26).
- 표본이 작고 직접 만든 깔끔한 예문이라, 실제 로그나 이슈에서는 정확도가 더 낮을 수 있다. 확신 있는 오답이 있으므로 표본 확인은 건너뛰지 않는다.
- `measure/results-*.json`(원시 결과)은 gitignore한다.

### 파일 모드 (합성 로그 600줄, stdio로 MCP 서버를 띄워 측정)

INFO·DEBUG 523줄, WARN 57줄, ERROR 20줄인 합성 로그(36KB)를 `path`와 `keep=["incident"]`로 넘겼다.

| 측정 | 값 |
|---|---|
| 처리 시간 | 44.8초(항목당 75ms, HTTP/1.0) → 29.7초(항목당 49ms, keep-alive). 진행률 알림 29회 |
| Claude가 받은 출력 | 22행, 2,515자(원본의 7%) |
| ERROR 줄 | 20줄 모두 incident로 뽑힘(놓친 것 0, 잘못 뽑힌 것 0) |
| uncertain | 2줄(둘 다 WARN) |

같은 로그에 `grep: "ERROR|WARN"`을 쓰면 보내는 항목이 77개로 줄어 8.4초(항목당 109ms)에 끝났고, keep-alive 뒤에는 3.8초(항목당 49ms)였다. 결과는 같았다(incident 20, WARN 중 2줄이 normal로 분류). 0.3.0 확인(합성 이슈 40개, jsonl + `id_key` + `out`): 40/40 정답, 2.6초(항목당 66ms), 도구 출력은 표본 9행이었다. 이 측정은 도구 출력 크기만 본 것이다. 이 도구가 있을 때 실제 과제에서 Claude의 총 토큰과 시간이 줄어드는지는 아직 baseline과 비교하지 않았다.
