# hg-claude-kit

직접 만든 Claude Code 도구(MCP 서버, 훅, 스킬 등)를 모은 개인 플러그인 마켓플레이스다. 플러그인 하나가 켜고 끄는 단위다. 쓸모는 평판이 아니라 측정으로 정하고, 새 모델이 나오면 다시 재서 필요 없어진 것은 끈다. 지금 무엇이 있고 어떤 상태인지는 [CATALOG.md](CATALOG.md)에 있다.

## 처음 한 번

```bash
claude plugin marketplace add ghjk0498/hg-claude-kit
```

이 저장소를 clone해 고치면서 쓰려면 clone한 폴더의 경로를 넘긴다. 그러면 플러그인을 그 폴더에서 바로 읽는다.

## 플러그인 다루기

| 하고 싶은 것 | 명령 |
|---|---|
| 설치 | `claude plugin install <이름>@hg-claude-kit --scope user` |
| 끄기 / 켜기 | `claude plugin disable <이름>@hg-claude-kit` / `claude plugin enable <이름>@hg-claude-kit` |
| 한 프로젝트에서만 끄기 | 그 프로젝트에서 `--scope local`(나만) 또는 `--scope project`(팀과 공유)를 붙여 disable |
| 코드를 고친 뒤 반영 | `claude plugin marketplace update hg-claude-kit` 후 새 세션 |
| 토큰 비용 보기 | `claude plugin details <이름>@hg-claude-kit` |
| 개발 중 한 세션에만 띄우기 | `claude --plugin-dir plugins/<이름>` |

변경은 새 세션부터 적용된다.

## 새 도구 추가

1. `plugins/<이름>/`에 `.claude-plugin/plugin.json`을 두고, 필요한 것을 넣는다: MCP면 `.mcp.json`, 훅이면 `hooks/hooks.json`, 스킬이면 `skills/`, 서브에이전트면 `agents/`.
2. `.claude-plugin/marketplace.json`의 `plugins`에 한 항목을 넣는다.
3. 플러그인 폴더 안에서 테스트를 돌리고, 측정해서 플러그인 README에 적는다.
4. `claude plugin validate .`로 형식을 확인한다.
5. `claude plugin marketplace update hg-claude-kit` 후 설치한다.
6. CATALOG.md에 한 줄 추가한다.

### 지킬 것

- **플러그인은 자기 폴더 밖을 참조하지 않는다.** 설치하면 `~/.claude/plugins/cache/`로 복사될 수 있다. 공용 코드가 필요하면 각 플러그인에 넣고, 같아야 하는 부분은 테스트로 묶는다(`torchcast-stop-check`의 비밀값 규칙 테스트가 예).
- **남겨야 할 데이터는 `${CLAUDE_PLUGIN_DATA}`에 둔다.** `${CLAUDE_PLUGIN_ROOT}`는 업데이트 때 바뀐다. torchcast의 venv와 Stop 훅의 결정 기록이 여기에 있다.
- **켜고 끄는 단위로 나눈다.** 따로 끄고 싶을 수 있는 기능은 다른 플러그인으로 둔다(torchcast MCP와 Stop 훅이 예).
- **외부로 보내는 것은 플러그인 설명과 README 맨 위에 적는다.**
- **비밀값을 넣지 않는다.** 커밋 전에 `sk-ant-` 같은 패턴을 검사한다.

## 은퇴

1. `claude plugin disable <이름>@hg-claude-kit` 또는 `claude plugin uninstall <이름>@hg-claude-kit`
2. CATALOG.md의 상태를 `retired`로 바꾸고 이유(어느 모델에서 무엇을 재서 효과가 없었는지)를 적는다.
3. 다시 쓸 일이 없으면 `marketplace.json`에서 빼고 폴더를 지운다. 기록은 git에 남는다.

## harness-test와의 관계

harness-test는 플러그인을 `--plugin-dir`로 그 실행에만 넣어 baseline과 비교한다. 이 저장소의 플러그인 폴더를 그대로 harness로 등록하면, 쓰는 것과 재는 것이 같은 코드가 된다. harness-test 러너는 `--setting-sources project,local`로 돌아서 여기서 켜 둔 플러그인이 실험에 섞이지 않는다.
