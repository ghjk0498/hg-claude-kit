import json

import pytest

from torchcast_mcp import core, prep, server

from .fake_server import FakeTorchcast, choice_answer, noul_answer

OPTS = {"error": "실패", "info": "정상"}


@pytest.fixture
def env(monkeypatch):
    def set_url(url, **kw):
        monkeypatch.setenv("TORCHCAST_URL", url)
        for k, v in kw.items():
            monkeypatch.setenv(f"TORCHCAST_{k.upper()}", str(v))
    return set_url


def by_state(body):
    s = body["state"] if isinstance(body["state"], str) else json.dumps(body["state"])
    if "ERROR" in s or "error" in s:
        return 200, choice_answer("error", {"error": 0.97, "info": 0.03}), 0
    if "maybe" in s:
        return 200, choice_answer("info", {"error": 0.45, "info": 0.55}), 0
    return 200, choice_answer("info", {"error": 0.05, "info": 0.95}), 0


def table(out: str) -> list[list[str]]:
    lines = out.split("\n---\n")[0].splitlines()
    start = next(k for k, l in enumerate(lines) if l.startswith("i\t"))  # 위에 경고 줄이 올 수 있다
    return [l.split("\t") for l in lines[start + 1:]]


@pytest.fixture
def log(tmp_path):
    p = tmp_path / "app.log"
    p.write_text(
        "INFO start\n"          # 1
        "\n"                    # 2 (빈 줄, 버림)
        "ERROR db down\n"       # 3
        "INFO ok\n"             # 4
        "INFO maybe slow\n"     # 5
        "ERROR timeout\n"       # 6
    )
    return p


async def test_file_lines_keep_shows_only_wanted_and_uncertain(env, log):
    with FakeTorchcast(by_state) as fake:
        env(fake.url)
        out = await server.classify("로그 성격?", "choice", path=str(log), options=OPTS, keep=["error"])
    t = table(out)
    # error 2개 + uncertain 1개(maybe)만 행으로, info 2개는 집계에만
    assert [(r[1], r[2]) for r in t] == [("3", "error"), ("5", "info"), ("6", "error")]
    assert t[1][4] == "uncertain"
    assert t[0][5] == "ERROR db down"  # excerpt
    assert "처리 5/5 | info 3, error 2" in out
    assert "나머지 2행은 집계에만" in out
    assert len(fake.requests) == 5  # 빈 줄은 보내지 않음
    assert fake.requests[0]["state"] == "INFO start"


async def test_grep_and_offset(env, log):
    with FakeTorchcast(by_state) as fake:
        env(fake.url)
        out = await server.classify("q", "choice", path=str(log), options=OPTS, grep=r"^INFO", offset=1)
    t = table(out)
    assert [r[1] for r in t] == ["4", "5"]
    assert [r[0] for r in t] == ["1", "2"]
    assert "grep 뒤 3개 중 1~2번 처리" in out
    assert len(fake.requests) == 2


async def test_file_item_cap_suggests_next_offset(env, tmp_path):
    p = tmp_path / "many.log"
    p.write_text("".join(f"INFO {i}\n" for i in range(10)))
    with FakeTorchcast(by_state) as fake:
        env(fake.url, max_file_items=4)
        out = await server.classify("q", "choice", path=str(p), options=OPTS, keep=["error"])
    assert "처리 4/4" in out
    assert "offset=4로 다시 호출" in out
    assert len(fake.requests) == 4


async def test_time_budget_stops_and_suggests_offset(env, tmp_path):
    p = tmp_path / "slow.log"
    p.write_text("".join(f"INFO {i}\n" for i in range(10)))
    with FakeTorchcast(lambda b: (200, noul_answer(0.9), 0.15)) as fake:
        env(fake.url, max_seconds=0.4)
        out = await server.classify("q", "noul", path=str(p))
    n = len(fake.requests)
    assert 2 <= n < 10
    assert f"offset={n}" in out and "시간 예산" in out


async def test_jsonl_and_blank(env, tmp_path):
    j = tmp_path / "issues.jsonl"
    j.write_text('{"title": "crash on login", "kind": "error"}\nnot json\n')
    b = tmp_path / "fails.txt"
    b.write_text("FAILED a\n  trace 1\n\n\nFAILED b\n  ERROR x\n")
    with FakeTorchcast(by_state) as fake:
        env(fake.url)
        await server.classify("q", "choice", path=str(j), split="jsonl", options=OPTS)
        out = await server.classify("q", "choice", path=str(b), split="blank", options=OPTS)
    assert fake.requests[0]["state"] == {"title": "crash on login", "kind": "error"}
    assert fake.requests[1]["state"] == "not json"
    assert fake.requests[2]["state"] == "FAILED a\n  trace 1"
    assert [r[1] for r in table(out)] == ["1", "5"]
    assert table(out)[1][5] == "FAILED b ERROR x"


async def test_input_errors(env, log, tmp_path):
    env("http://127.0.0.1:9")
    assert "정확히 하나" in await server.classify("q", "noul")
    assert "정확히 하나" in await server.classify("q", "noul", items=["a"], path=str(log))
    assert "파일이 없음" in await server.classify("q", "noul", path=str(tmp_path / "nope"))
    assert "정규식 오류" in await server.classify("q", "noul", path=str(log), grep="(")
    assert "보낼 항목이 없음" in await server.classify("q", "noul", path=str(log), grep="zzz")
    assert "범위 밖" in await server.classify("q", "noul", path=str(log), offset=99)
    big = ["x"] * 201
    assert "path로 주거나" in await server.classify("q", "noul", items=big)


async def test_secrets_masked_before_sending(env, tmp_path):
    p = tmp_path / "env.log"
    p.write_text(
        "using key sk-ant-api03-AAAABBBBCCCCDDDD\n"
        "export DB_PASSWORD=hunter2hunter\n"
        "Authorization: Bearer abcdefghijklmnop123456\n"
        "aws AKIAABCDEFGHIJKLMNOP done\n"
        "postgres://app:s3cretpw@db:5432/x\n"
        "plain line\n"
    )
    with FakeTorchcast(by_state) as fake:
        env(fake.url)
        out = await server.classify("q", "choice", path=str(p), options=OPTS)
        await server.classify("q", "choice", items=[{"user": "a", "api_key": "zzzzzzzz", "msg": "token=abc123xyz"}],
                              options=OPTS)
        await server.ask({"note": "ghp_" + "a" * 36}, {"x": {"type": "noul", "instructions": "?"}})
    sent = json.dumps([r["state"] for r in fake.requests], ensure_ascii=False)
    for secret in ("AAAABBBBCCCCDDDD", "hunter2hunter", "abcdefghijklmnop123456", "AKIAABCDEFGHIJKLMNOP",
                   "s3cretpw", "zzzzzzzz", "abc123xyz", "a" * 36):
        assert secret not in sent, secret
        assert secret not in out
    assert fake.requests[1]["state"] == "export DB_PASSWORD=[MASKED]"
    assert fake.requests[4]["state"] == "postgres://app:[MASKED]@db:5432/x"
    assert fake.requests[5]["state"] == "plain line"
    assert "5곳을 [MASKED]로 가림" in out


def test_mask_leaves_normal_text():
    for s in ["GET /api/token/refresh 200", "password reset email sent", "skip-ant tests", "user=bob"]:
        assert prep.mask_text(s) == (s, 0), s


async def test_inline_rows_cap(env):
    with FakeTorchcast(by_state) as fake:
        env(fake.url)
        run = await core.run_classify(core.Config.from_env(), [prep.Entry(i, "x") for i in range(5)], "q", "choice", OPTS)
    out = core.format_classify(run, max_rows=2)
    assert len(table(out)) == 2 and "3행 생략" in out
    # 잘린 행도 버리지 않고 임시 TSV에 전부 쓴다
    import re
    spilled = re.search(r"전체 결과는 (\S+\.tsv)에", out).group(1)
    lines = open(spilled, encoding="utf-8").read().splitlines()
    assert lines[0].split("\t") == core.OUT_COLUMNS and len(lines) == 6


async def test_measure_script_runs_against_fake(env, tmp_path):
    """measure/run.py가 현재 core API와 맞는지(예전에 Entry로 바뀐 것을 놓친 적이 있다)."""
    import importlib.util
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("measure_run", root / "measure" / "run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    samples = tmp_path / "samples.json"
    samples.write_text((root / "measure" / "samples.json").read_text())
    with FakeTorchcast(by_state) as fake:
        env(fake.url)
        fake.health_status = {"status": "ok", "model": "fake"}
        await mod.main(samples)
    out = json.loads(next(tmp_path.glob("results-*.json")).read_text())
    assert out["model"] == "fake" and out["overall"]["n"] == 26


def test_caps_fit_real_workload():
    """2,500개 파일을 한 번에(항목당 ~50ms ≈ 125초, 예산 240초) 처리할 수 있어야 한다."""
    cfg = core.Config()
    assert cfg.max_file_items >= 2500
    assert 2500 * 0.05 < cfg.max_seconds


async def test_out_tsv_writes_all_rows_and_returns_summary(env, log, tmp_path):
    out_path = tmp_path / "result.tsv"
    with FakeTorchcast(by_state) as fake:
        env(fake.url)
        out = await server.classify("로그 성격?", "choice", path=str(log), options=OPTS, out=str(out_path))
    lines = out_path.read_text(encoding="utf-8").splitlines()
    assert lines[0].split("\t") == core.OUT_COLUMNS
    rows = [dict(zip(core.OUT_COLUMNS, l.split("\t"))) for l in lines[1:]]
    assert [(r["line"], r["answer"], r["uncertain"]) for r in rows] == [
        ("1", "info", "0"), ("3", "error", "0"), ("4", "info", "0"), ("5", "info", "1"), ("6", "error", "0")]
    assert rows[1]["excerpt"] == "ERROR db down" and rows[1]["confidence"] == "0.94"
    assert str(out_path) in out and "5행" in out
    # 도구 출력에는 uncertain과 답별 표본만(여기선 답별 3개 이하라 전부 표본)
    t = table(out)
    assert {r[1] for r in t if "uncertain" in r[4]} == {"5"}
    assert all(("sample" in r[4]) != ("uncertain" in r[4]) for r in t)
    assert "아직 끝나지 않음" not in out


async def test_out_sample_is_small(env, tmp_path):
    p = tmp_path / "many.log"
    p.write_text("".join(f"INFO {i}\n" for i in range(50)) + "ERROR x\n" * 10)
    out_path = tmp_path / "r.tsv"
    with FakeTorchcast(by_state) as fake:
        env(fake.url)
        out = await server.classify("q", "choice", path=str(p), options=OPTS, out=str(out_path))
    t = table(out)
    assert len(t) == 6 and sum(r[2] == "error" for r in t) == 3
    assert len(out_path.read_text().splitlines()) == 61


async def test_out_jsonl_with_id_key_and_continuation_appends(env, tmp_path):
    p = tmp_path / "issues.jsonl"
    p.write_text("".join(json.dumps({"number": 100 + k, "title": "ERROR crash" if k % 2 else "docs"}) + "\n"
                         for k in range(6)))
    out_path = tmp_path / "r.jsonl"
    with FakeTorchcast(by_state) as fake:
        env(fake.url, max_file_items=4)
        first = await server.classify("q", "choice", path=str(p), split="jsonl", options=OPTS,
                                      out=str(out_path), id_key="number")
        assert first.startswith("⚠ 아직 끝나지 않음")
        assert "offset=4로 다시 호출" in first and "2개가 남음" in first
        second = await server.classify("q", "choice", path=str(p), split="jsonl", options=OPTS,
                                       out=str(out_path), id_key="number", offset=4)
    assert "아직 끝나지 않음" not in second and "이어 붙임" in second
    rows = [json.loads(l) for l in out_path.read_text().splitlines()]
    assert [r["id"] for r in rows] == [str(100 + k) for k in range(6)]
    assert [r["i"] for r in rows] == list(range(6))
    assert [r["answer"] for r in rows] == ["info", "error"] * 3
    assert set(rows[0]) >= set(core.OUT_COLUMNS)
    # 표에도 id 열이 붙는다
    assert table(second)[0][2] in {"104", "105"}


async def test_out_tsv_continuation_keeps_single_header(env, tmp_path):
    p = tmp_path / "x.log"
    p.write_text("".join(f"INFO {i}\n" for i in range(5)))
    out_path = tmp_path / "r.tsv"
    out_path.write_text("\t".join(core.OUT_COLUMNS) + "\n0\t9\t\tstale\t\t\t\t\t\n")  # 이전 실행 결과
    with FakeTorchcast(by_state) as fake:
        env(fake.url, max_file_items=3)
        await server.classify("q", "choice", path=str(p), options=OPTS, out=str(out_path))
        await server.classify("q", "choice", path=str(p), options=OPTS, out=str(out_path), offset=3)
    lines = out_path.read_text().splitlines()
    assert lines[0].startswith("i\tline") and len(lines) == 6  # offset=0은 덮어쓴다
    assert [l.split("\t")[1] for l in lines[1:]] == ["1", "2", "3", "4", "5"]


async def test_out_items_mode_has_excerpt(env, tmp_path):
    out_path = tmp_path / "r.tsv"
    with FakeTorchcast(by_state) as fake:
        env(fake.url)
        await server.classify("q", "choice", items=["ERROR\tone", {"id": "t1", "msg": "ok"}], options=OPTS,
                              out=str(out_path), id_key="id")
    rows = [l.split("\t") for l in out_path.read_text().splitlines()[1:]]
    assert rows[0][8] == "ERROR one" and rows[0][1] == ""
    assert rows[1][2] == "t1"


async def test_out_path_errors(env, log, tmp_path):
    env("http://127.0.0.1:9")
    assert "절대 경로" in await server.classify("q", "noul", path=str(log), out="r.tsv")
    assert ".tsv 또는 .jsonl" in await server.classify("q", "noul", path=str(log), out=str(tmp_path / "r.txt"))
    assert "디렉터리가 없음" in await server.classify("q", "noul", path=str(log), out=str(tmp_path / "no" / "r.tsv"))
    (tmp_path / "d.tsv").mkdir()
    assert "파일이 아님" in await server.classify("q", "noul", path=str(log), out=str(tmp_path / "d.tsv"))
    src = tmp_path / "in.tsv"
    src.write_text("a\n")
    assert "입력 파일" in await server.classify("q", "noul", path=str(src), out=str(src))
    assert src.read_text() == "a\n"


async def test_out_masks_secrets_in_file(env, tmp_path):
    p = tmp_path / "s.log"
    p.write_text("export DB_PASSWORD=hunter2hunter\n")
    out_path = tmp_path / "r.tsv"
    with FakeTorchcast(by_state) as fake:
        env(fake.url)
        await server.classify("q", "choice", path=str(p), options=OPTS, out=str(out_path))
    assert "hunter2hunter" not in out_path.read_text()


@pytest.mark.parametrize("name,content", [
    ("notes.tsv", "name\tvalue\nimportant\t1\n"),
    ("data.jsonl", '{"user": "a"}\n'),
    ("bin.tsv", None),
])
async def test_out_refuses_to_overwrite_foreign_file(env, log, tmp_path, name, content):
    target = tmp_path / name
    if content is None:
        target.write_bytes(b"\xff\xfe\x00garbage")
    else:
        target.write_text(content)
    before = target.read_bytes()
    with FakeTorchcast(by_state) as fake:
        env(fake.url)
        for offset in (0, 1):
            out = await server.classify("q", "choice", path=str(log), options=OPTS, out=str(target), offset=offset)
            assert out.startswith("ERROR") and "덮어쓰지 않음" in out
    assert target.read_bytes() == before
    assert fake.requests == []  # 보내기 전에 거절


async def test_out_overwrites_previous_jsonl_and_empty_file(env, log, tmp_path):
    j = tmp_path / "r.jsonl"
    e = tmp_path / "empty.tsv"
    e.write_text("")
    with FakeTorchcast(by_state) as fake:
        env(fake.url)
        await server.classify("q", "choice", path=str(log), options=OPTS, out=str(j))
        again = await server.classify("q", "choice", path=str(log), options=OPTS, out=str(j))
        empty = await server.classify("q", "choice", path=str(log), options=OPTS, out=str(e))
    assert not again.startswith("ERROR") and not empty.startswith("ERROR")
    assert len(j.read_text().splitlines()) == 5 and len(e.read_text().splitlines()) == 6
