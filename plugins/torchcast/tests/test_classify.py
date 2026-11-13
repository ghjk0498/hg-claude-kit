import json

import pytest

from torchcast_mcp import core, server

from .fake_server import FakeTorchcast, choice_answer, free_port, noul_answer

OPTS = {"error": "실패·예외", "info": "정상 진행"}


@pytest.fixture
def env(monkeypatch):
    def set_url(url, **kw):
        monkeypatch.setenv("TORCHCAST_URL", url)
        for k, v in kw.items():
            monkeypatch.setenv(f"TORCHCAST_{k.upper()}", str(v))
    return set_url


async def cls(items, question, qtype, options=None, **kw):
    return await server.classify(question, qtype, items=items, options=options, **kw)


def rows(text: str) -> list[list[str]]:
    lines = text.split("\n---\n")[0].splitlines()
    start = next(k for k, l in enumerate(lines) if l.startswith("i\t"))  # 위에 경고 줄이 올 수 있다
    return [line.split("\t") for line in lines[start + 1:]]


async def test_normal_choice(env):
    def h(body):
        state = body["state"]
        if "Exception" in state:
            return 200, choice_answer("error", {"error": 0.97, "info": 0.03}), 0
        return 200, choice_answer("info", {"error": 0.1, "info": 0.9}), 0

    with FakeTorchcast(h) as fake:
        env(fake.url)
        out = await cls(["Exception: boom", "started ok", "Exception: x"],
                                    "이 로그 줄은?", "choice", OPTS)
    r = rows(out)
    assert [x[1] for x in r] == ["error", "info", "error"]
    assert r[0][2] == "0.94"
    assert all("uncertain" not in x for x in r)
    assert "처리 3/3 | error 2, info 1 | uncertain 0 | 요청 실패 0" in out
    # 항목마다 요청 하나, 질문 형식 확인
    assert len(fake.requests) == 3
    assert fake.requests[0]["questions"]["q"] == {"type": "choice", "instructions": "이 로그 줄은?",
                                                  "criteria": OPTS}
    assert "probabilities" not in out and "{" not in out


async def test_verbose_and_context_and_object_items(env):
    with FakeTorchcast(lambda b: (200, choice_answer("info", {"error": 0.2, "info": 0.8}), 0)) as fake:
        env(fake.url)
        out = await cls([{"line": 1}, "plain"], "q", "choice", OPTS,
                                    context="서비스 A 로그", verbose=True)
    assert '"info": 0.8' in out
    assert fake.requests[0]["state"] == {"context": "서비스 A 로그", "item": {"line": 1}}
    assert fake.requests[1]["state"].startswith("[배경]\n서비스 A 로그")


async def test_low_confidence_marked_uncertain(env):
    with FakeTorchcast(lambda b: (200, choice_answer("info", {"error": 0.4, "info": 0.6}), 0)) as fake:
        env(fake.url)
        out = await cls(["a"], "q", "choice", OPTS)
        out2 = await cls(["a"], "q", "choice", OPTS, min_confidence=0.1)
    assert rows(out)[0][3] == "uncertain"
    assert "uncertain" not in rows(out2)[0]


@pytest.mark.parametrize("p,answer,uncertain", [
    (0.801, "yes", True), (0.199, "no", True), (0.97, "yes", False), (0.03, "no", False),
])
async def test_noul_boundary_values(env, p, answer, uncertain):
    with FakeTorchcast(lambda b: (200, noul_answer(p), 0)) as fake:
        env(fake.url)
        out = await cls(["x"], "테스트 실패인가?", "noul")
    r = rows(out)[0]
    assert r[1] == answer
    assert ("uncertain" in r) is uncertain
    assert f"uncertain {int(uncertain)}" in out
    assert "criteria" not in fake.requests[0]["questions"]["q"]


async def test_ask_marks_uncertain_noul(env):
    resp = {"answers": {"a": {"type": "noul", "noul": 0.199}, "b": {"type": "noul", "noul": 0.95}},
            "latency_ms": 12.0, "usage": {"input_tokens": 50}}
    with FakeTorchcast(lambda b: (200, resp, 0)) as fake:
        env(fake.url)
        out = json.loads(await server.ask("상황", {"a": {"type": "noul", "instructions": "?"},
                                                   "b": {"type": "noul", "instructions": "?"}}))
    assert out["uncertain"] == ["a"]
    assert out["answers"]["a"]["uncertain"] is True
    assert out["input_tokens"] == 50


async def test_score_maps_legend():
    a = {"type": "score", "score": 2.6, "confidence": 0.6,
         "legend": {"0": "low", "1": "medium", "2": "high", "3": "critical"},
         "probabilities": {"0": 0.006, "1": 0.032, "2": 0.317, "3": 0.645}}
    r = core.interpret(a, 0.5)
    assert r["answer"] == "critical" and r["score"] == 2.6 and not r["uncertain"]


async def test_connection_refused(env):
    env(f"http://127.0.0.1:{free_port()}")
    out = await cls(["a", "b"], "q", "choice", OPTS)
    assert core.UNREACHABLE in out
    assert "처리 0/2" in out
    assert core.UNREACHABLE in await server.health()
    assert core.UNREACHABLE in await server.ask("s", {"x": {"type": "noul", "instructions": "?"}})


async def test_server_dies_midway_returns_partial(env):
    calls = {"n": 0}
    fake = FakeTorchcast(lambda b: (200, noul_answer(0.9), 0))

    def h(body):
        calls["n"] += 1
        if calls["n"] == 2:
            # 두 번째 요청에 답한 뒤 서버를 내린다
            import threading
            threading.Thread(target=fake.stop).start()
        return 200, noul_answer(0.9), 0

    fake.handler = h
    with fake:
        env(fake.url)
        out = await cls(["a", "b", "c", "d"], "q", "noul")
    assert core.UNREACHABLE in out
    assert len(rows(out)) == 2
    assert "처리 2/4" in out
    assert "2번부터 2개" in out


async def test_422_and_503_recorded_per_item(env):
    def h(body):
        s = body["state"]
        if s == "bad":
            return 422, {"error": "a question takes 2 to 26 options, not 30"}, 0
        if s == "oom":
            return 503, {"error": "CUDA out of memory"}, 0
        return 200, noul_answer(0.95), 0

    with FakeTorchcast(h) as fake:
        env(fake.url)
        out = await cls(["ok", "bad", "oom", "ok"], "q", "noul")
    r = rows(out)
    assert r[1] == ["1", "ERROR", "", "422 a question takes 2 to 26 options, not 30"]
    assert r[2] == ["2", "ERROR", "", "503 CUDA out of memory"]
    assert r[3][1] == "yes"
    assert "요청 실패 2" in out
    # 503은 한 번 재시도한다: ok, bad, oom×2, ok
    assert len(fake.requests) == 5


async def test_timeout_per_item_then_abort(env):
    def h(body):
        return 200, noul_answer(0.95), (2.0 if body["state"].startswith("slow") else 0)

    with FakeTorchcast(h) as fake:
        env(fake.url, timeout=0.3)
        out = await cls(["fast", "slow1", "fast"], "q", "noul")
        assert rows(out)[1][1:] == ["ERROR", "", "시간 초과(0.3s)"]
        assert rows(out)[2][1] == "yes"
        assert core.UNREACHABLE not in out

        out2 = await cls(["slow1", "slow2", "slow3", "fast"], "q", "noul")
    assert core.UNREACHABLE in out2
    assert "연속 3회 시간 초과" in out2
    assert "처리 3/4" in out2


async def test_item_limit(env):
    with FakeTorchcast(lambda b: (200, noul_answer(0.9), 0)) as fake:
        env(fake.url, max_items=5)
        out = await cls(["x"] * 6, "q", "noul")
        ok = await cls(["x"] * 5, "q", "noul")
    assert out.startswith("ERROR 항목 6개는 상한 5개")
    assert "처리 5/5" in ok
    assert len(fake.requests) == 5


async def test_default_item_limit_is_200():
    assert core.Config().max_items == 200


@pytest.mark.parametrize("qtype,options,msg", [
    ("choice", {"a": "x"}, "2~26"),
    ("choice", [str(i) for i in range(27)], "2~26"),
    ("score", [str(i) for i in range(11)], "2~10"),
    ("choice", None, "options가 필요"),
    ("choice", ["a", "a"], "겹침"),
    ("bogus", None, "type은"),
])
async def test_local_validation(qtype, options, msg):
    out = await cls(["x"], "q", qtype, options)
    assert out.startswith("ERROR") and msg in out


async def test_health_ok(env):
    with FakeTorchcast(lambda b: (200, {}, 0)) as fake:
        env(fake.url)
        out = json.loads(await server.health())
    assert out["ok"] is True and out["models"]["data"][0]["id"] == "fake-model"


async def test_tools_registered_with_privacy_note():
    tools = {t.name: t for t in await server.mcp.list_tools()}
    assert set(tools) == {"classify", "ask", "health"}
    for name in ("classify", "ask"):
        assert "Meshnet" in tools[name].description and "개인정보" in tools[name].description
    props = tools["classify"].input_schema["properties"]
    assert {"items", "question", "type", "options", "context", "min_confidence", "verbose", "out", "id_key"} <= set(props)


async def test_wording_trusts_result_and_says_when_to_use():
    """결과를 처음부터 다시 확인하라는 문구가 다시 들어가지 않게 한다(harness-test에서 결과를 버리고 다시 풀었다)."""
    desc = {t.name: t for t in await server.mcp.list_tools()}["classify"].description
    text = desc + server.mcp.instructions
    for banned in ("거친", "최종 판단", "직접 다시"):
        assert banned not in text, banned
    for need in ("uncertain", "표본", "그대로", "grep/awk", "offset", "out"):
        assert need in desc and need in server.mcp.instructions, need
    assert server.PRIVACY in desc and server.PRIVACY in server.mcp.instructions
    # harness-test 평가 과제(test-triage: 1,000건 중 코드 결함 180건)의 성적을 도구 문구에 넣으면 측정이 오염된다
    for leak in ("180", "1,000건", "1000건", "harness"):
        assert leak not in text, leak
