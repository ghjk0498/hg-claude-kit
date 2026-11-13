"""torchcast 호출과 결과 정리. MCP와 무관한 순수 로직이라 테스트에서 바로 부른다."""

from __future__ import annotations

import asyncio
import json
import os
import random
import tempfile
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

import httpx

from .prep import MASK, Entry, excerpt, mask_value

UNCERTAIN_NOUL = (0.801, 0.199)
UNREACHABLE = "torchcast에 연결할 수 없음"
OPTION_LIMITS = {"choice": (2, 26), "score": (2, 10)}
QUESTION_KEY = "q"


@dataclass
class Config:
    url: str = "http://100.112.79.59:8011"
    timeout: float = 10.0  # 요청 하나의 시간 제한(초)
    connect_timeout: float = 3.0
    max_items: int = 200
    max_file_items: int = 5000  # 항목당 약 50ms라 시간 예산 안에 4,000개 남짓 끝난다
    max_seconds: float = 240.0  # classify 한 번의 시간 예산(초)
    min_confidence: float = 0.5
    max_consecutive_timeouts: int = 3
    retry_503_delay: float = 0.5

    @classmethod
    def from_env(cls) -> "Config":
        e = os.environ
        return cls(
            url=e.get("TORCHCAST_URL", cls.url).rstrip("/"),
            timeout=float(e.get("TORCHCAST_TIMEOUT", cls.timeout)),
            connect_timeout=float(e.get("TORCHCAST_CONNECT_TIMEOUT", cls.connect_timeout)),
            max_items=int(e.get("TORCHCAST_MAX_ITEMS", cls.max_items)),
            max_file_items=int(e.get("TORCHCAST_MAX_FILE_ITEMS", cls.max_file_items)),
            max_seconds=float(e.get("TORCHCAST_MAX_SECONDS", cls.max_seconds)),
            min_confidence=float(e.get("TORCHCAST_MIN_CONFIDENCE", cls.min_confidence)),
        )

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.url,
            timeout=httpx.Timeout(self.timeout, connect=self.connect_timeout),
        )


class Unreachable(Exception):
    """서버가 꺼져 있거나 Meshnet이 끊긴 경우."""


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(f"{status} {message}")
        self.status = status
        self.message = message


def is_uncertain_noul(p: float) -> bool:
    return any(abs(p - v) < 1e-9 for v in UNCERTAIN_NOUL)


async def post_systemone(client: httpx.AsyncClient, cfg: Config, body: dict) -> dict:
    """요청 하나. 연결 실패는 Unreachable, HTTP 오류는 ApiError, 읽기 시간 초과는 httpx.ReadTimeout."""
    for attempt in range(2):
        try:
            r = await client.post("/v1/systemone", json=body)
        except (httpx.ConnectError, httpx.ConnectTimeout) as ex:
            raise Unreachable(f"{type(ex).__name__}: {ex}") from ex
        except (httpx.ReadError, httpx.WriteError, httpx.RemoteProtocolError) as ex:
            # 요청 중 연결이 끊김. 한 번 다시 시도하고, 그래도 끊기면 연결 불가로 본다.
            if attempt == 0:
                await asyncio.sleep(0.2)
                continue
            raise Unreachable(f"연결이 끊김: {type(ex).__name__}") from ex
        if r.status_code == 503 and attempt == 0:
            await asyncio.sleep(cfg.retry_503_delay)
            continue
        break
    if r.status_code != 200:
        try:
            msg = r.json().get("error") or r.text
        except ValueError:
            msg = r.text
        raise ApiError(r.status_code, str(msg)[:300])
    return r.json()


def validate_question(qtype: str, options: Any) -> str | None:
    if qtype not in ("choice", "score", "noul"):
        return f"type은 choice, score, noul 중 하나여야 함: {qtype!r}"
    if qtype == "noul":
        return None
    if not options:
        return f"{qtype}에는 options가 필요함"
    ids = list(options.keys()) if isinstance(options, dict) else list(options)
    lo, hi = OPTION_LIMITS[qtype]
    if not lo <= len(ids) <= hi:
        return f"{qtype}의 선택지는 {lo}~{hi}개여야 함 (지금 {len(ids)}개)"
    if len(set(map(str, ids))) != len(ids):
        return "선택지 id가 겹침"
    for i in ids:
        s = str(i)
        if "\n" in s or len(s) > 200:
            return f"선택지 id는 한 줄, 200자 이하여야 함: {s[:40]!r}"
    return None


def interpret(answer: dict, min_conf: float) -> dict:
    """서버 답 하나를 {answer, confidence, uncertain, probabilities}로 줄인다."""
    t = answer.get("type")
    if t == "noul" or "noul" in answer:
        p = float(answer["noul"])
        weak = is_uncertain_noul(p)
        conf = abs(p - 0.5) * 2
        return {
            "answer": "yes" if p >= 0.5 else "no",
            "confidence": round(conf, 3),
            "uncertain": weak or conf < min_conf,
            "probabilities": {"yes": p},
        }
    if t == "score" or "score" in answer:
        score = float(answer["score"])
        legend = answer.get("legend", {})
        idx = str(int(round(score)))
        conf = float(answer.get("confidence", 0.0))
        return {
            "answer": legend.get(idx, idx),
            "score": round(score, 2),
            "confidence": round(conf, 3),
            "uncertain": conf < min_conf,
            "probabilities": answer.get("probabilities"),
        }
    conf = float(answer.get("confidence", 0.0))
    return {
        "answer": answer.get("choice"),
        "confidence": round(conf, 3),
        "uncertain": conf < min_conf,
        "probabilities": answer.get("probabilities"),
    }


def build_state(item: Any, context: str | None) -> Any:
    if not context:
        return item
    if isinstance(item, str):
        return f"[배경]\n{context}\n\n[항목]\n{item}"
    return {"context": context, "item": item}


@dataclass
class ClassifyRun:
    results: list[dict] = field(default_factory=list)  # {i, line?, answer, ...} 또는 {i, line?, error}
    unreachable: str | None = None
    budget_hit: bool = False
    total: int = 0  # 이번 호출에서 처리하려던 항목 수
    selected: int | None = None  # 파일 모드: grep 뒤 전체 항목 수
    offset: int = 0
    file_mode: bool = False
    masked: int = 0
    elapsed_ms: float = 0.0
    excerpts: dict[int, str] = field(default_factory=dict)
    ids: dict[int, str] = field(default_factory=dict)  # id_key로 뽑은 항목 id


ProgressFn = Callable[[int, int], Awaitable[None]]


async def run_classify(
    cfg: Config,
    entries: list[Entry],
    question: str,
    qtype: str,
    options: Any = None,
    context: str | None = None,
    min_confidence: float | None = None,
    *,
    file_mode: bool = False,
    excerpt_chars: int = 100,
    max_seconds: float | None = None,
    progress: ProgressFn | None = None,
    id_key: str | None = None,
) -> ClassifyRun:
    min_conf = cfg.min_confidence if min_confidence is None else min_confidence
    budget = cfg.max_seconds if max_seconds is None else max_seconds
    q: dict[str, Any] = {"type": qtype, "instructions": question}
    if options:
        q["criteria"] = options
    run = ClassifyRun(total=len(entries), file_mode=file_mode, offset=entries[0].i if entries else 0)
    t0 = time.perf_counter()
    consecutive_timeouts = 0

    def add(e: Entry, **r):
        if e.line is not None:
            r["line"] = e.line
        run.results.append({"i": e.i, **r})

    async with cfg.client() as client:
        for k, e in enumerate(entries):
            if budget and time.perf_counter() - t0 > budget:
                run.budget_hit = True
                break
            if progress and k and k % 20 == 0:
                await progress(k, len(entries))
            value, n_masked = mask_value(e.value)
            run.masked += n_masked
            run.excerpts[e.i] = excerpt(value, excerpt_chars)
            if id_key and isinstance(value, dict) and value.get(id_key) is not None:
                run.ids[e.i] = _cell(value[id_key])
            body = {"state": build_state(value, context), "questions": {QUESTION_KEY: q}}
            try:
                resp = await post_systemone(client, cfg, body)
            except Unreachable as ex:
                run.unreachable = str(ex)
                break
            except httpx.TimeoutException:
                consecutive_timeouts += 1
                add(e, error=f"시간 초과({cfg.timeout:g}s)")
                if consecutive_timeouts >= cfg.max_consecutive_timeouts:
                    run.unreachable = f"연속 {consecutive_timeouts}회 시간 초과"
                    break
                continue
            except ApiError as ex:
                consecutive_timeouts = 0
                add(e, error=f"{ex.status} {ex.message}")
                continue
            except (httpx.HTTPError, ValueError) as ex:
                consecutive_timeouts = 0
                add(e, error=f"{type(ex).__name__}: {ex}"[:300])
                continue
            consecutive_timeouts = 0
            ans = (resp.get("answers") or {}).get(QUESTION_KEY)
            if not ans:
                add(e, error="응답에 answers가 없음")
                continue
            add(e, **interpret(ans, min_conf))
    run.elapsed_ms = (time.perf_counter() - t0) * 1000
    return run


def _fmt_conf(c: float) -> str:
    return f"{c:.2f}"


def _cell(v: Any) -> str:
    """TSV 칸 하나: 탭·줄바꿈을 공백으로."""
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    return " ".join(s.split())


def _shown(r: dict, keep: set[str] | None) -> bool:
    if keep is None or "error" in r:
        return True
    return r["uncertain"] or str(r["answer"]) in keep


OUT_COLUMNS = ["i", "line", "id", "answer", "confidence", "uncertain", "score", "error", "excerpt"]
OUT_FORMATS = {".tsv": "tsv", ".jsonl": "jsonl"}
DISPLAY_ROWS = 100


def check_out_path(out: str, src: str | None = None) -> tuple[Path, str]:
    """out 경로를 검사해 (경로, 형식)을 돌려준다. 문제가 있으면 ValueError(메시지)."""
    p = Path(out).expanduser()
    if not p.is_absolute():
        raise ValueError(f"out은 절대 경로여야 함(MCP 서버의 작업 디렉터리는 프로젝트가 아님): {out}")
    fmt = OUT_FORMATS.get(p.suffix.lower())
    if fmt is None:
        raise ValueError(f"out 확장자는 .tsv 또는 .jsonl이어야 함: {out}")
    if not p.parent.is_dir():
        raise ValueError(f"out의 디렉터리가 없음: {p.parent}")
    if p.exists() and not p.is_file():
        raise ValueError(f"out이 파일이 아님: {out}")
    if src is not None and p.exists() and p.resolve() == Path(src).expanduser().resolve():
        raise ValueError("out이 입력 파일(path)과 같음")
    if p.exists() and p.stat().st_size > 0 and not _is_our_output(p, fmt):
        # MCP 서버는 Claude Code 샌드박스 밖에서 쓰므로, 남의 파일을 덮어쓰지 않게 막는다.
        raise ValueError(f"out에 이미 torchcast 결과가 아닌 파일이 있어 덮어쓰지 않음: {out}. 새 경로를 줄 것")
    return p, fmt


def _is_our_output(p: Path, fmt: str) -> bool:
    """이전 classify가 쓴 결과 파일인지(첫 줄로 판단)."""
    try:
        with p.open(encoding="utf-8") as f:
            first = f.readline().rstrip("\n")
    except (OSError, UnicodeDecodeError):
        return False
    if fmt == "tsv":
        return first == "\t".join(OUT_COLUMNS)
    try:
        row = json.loads(first)
    except ValueError:
        return False
    return isinstance(row, dict) and set(OUT_COLUMNS) <= set(row)


def result_rows(run: ClassifyRun, verbose: bool = False) -> list[dict]:
    """모든 결과를 스크립트에서 쓰기 좋은 행으로. 열은 OUT_COLUMNS."""
    rows = []
    for r in run.results:
        row: dict[str, Any] = {
            "i": r["i"], "line": r.get("line"), "id": run.ids.get(r["i"]),
            "answer": r.get("answer"), "confidence": r.get("confidence"),
            "uncertain": r.get("uncertain") if "error" not in r else None,
            "score": r.get("score"), "error": r.get("error"),
            "excerpt": run.excerpts.get(r["i"], ""),
        }
        if verbose and r.get("probabilities") is not None:
            row["probabilities"] = r["probabilities"]
        rows.append(row)
    return rows


def write_rows(run: ClassifyRun, path: Path, fmt: str, append: bool = False, verbose: bool = False) -> int:
    """결과 전부를 파일로 쓴다. append면 이어 붙인다(TSV 머리줄은 새 파일에만)."""
    rows = result_rows(run, verbose)
    new_file = not (append and path.exists() and path.stat().st_size > 0)
    with path.open("w" if new_file else "a", encoding="utf-8") as f:
        if fmt == "jsonl":
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        else:
            if new_file:
                f.write("\t".join(OUT_COLUMNS) + "\n")
            for row in rows:
                cells = []
                for c in OUT_COLUMNS:
                    v = row[c]
                    if v is None:
                        cells.append("")
                    elif c == "uncertain":
                        cells.append("1" if v else "0")
                    elif c == "confidence":
                        cells.append(_fmt_conf(v))
                    else:
                        cells.append(_cell(v))
                f.write("\t".join(cells) + "\n")
    return len(rows)


def spill_path() -> Path:
    d = Path(tempfile.gettempdir()) / "torchcast"
    d.mkdir(exist_ok=True)
    return d / f"classify-{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}-{random.randrange(10**6):06d}.tsv"


def _sample(run: ClassifyRun, per_answer: int) -> set[int]:
    """확인용 표본: uncertain이 아닌 결과에서 답마다 per_answer개(고정 시드)."""
    by: dict[str, list[int]] = {}
    for r in run.results:
        if "error" not in r and not r["uncertain"]:
            by.setdefault(str(r["answer"]), []).append(r["i"])
    rng = random.Random(0)
    out: set[int] = set()
    for ids in by.values():
        out.update(rng.sample(ids, min(per_answer, len(ids))))
    return out


def format_classify(
    run: ClassifyRun,
    verbose: bool = False,
    keep: list[str] | None = None,
    max_rows: int = DISPLAY_ROWS,
    out: tuple[Path, str] | None = None,
    sample_per_answer: int = 3,
) -> str:
    """사람·Claude가 읽는 결과. out이 있으면 전체 행은 파일에 쓰고 여기에는 uncertain·실패·표본만 보인다."""
    keep_set = {str(k) for k in keep} if keep else None
    has_id = bool(run.ids)
    header = ["i"] + (["line"] if run.file_mode else []) + (["id"] if has_id else []) + ["answer", "confidence", "flags"]
    if run.file_mode:
        header.append("excerpt")
    processed = len(run.results)
    next_i = run.offset + processed
    end = run.selected if run.selected is not None else run.offset + run.total
    remaining = max(end - next_i, 0)

    sample: set[int] = set()
    if out is not None:
        sample = _sample(run, sample_per_answer)
        shown = [r for r in run.results if "error" in r or r["uncertain"] or r["i"] in sample]
    else:
        shown = [r for r in run.results if _shown(r, keep_set)]

    written = None
    spilled = None
    if out is not None:
        written = write_rows(run, out[0], out[1], append=run.offset > 0, verbose=verbose)
    elif len(shown) > max_rows:
        spilled = spill_path()
        write_rows(run, spilled, "tsv", verbose=verbose)

    lines: list[str] = []
    for r in shown[:max_rows]:
        parts = [str(r["i"])]
        if run.file_mode:
            parts.append(str(r.get("line", "")))
        if has_id:
            parts.append(run.ids.get(r["i"], ""))
        if "error" in r:
            parts += ["ERROR", "", _cell(r["error"])]
        else:
            flags = []
            if "score" in r:
                flags.append(f"score={r['score']}")
            if r["uncertain"]:
                flags.append("uncertain")
            if r["i"] in sample:
                flags.append("sample")
            if verbose and r.get("probabilities") is not None:
                flags.append(json.dumps(r["probabilities"], ensure_ascii=False))
            parts += [str(r["answer"]), _fmt_conf(r["confidence"]), " ".join(flags)]
        if run.file_mode:
            parts.append(run.excerpts.get(r["i"], ""))
        lines.append("\t".join(parts))

    done = [r for r in run.results if "error" not in r]
    counts = Counter(str(r["answer"]) for r in done)
    n_unc = sum(1 for r in done if r["uncertain"])
    n_err = processed - len(done)
    summary = (
        f"집계: 처리 {processed}/{run.total}"
        + (" | " + ", ".join(f"{k} {v}" for k, v in counts.most_common()) if counts else "")
        + f" | uncertain {n_unc} | 요청 실패 {n_err} | {run.elapsed_ms:.0f}ms"
    )

    # 끝나지 않았으면 맨 위에 알린다(아래쪽 안내는 놓치기 쉽다).
    top: list[str] = []
    if run.unreachable:
        top.append(
            f"⚠ {UNREACHABLE} ({run.unreachable}). 항목 {next_i}번부터 {remaining}개는 처리하지 못함. "
            "Meshnet 연결과 서버 상태(health)를 확인할 것."
        )
    elif remaining:
        why = "시간 예산을 다 써서" if run.budget_hit else "한 번에 처리하는 상한에 걸려"
        top.append(
            f"⚠ 아직 끝나지 않음: {why} {run.offset}~{next_i - 1}번만 처리했고 {remaining}개가 남음. "
            f"같은 인자에 offset={next_i}로 다시 호출해 끝까지 처리할 것"
            + ("(out 파일에는 이어 붙는다)" if out is not None else "")
            + ". 남은 항목을 직접 분석으로 대신하지 말 것."
        )

    body = ["\t".join(header), *lines, "---", summary]
    if out is not None:
        body.append(
            f"전체 결과 {written}행을 {out[0]}에 {out[1].upper()}로 씀"
            + ("(이어 붙임)" if run.offset > 0 else "")
            + f". 열: {', '.join(OUT_COLUMNS)}"
            + ("(uncertain은 1/0)" if out[1] == "tsv" else "")
            + ". 스크립트로 이 파일을 읽어 답을 만든다."
        )
        body.append(f"표시: uncertain·요청 실패와 답마다 표본 {sample_per_answer}개(flags=sample) 총 {len(shown)}행. 이것만 직접 확인하면 된다")
    elif keep_set is not None:
        body.append(f"표시: keep={sorted(keep_set)}와 uncertain·요청 실패 {len(shown)}행, 나머지 {processed - len(shown)}행은 집계에만 있음")
    if len(shown) > max_rows:
        body.append(
            f"표시 행이 많아 {max_rows}행까지만 보임({len(shown) - max_rows}행 생략)."
            + (f" 전체 결과는 {spilled}에 TSV로 씀(열: {', '.join(OUT_COLUMNS)}). 다음부터는 out으로 경로를 줄 것" if spilled else "")
        )
    if run.masked:
        body.append(f"보내기 전에 비밀값으로 보이는 {run.masked}곳을 {MASK}로 가림")
    if run.selected is not None:
        body.append(f"파일 항목: grep 뒤 {run.selected}개 중 {run.offset}~{next_i - 1}번 처리")
    if top:
        body.append(top[0])
    return "\n".join(top + body)


def summarize_answers(resp: dict) -> dict:
    """ask 결과: 서버 답 원형에 uncertain 표시만 덧붙인다."""
    answers = resp.get("answers") or {}
    uncertain = []
    for k, a in answers.items():
        if ("noul" in a and is_uncertain_noul(float(a["noul"]))):
            a["uncertain"] = True
            uncertain.append(k)
    return {
        "answers": answers,
        "uncertain": uncertain,
        "latency_ms": resp.get("latency_ms"),
        "input_tokens": (resp.get("usage") or {}).get("input_tokens"),
    }


async def run_ask(cfg: Config, state: Any, questions: dict, images: list[str] | None = None) -> str:
    state, _ = mask_value(state)
    body: dict[str, Any] = {"state": state, "questions": questions}
    if images:
        body["images"] = images
    try:
        async with cfg.client() as client:
            resp = await post_systemone(client, cfg, body)
    except Unreachable as ex:
        return f"⚠ {UNREACHABLE} ({ex})"
    except httpx.TimeoutException:
        return f"ERROR 시간 초과({cfg.timeout:g}s)"
    except ApiError as ex:
        return f"ERROR {ex.status} {ex.message}"
    return json.dumps(summarize_answers(resp), ensure_ascii=False)


async def run_health(cfg: Config) -> str:
    t0 = time.perf_counter()
    try:
        async with cfg.client() as client:
            h = await client.get("/health")
            ms = (time.perf_counter() - t0) * 1000
            try:
                m = (await client.get("/v1/models")).json()
            except (httpx.HTTPError, ValueError):
                m = None
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.RemoteProtocolError) as ex:
        return f"⚠ {UNREACHABLE} ({cfg.url}): {type(ex).__name__}"
    except httpx.TimeoutException:
        return f"⚠ {UNREACHABLE} ({cfg.url}): 시간 초과"
    try:
        body = h.json()
    except ValueError:
        body = {"raw": h.text[:200]}
    ok = h.status_code == 200 and body.get("status") == "ok"
    return json.dumps(
        {"ok": ok, "url": cfg.url, "http": h.status_code, "health": body, "models": m,
         "round_trip_ms": round(ms, 1)},
        ensure_ascii=False,
    )
