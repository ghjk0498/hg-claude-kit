import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

import stop_check

from .fake_server import FakeTorchcast, free_port

PLUGIN = Path(__file__).resolve().parents[1]


def user(text):
    return {"type": "user", "message": {"role": "user", "content": text}}


def say(text):
    return {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}


def call(i, name, **inp):
    return {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": f"t{i}", "name": name, "input": inp}]}}


def result(i, text, error=False):
    return {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": f"t{i}",
                                                     "content": text, "is_error": error}]}}


EDIT_THEN_CLAIM = [
    user("이전 요청"), call(0, "Bash", command="uv run pytest"), result(0, "1 passed"), say("이전 답"),
    user("버그 고쳐 줘"),
    call(1, "Read", file_path="/r/a.py"), result(1, "..."),
    call(2, "Edit", file_path="/r/a.py", old_string="x", new_string="y"), result(2, "ok"),
    say("고쳤습니다. 이제 동작합니다."),
]


def write(tp, entries):
    tp.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in entries) + "\n")


@pytest.fixture
def hook(tmp_path, monkeypatch):
    log = tmp_path / "log.jsonl"
    monkeypatch.setattr(stop_check, "LOG", log)
    monkeypatch.setattr(stop_check, "TIMEOUT", 0.5)

    def make(entries, url, **extra):
        monkeypatch.setattr(stop_check, "URL", url)
        tp = tmp_path / "t.jsonl"
        write(tp, entries)
        out = stop_check.run({"session_id": "s", "transcript_path": str(tp), "stop_hook_active": False, **extra})
        return out, json.loads(log.read_text().splitlines()[-1])
    return make


def answers(claim, verified, contradicts=0.02):
    vals = {"claim": claim, "verified": verified, "contradicts": contradicts}
    return lambda b: (200, {"answers": {k: {"type": "noul", "noul": v} for k, v in vals.items()}}, 0)


def test_blocks_claim_without_verification(hook):
    with FakeTorchcast(answers(0.97, 0.03)) as fake:
        out, rec = hook(EDIT_THEN_CLAIM, fake.url)
    assert out["decision"] == "block" and "테스트·빌드" in out["reason"]
    assert rec["decision"] == "block:unverified" and rec["edits"] == 1
    state = fake.requests[0]["state"]
    assert "pytest" not in state and "이전 답" not in state  # 이번 턴만
    assert "[마지막 응답]\n고쳤습니다." in state
    assert "#2 파일 수정 /r/a.py → 성공   ← 마지막 파일 수정" in state
    qs = fake.requests[0]["questions"]
    assert set(qs) == {"claim", "verified", "contradicts"} and all(q["type"] == "noul" for q in qs.values())


def test_blocks_success_claim_contradicting_failed_test(hook):
    entries = EDIT_THEN_CLAIM[:-1] + [call(3, "Bash", command="pytest"), result(3, "2 failed, 5 passed", True),
                                      say("고쳤고 테스트가 모두 통과합니다.")]
    with FakeTorchcast(answers(0.97, 0.96, 0.95)) as fake:
        out, rec = hook(entries, fake.url)
    assert rec["decision"] == "block:contradiction" and "실패나 오류" in out["reason"]
    assert "#3 Bash: pytest → 실패: 2 failed, 5 passed" in fake.requests[0]["state"]


@pytest.mark.parametrize("claim,verified,contra,decision", [
    (0.97, 0.95, 0.02, "pass"),                  # 검증했고 결과와 맞음
    (0.05, 0.03, 0.02, "pass"),                  # 주장 없음
    (0.801, 0.03, 0.02, "pass:uncertain"),       # 주장 불확실
    (0.97, 0.199, 0.02, "pass:uncertain"),       # 실행 여부 불확실
    (0.97, 0.95, 0.801, "pass:uncertain"),       # 모순 불확실
    (0.97, 0.199, 0.95, "block:contradiction"),  # 실행 불확실해도 모순이 확실하면 막음
    (0.97, 0.03, 0.199, "block:unverified"),     # 모순 불확실해도 미실행이 확실하면 막음
])
def test_decisions(hook, claim, verified, contra, decision):
    with FakeTorchcast(answers(claim, verified, contra)) as fake:
        out, rec = hook(EDIT_THEN_CLAIM, fake.url)
    assert rec["decision"] == decision
    assert (out is not None) == decision.startswith("block")


def test_no_edits_and_docs_only_skip_server(hook):
    no_edit = [user("질문"), call(1, "Bash", command="ls"), result(1, "a"), say("완료했습니다.")]
    docs = [user("x"), call(1, "Edit", file_path="/r/README.md"), result(1, "ok"),
            call(2, "Write", file_path="/r/docs/plan.txt"), result(2, "ok"), say("문서를 고쳤습니다.")]
    mixed = docs[:-1] + [call(3, "Edit", file_path="/r/src/a.py"), result(3, "ok"), say("완료했습니다.")]
    with FakeTorchcast(answers(0.97, 0.03)) as fake:
        assert hook(no_edit, fake.url)[1]["decision"] == "pass:no_edits"
        assert hook(docs, fake.url)[1]["decision"] == "pass:docs_only"
        assert not fake.requests
        assert hook(mixed, fake.url)[0]["decision"] == "block"


def test_unreachable_timeout_errors_pass(hook):
    assert hook(EDIT_THEN_CLAIM, f"http://127.0.0.1:{free_port()}")[1]["decision"] == "pass:unreachable"
    for handler, decision in [(lambda b: (200, {}, 2.0), "pass:unreachable"),
                              (lambda b: (503, {"error": "oom"}, 0), "pass:unreachable"),
                              (lambda b: (200, {"answers": {}}, 0), "pass:bad_response")]:
        with FakeTorchcast(handler) as fake:
            out, rec = hook(EDIT_THEN_CLAIM, fake.url)
        assert out is None and rec["decision"] == decision


def test_guards(hook):
    with FakeTorchcast(answers(0.97, 0.03)) as fake:
        assert hook(EDIT_THEN_CLAIM, fake.url, stop_hook_active=True)[1]["decision"] == "pass:already_blocked"
        assert hook(EDIT_THEN_CLAIM, fake.url, background_tasks=[{"id": "x"}])[1]["decision"] == "pass:background_tasks"
    assert not fake.requests


def test_prefers_last_assistant_message(hook):
    with FakeTorchcast(answers(0.97, 0.03)) as fake:
        out, _ = hook(EDIT_THEN_CLAIM[:-1], fake.url, last_assistant_message="다 고쳤고 통과합니다.")
    assert out["decision"] == "block"
    assert "[마지막 응답]\n다 고쳤고 통과합니다." in fake.requests[0]["state"]


def test_tail_read_finds_turn_across_chunks(tmp_path, monkeypatch):
    monkeypatch.setattr(stop_check, "TAIL_CHUNK", 64)  # 아주 작은 조각으로 거슬러 읽기
    old = [user("old")] + [say("x" * 50) for _ in range(200)]
    turn = [call(1, "Edit", file_path="/r/a.py"), result(1, "ok"), say("끝")]
    tp = tmp_path / "t.jsonl"
    write(tp, old + [user("이번 요청")] + turn)
    got = stop_check.load_turn(tp)
    assert got == turn
    # 사용자 입력이 읽기 한도 안에 없으면 읽은 범위 전체를 쓴다
    monkeypatch.setattr(stop_check, "TAIL_MAX", 300)
    got = stop_check.load_turn(tp)
    assert got and got[-1] == turn[-1] and len(got) < len(old)


def test_state_tail_fits_and_masks(hook, monkeypatch):
    monkeypatch.setattr(stop_check, "MAX_STATE_CHARS", 2000)
    entries = [user("x")]
    for i in range(200):
        entries += [call(i, "Bash", command=f"echo step {i}"), result(i, "ok")]
    entries += [call(999, "Write", file_path="/r/b.py", content="..."), result(999, "ok"),
                call(1000, "Bash", command="export API_KEY=sk-ant-api03-SECRETSECRET; uv run pytest -q"),
                result(1000, "32 passed"), say("완료. 테스트 통과.")]
    with FakeTorchcast(answers(0.97, 0.95)) as fake:
        out, rec = hook(entries, fake.url)
    s = fake.requests[0]["state"]
    assert len(s) <= 2000
    assert "생략" in s and "echo step 199" in s and "echo step 0 " not in s
    assert "SECRETSECRET" not in s
    assert "← 마지막 파일 수정" in s and "32 passed" in s
    assert rec["decision"] == "pass"


def test_runs_as_plugin_command_and_never_fails(tmp_path):
    # hooks.json과 같은 방식(python3 -I 파일 경로)으로 실행. 엉터리 입력에도 exit 0, 출력 없음
    env = {"CLAUDE_PLUGIN_DATA": str(tmp_path), "PATH": "/usr/bin:/bin"}
    for stdin in ["not json", "{}", json.dumps({"transcript_path": "/nope"})]:
        p = subprocess.run([sys.executable, "-I", str(PLUGIN / "stop_check.py")], input=stdin,
                           capture_output=True, text=True, timeout=20, env=env)
        assert p.returncode == 0 and p.stdout == ""
    assert (tmp_path / "decisions.jsonl").exists()  # 기록은 CLAUDE_PLUGIN_DATA 아래


def test_hooks_json_points_to_script():
    cfg = json.loads((PLUGIN / "hooks" / "hooks.json").read_text())
    cmd = cfg["hooks"]["Stop"][0]["hooks"][0]["command"]
    assert "${CLAUDE_PLUGIN_ROOT}/stop_check.py" in cmd and "-I" in cmd


def test_mask_rules_match_torchcast_plugin():
    """같은 규칙을 두 플러그인이 따로 가진다. 한쪽만 고치면 여기서 걸린다."""
    prep = PLUGIN.parent / "torchcast" / "src" / "torchcast_mcp" / "prep.py"
    if not prep.exists():
        pytest.skip("torchcast 플러그인이 옆에 없음")
    src = prep.read_text()
    theirs = re.findall(r're\.compile\((r".*?")\)', src.split("_PATTERNS = [", 1)[1].split("]\n", 1)[0])
    mine = [repr(p.pattern) for p in stop_check._PATTERNS]
    assert [eval(t) for t in theirs] == [p.pattern for p in stop_check._PATTERNS], (theirs, mine)


def test_disabled_by_env(hook, monkeypatch):
    monkeypatch.setenv("TORCHCAST_STOP_HOOK", "off")
    out, rec = hook(EDIT_THEN_CLAIM, "http://127.0.0.1:9")
    assert out is None and rec["decision"] == "pass:disabled"
