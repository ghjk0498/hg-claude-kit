# away

자리를 오래 비우기 전에 현재 세션의 컨텍스트 길이와 프롬프트 캐시 비용을 재고, 그대로 둘지 · 떠나기 전에 `/compact` 할지 · 새 세션으로 핸드오프할지 정하는 스킬이다. 판정과 무관하게 복귀 메모 3줄을 남긴다.

> **전송:** 없음. `~/.claude/projects/`의 로컬 transcript만 읽는다.

## 설치

```bash
claude plugin install away@hg-claude-kit --scope user
```

스킬 이름은 `away:away`다. "자리 비울게", "퇴근", "회의 다녀올게"로도 불린다.

## 구성

- `skills/away/SKILL.md`: 측정 → 묻기 → 판정 → 보존 → 실행 → 복귀 메모 순서
- `skills/away/away_check.py`: 마지막 턴의 usage로 컨텍스트, 바닥값(압축해도 남는 부분), 캐시 TTL, 식은 복귀 비용, 압축 비용, 손익분기를 계산한다. 의존성 없음(python3 표준 라이브러리)

## 다시 잴 값

`away_check.py` 상단에 있다.

- `PRICES`: 2026-10-06 단가표. 목록에 없는 모델은 Opus 5.5 단가로 계산한다(`(fallback)` 표시). 지금 Fable 5.2가 목록에 없다
- `DEFAULT_BASELINE` · `DEFAULT_SUMMARY` · `COMPACT_OUTPUT_TOKENS`: 실측 바닥값이 없을 때만 쓰는 추정값

## 측정

2026-11-14에 transcript를 훑어 실제 사용 기록을 모았다(개발 중이던 2026-10-28 실행 제외).

- 2026-11-02 ~ 11-14 실사용 10회(세션 7개). 판정: 압축 5 · 그대로(TTL 미만) 2 · 그 밖 3
- 직접 압축한 3회에서 압축 직후 첫 턴의 실제 입력은 88~97K로, 스크립트의 `after compact` 추정(88~101K)과 맞았다(나머지 압축 2회는 transcript에서 첫 턴을 짚지 못했다). 첫 턴에서 약 45K는 다른 세션 덕에 캐시 읽기였다(`shared prefix` 줄이 말하는 경우)
- 압축 판정 때 스크립트가 낸 «식은 복귀 − 압축» 차이는 회당 $0.48~1.64였다. 실제 아낀 금액은 재지 않았다
