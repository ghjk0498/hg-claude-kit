"""torchcast 판단 API를 감싼 MCP 서버 (stdio)."""

from __future__ import annotations

import logging
from typing import Any, Literal

from mcp.server.mcpserver import Context, MCPServer

from . import core, prep

PRIVACY = (
    "주의: 항목 내용은 NordVPN Meshnet의 다른 PC(torchcast 서버)로 평문 HTTP로 전송된다. "
    "비밀값(API key, 토큰, 비밀번호, .env 내용)이나 고객 개인정보가 든 항목·파일은 보내지 않는다. "
    "흔한 키·토큰 형식은 보내기 전에 자동으로 [MASKED] 처리하지만 완벽하지 않으므로 믿고 보내지 말 것."
)

USE_RESULT = (
    "결과 쓰는 법: uncertain·요청 실패 항목과 답마다 몇 개 표본(합쳐 10~20개)만 직접 확인하고, "
    "표본이 맞으면 나머지는 결과를 그대로 답으로 쓴다. 같은 분류를 정규식·키워드 규칙이나 직접 읽기로 처음부터 "
    "다시 하지 않는다(그러면 classify에 쓴 시간만 버린다). 표본에서 틀린 것이 여럿 나올 때만 질문·선택지 설명을 "
    "고쳐 다시 돌리거나 그 범주를 직접 본다. "
    "출력 맨 위에 '아직 끝나지 않음'이 있으면 알려 준 offset으로 다시 호출해 끝까지 처리한다."
)

WHEN = (
    "언제 쓰나: 의미를 읽어야 갈리는 판단이 항목 수십~수천 개에 필요할 때(이슈·PR 분류, 테스트 실패가 코드 결함인지 "
    "환경 문제인지, 로그 줄이 장애인지, 리뷰 지적 종류). 키워드나 예외 이름만으로는 안 갈리는 일에 맞다. "
    "정확한 개수 세기·합계·정해진 문자열이나 형식(상태 코드, 레벨 이름)으로 갈리는 일은 grep/awk가 더 빠르고 정확하다. "
    "항목이 몇 개뿐이면 직접 읽는다."
)

mcp = MCPServer(
    "torchcast",
    instructions=(
        "torchcast는 작은 판단 전용 모델(4B)이다. 자체 라벨 표본(로그·테스트 실패·리뷰 지적 26개)에서 96%를 맞혔다. " + WHEN + " 대량이면 파일 경로(path)로 넘기고 out으로 결과 파일을 받아 스크립트로 쓴다. "
        + USE_RESULT + " " + PRIVACY
    ),
)


@mcp.tool(
    description=(
        "대량 항목을 정해진 선택지로 분류한다. " + WHEN + "\n"
        + USE_RESULT + "\n"
        "항목 주는 법(둘 중 하나):\n"
        "- path: 파일 경로(절대 경로). 서버가 파일을 직접 읽으므로 내용을 컨텍스트에 읽거나 인자로 옮겨 쓰지 않는다. "
        "대량 항목은 반드시 이 방식으로 준다(명령 출력이면 먼저 파일로 저장). "
        "split=lines(한 줄=한 항목, 기본)/jsonl(줄마다 JSON)/blank(빈 줄로 나뉜 블록). "
        "grep(정규식)으로 보낼 줄을 먼저 거를 수 있다. 항목당 약 50ms(2,500개 ≈ 2분). "
        "한 번에 최대 5000개, 시간 예산 240초. 넘으면 멈추고 맨 위에 이어 할 offset을 알려 준다.\n"
        "- items: 문자열 또는 객체 배열(최대 200개). 이미 손에 든 짧은 항목에만 쓴다.\n"
        "질문: question(짧고 분명하게), type(choice=선택지 2~26개 / score=단계 2~10개, 낮은 단계부터 / noul=예·아니오), "
        "options(설명을 붙인 {id: 설명} 권장, noul은 생략), context(모든 항목에 공통으로 붙일 배경), "
        "min_confidence(이보다 낮으면 uncertain, 기본 0.5).\n"
        "출력 받는 법:\n"
        "- out: 결과 파일 절대 경로(.tsv 또는 .jsonl, 작업 디렉터리 안도 됨). 주면 모든 항목의 행"
        "(i, line, id, answer, confidence, uncertain, score, error, excerpt)을 그 파일에 쓰고, 도구 출력에는 집계와 "
        "uncertain·요청 실패·답별 표본 행만 온다. 이미 있는 파일은 torchcast가 쓴 결과 파일일 때만 덮어쓰거나 이어 붙인다. 항목이 수백 개를 넘거나 결과로 목록(번호, id)을 만들어야 하면 out을 쓰고 "
        "awk·jq·python으로 그 파일에서 답을 뽑는다. offset>0이면 같은 파일에 이어 붙인다.\n"
        "- id_key: 객체 항목(jsonl, items)에서 id로 쓸 키(예: number, test_id). 표와 out 파일의 id 열에 들어간다.\n"
        "- out이 없으면 탭 구분 표와 집계. 파일 모드는 원래 줄 번호와 앞부분(excerpt_chars, 기본 100자)을 붙인다. "
        "keep=[답 id...]을 주면 그 답과 uncertain·요청 실패 항목만 행으로 보인다. 표시 행이 100개를 넘으면 전체를 임시 TSV로 쓰고 경로를 알려 준다.\n"
        "noul 답은 yes/no. verbose=true면 전체 확률.\n" + PRIVACY
    ),
)
async def classify(
    question: str,
    type: Literal["choice", "score", "noul"],
    items: list[str | dict[str, Any]] | None = None,
    options: dict[str, str] | list[str] | None = None,
    context: str | None = None,
    min_confidence: float | None = None,
    verbose: bool = False,
    path: str | None = None,
    split: Literal["lines", "jsonl", "blank"] = "lines",
    grep: str | None = None,
    offset: int = 0,
    keep: list[str] | None = None,
    excerpt_chars: int = 100,
    out: str | None = None,
    id_key: str | None = None,
    ctx: Context | None = None,
) -> str:
    cfg = core.Config.from_env()
    if not question:
        return "ERROR question이 필요함"
    if err := core.validate_question(type, options):
        return f"ERROR {err}"
    if (items is None) == (path is None):
        return "ERROR items와 path 중 정확히 하나를 줄 것"
    out_target = None
    if out is not None:
        try:
            out_target = core.check_out_path(out, path)
        except ValueError as ex:
            return f"ERROR {ex}"

    selected = None
    if path is not None:
        try:
            all_entries = prep.read_entries(path, split, grep)
        except prep.PrepError as ex:
            return f"ERROR {ex}"
        selected = len(all_entries)
        if not all_entries:
            return f"ERROR 보낼 항목이 없음(grep={grep!r}에 맞는 줄이 없거나 빈 파일)"
        if offset < 0 or offset >= selected:
            return f"ERROR offset={offset}이 범위 밖(항목 {selected}개)"
        entries = all_entries[offset : offset + cfg.max_file_items]
    else:
        if not items:
            return "ERROR items가 비어 있음"
        if len(items) > cfg.max_items:
            return (
                f"ERROR 항목 {len(items)}개는 상한 {cfg.max_items}개를 넘음. "
                "파일로 저장해 path로 주거나 나눠서 호출할 것."
            )
        entries = [prep.Entry(i=i, value=v) for i, v in enumerate(items)]

    progress = None
    if ctx is not None:
        async def progress(done: int, total: int) -> None:
            try:
                await ctx.report_progress(done, total)
            except Exception:
                pass

    run = await core.run_classify(
        cfg, entries, question, type, options, context, min_confidence,
        file_mode=path is not None, excerpt_chars=excerpt_chars, progress=progress, id_key=id_key,
    )
    run.selected = selected
    try:
        return core.format_classify(run, verbose, keep, out=out_target)
    except OSError as ex:
        return f"ERROR 결과 파일을 쓰지 못함({type(ex).__name__}: {ex})\n" + core.format_classify(run, verbose, keep)


@mcp.tool(
    description=(
        "torchcast /v1/systemone 원형 호출. 상황(state) 하나에 질문 여러 개를 한 번에 묻는다. "
        "항목이 여럿이면 classify를 쓴다. "
        "questions 예: {\"team\": {\"type\": \"choice\", \"instructions\": \"담당 팀은?\", "
        "\"criteria\": {\"billing\": \"결제, 환불\", \"technical\": \"버그, 로그인\"}}, "
        "\"urgent\": {\"type\": \"noul\", \"instructions\": \"긴급한가?\"}}. "
        "score는 낮은 단계부터 적고, 응답의 score는 0부터 매긴 단계 기댓값이다(legend 참고). "
        "noul 값은 '예'일 확률이며 정확히 0.801/0.199면 모델이 확신하지 못한 것이라 uncertain으로 표시된다. "
        "images는 base64 또는 data URI 배열(선택).\n" + PRIVACY
    ),
)
async def ask(
    state: str | dict[str, Any] | list[Any],
    questions: dict[str, dict[str, Any]],
    images: list[str] | None = None,
) -> str:
    if not questions:
        return "ERROR questions가 비어 있음"
    return await core.run_ask(core.Config.from_env(), state, questions, images)


@mcp.tool(description="torchcast 서버 상태와 모델 이름, 왕복 지연을 확인한다. classify가 연결 실패를 알릴 때 먼저 써 본다.")
async def health() -> str:
    return await core.run_health(core.Config.from_env())


def main() -> None:
    logging.getLogger("httpx").setLevel(logging.WARNING)  # 요청마다 찍히는 INFO 로그를 끈다
    mcp.run()


if __name__ == "__main__":
    main()
