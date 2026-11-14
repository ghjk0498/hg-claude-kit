# context-meter

컨텍스트가 away 손익분기(125K)를 넘으면 Claude Code 프롬프트 바로 위에 한 줄 띠를 띄우는 mod다. 떠날 때 보고 바로 판단하라는 용도다.

> **전송:** 없음. `$.session.usage()`로 마지막 응답의 입력 토큰만 읽는다.

```
컨텍스트 312K · 손익분기 125K 넘음 — 1시간 넘게 비울 때: 이어갈 일이면 /compact, 다른 일이면 새 세션
```

125K 아래면 아무것도 띄우지 않는다.

## 설치

```bash
claude plugin install context-meter@hg-claude-kit --scope user
```

Desktop Code 탭에서도 그려진다(2026-11-14 확인). `settings.json`의 `statusLine`은 Desktop에서 그려지지 않아 이 방식을 쓴다.

## 규칙

- 1시간 안에 돌아오면 아무것도 안 한다. 캐시가 따뜻하다
- 1시간 넘게 비우고 같은 일을 이어가면 떠나기 전에 `/compact`(문구 없이도 된다)
- 1시간 넘게 비우고 다른 일을 하면 그대로 두고 새 세션을 연다

## 손익분기를 125K 하나로 두는 이유

away 공식 `(압축 출력 × 출력 단가 + 압축 뒤 크기 × 쓰기 단가) / (쓰기 단가 − 읽기 단가)`에 단가를 넣으면 Opus 5.5 약 118~125K, Sonnet 5.5·Haiku 5.5 약 121K, Fable 5.1 약 117K로 거의 같다. 단가가 양쪽에서 상쇄되고 출력/입력 비율(5배)이 모델마다 같아서다. 손익분기를 움직이는 것은 압축해도 남는 바닥값(프로젝트마다 70~81K)이고, 그래도 110~129K 안이다. Fable 5.2는 단가가 없어 계산하지 않았다.

## 테스트

```bash
claude plugin test plugins/context-meter
```

312K에서 terminal·desktop 양쪽에 경고가 그려지고, 90K에서는 띠가 비는지 본다.
