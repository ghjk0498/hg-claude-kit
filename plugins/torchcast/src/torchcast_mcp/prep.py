"""항목 준비: 파일에서 항목 읽기, 보내기 전 비밀값 가리기."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

Split = Literal["lines", "jsonl", "blank"]
MAX_FILE_BYTES = 50 * 1024 * 1024
MASK = "[MASKED]"


@dataclass
class Entry:
    i: int  # 고른 항목 안에서의 번호(0부터, offset 반영)
    value: Any
    line: int | None = None  # 파일 모드일 때 원래 줄 번호(1부터). blank 모드는 블록 첫 줄


class PrepError(Exception):
    pass


def read_entries(path: str, split: Split = "lines", grep: str | None = None) -> list[Entry]:
    """파일을 항목으로 나누고 grep으로 거른다. 빈 줄·빈 블록은 버린다."""
    p = Path(path).expanduser()
    if not p.is_file():
        raise PrepError(f"파일이 없음: {path}")
    size = p.stat().st_size
    if size > MAX_FILE_BYTES:
        raise PrepError(f"파일이 너무 큼: {size // 1024 // 1024}MB (최대 {MAX_FILE_BYTES // 1024 // 1024}MB). grep으로 먼저 줄일 것")
    try:
        pattern = re.compile(grep) if grep else None
    except re.error as ex:
        raise PrepError(f"grep 정규식 오류: {ex}") from ex

    text = p.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    raw: list[tuple[int, str]] = []  # (줄 번호, 원문)
    if split in ("lines", "jsonl"):
        raw = [(n, s) for n, s in enumerate(lines, 1) if s.strip()]
    elif split == "blank":
        start, buf = None, []
        for n, s in enumerate(lines, 1):
            if s.strip():
                if start is None:
                    start = n
                buf.append(s)
            elif buf:
                raw.append((start, "\n".join(buf)))
                start, buf = None, []
        if buf:
            raw.append((start, "\n".join(buf)))
    else:
        raise PrepError(f"split은 lines, jsonl, blank 중 하나여야 함: {split!r}")

    if pattern:
        raw = [(n, s) for n, s in raw if pattern.search(s)]

    out = []
    for i, (n, s) in enumerate(raw):
        value: Any = s
        if split == "jsonl":
            try:
                value = json.loads(s)
            except ValueError:
                value = s
        out.append(Entry(i=i, value=value, line=n))
    return out


# 보내기 전에 가릴 패턴. 완벽하지 않다(최선 노력). 앞쪽 그룹이 있으면 그 부분은 남긴다.
_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)"),
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})"),
    re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),  # JWT
    re.compile(r"(?i)(\bbearer\s+)[A-Za-z0-9._~+/=-]{12,}"),
    # DB_PASSWORD=, api_key:, "token": 등. 앞은 글자가 아니면 되고(_ 허용), 뒤에 _ID 같은 꼬리가 붙어도 된다.
    re.compile(r"(?i)((?<![A-Za-z])(?:password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|client[_-]?secret)[A-Za-z_]*[\"']?\s*[=:]\s*[\"']?)[^\s\"',;&]+"),
    re.compile(r"(?i)(://[^:/\s@]+:)[^@\s/]+(?=@)"),  # URL 안의 비밀번호
]
_SENSITIVE_KEY = re.compile(r"(?i)(password|passwd|secret|token|api[_-]?key|access[_-]?key|authorization|cookie|private[_-]?key)")


def mask_text(s: str) -> tuple[str, int]:
    n = 0
    for pat in _PATTERNS:
        def sub(m: re.Match) -> str:
            nonlocal n
            n += 1
            return (m.group(1) if m.groups() and m.group(1) else "") + MASK
        s = pat.sub(sub, s)
    return s, n


def mask_value(v: Any) -> tuple[Any, int]:
    """문자열·객체·배열 안의 비밀값을 가린다. 민감한 이름의 키는 값을 통째로 가린다."""
    if isinstance(v, str):
        return mask_text(v)
    if isinstance(v, list):
        total, out = 0, []
        for x in v:
            y, k = mask_value(x)
            out.append(y)
            total += k
        return out, total
    if isinstance(v, dict):
        total, out = 0, {}
        for key, x in v.items():
            if _SENSITIVE_KEY.search(str(key)) and isinstance(x, (str, int, float)) and str(x):
                out[key] = MASK
                total += 1
            else:
                out[key], k = mask_value(x)
                total += k
        return out, total
    return v, 0


def excerpt(v: Any, n: int) -> str:
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    s = " ".join(s.split())  # 줄바꿈·탭을 공백으로
    return s if len(s) <= n else s[: n - 1] + "…"
