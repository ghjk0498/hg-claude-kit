from __future__ import annotations

import sys

if sys.version_info < (3, 11):
    print("Python 3.11 이상이 필요하다. uv run python scripts/render.py 로 돌린다.", file=sys.stderr)
    sys.exit(2)

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

EFFORTS: tuple[str, ...] = ("low", "medium", "high", "xhigh", "max")


@dataclass(frozen=True)
class Tiers:
    checked: str
    models: dict[str, str]  # 별칭 -> 확인한 버전 이름
    tiers: dict[str, tuple[str, str]]  # 등급 이름 -> (model, effort), tiers.toml에 적힌 순서


def load_tiers(root: Path) -> tuple[Tiers | None, list[str]]:
    """root/"tiers.toml"을 읽는다. 문제가 있으면 (None, 문제 목록), 없으면 (Tiers, [])."""
    path = Path(root) / "tiers.toml"
    try:
        data = tomllib.loads(path.read_bytes().decode("utf-8"))
    except FileNotFoundError:
        return None, ["tiers.toml: 파일이 없다"]
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
        return None, [f"tiers.toml: 읽을 수 없다 ({e})"]

    problems: list[str] = []
    checked = data.get("checked")
    if not isinstance(checked, str):
        problems.append("tiers.toml: checked가 없거나 문자열이 아니다")
    models = data.get("models")
    if not (isinstance(models, dict) and all(isinstance(v, str) for v in models.values())):
        problems.append("tiers.toml: [models]가 없거나 별칭 = 버전 이름 표가 아니다")
        models = None
    raw_tiers = data.get("tiers")
    if not (isinstance(raw_tiers, dict) and raw_tiers):
        problems.append("tiers.toml: [tiers.*]가 없거나 표가 아니다")
        raw_tiers = None

    tiers: dict[str, tuple[str, str]] = {}
    if raw_tiers is not None:
        for name, spec in raw_tiers.items():
            if not isinstance(spec, dict):
                problems.append(f"tiers.toml: 등급 {name}이 표가 아니다")
                continue
            model, effort = spec.get("model"), spec.get("effort")
            ok = True
            if not isinstance(model, str):
                problems.append(f"tiers.toml: 등급 {name}에 model이 없다")
                ok = False
            elif models is not None and model not in models:
                problems.append(f"tiers.toml: 등급 {name}의 model {model}이 [models]에 없다")
                ok = False
            if not isinstance(effort, str):
                problems.append(f"tiers.toml: 등급 {name}에 effort가 없다")
                ok = False
            elif effort not in EFFORTS:
                problems.append(f"tiers.toml: 등급 {name}의 effort {effort}가 {', '.join(EFFORTS)}에 없다")
                ok = False
            if ok:
                tiers[name] = (model, effort)

    if problems:
        return None, problems
    return Tiers(checked, dict(models), tiers), []


def unknown_keys(root: Path) -> list[str]:
    """tiers.toml에서 쓰지 않는 키마다 경고 한 줄. 읽을 수 없으면 빈 목록(문제는 load_tiers가 낸다)."""
    try:
        data = tomllib.loads((Path(root) / "tiers.toml").read_bytes().decode("utf-8"))
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError):
        return []
    keys = [k for k in data if k not in ("checked", "models", "tiers")]
    tiers = data.get("tiers")
    if isinstance(tiers, dict):
        for name, spec in tiers.items():
            if isinstance(spec, dict):
                keys += [f"tiers.{name}.{k}" for k in spec if k not in ("model", "effort")]
    return [f"경고: tiers.toml의 {k}는 쓰지 않는 키다" for k in keys]


_COMP_RE = re.compile(r"^## 모델 보정 \((.+)\)\s*$", re.MULTILINE)


def _split(text: str) -> tuple[list[str], list[str]]:
    """(frontmatter 안쪽 줄들, 닫는 --- 뒤의 줄들). 형식이 틀리면 ValueError."""
    if "\r" in text:
        raise ValueError("줄 끝이 CRLF다 (LF만 쓴다)")
    lines = text.split("\n")
    if lines[0] != "---":
        raise ValueError("frontmatter가 ---로 시작하지 않는다")
    for i in range(1, len(lines)):
        if lines[i] == "---":
            return lines[1:i], lines[i + 1:]
    raise ValueError("frontmatter를 닫는 ---가 없다")


def frontmatter(text: str) -> dict[str, str]:
    inner, _ = _split(text)
    result: dict[str, str] = {}
    for line in inner:
        if not line.strip():
            continue
        key, sep, value = line.partition(":")
        if not sep or not key.strip():
            raise ValueError(f"frontmatter 줄이 key: value 형식이 아니다 ({line})")
        result[key.strip()] = value.strip()
    return result


def render_agent(text: str, model: str, effort: str) -> str:
    inner, rest = _split(text)
    for key, value in (("model", model), ("effort", effort)):
        idx = [i for i, line in enumerate(inner) if line.startswith(f"{key}:")]
        if len(idx) > 1:
            raise ValueError(f"frontmatter에 {key}: 줄이 {len(idx)}개다")
        if idx:
            inner[idx[0]] = f"{key}: {value}"
        else:
            inner.append(f"{key}: {value}")
    return "\n".join(["---", *inner, "---", *rest])


def compensation_versions(text: str) -> list[str]:
    _, rest = _split(text)
    return _COMP_RE.findall("\n".join(rest))


BEGIN = "<!-- tiers:begin -->"
END = "<!-- tiers:end -->"


def render_block(t: Tiers) -> str:
    lines = [BEGIN, "| 에이전트 | model | effort | 확인한 버전 |", "|---|---|---|---|"]
    for name, (model, effort) in t.tiers.items():
        lines.append(f"| `{name}` | `{model}` | `{effort}` | {t.models[model]} |")
    lines += ["", f"확인한 날: {t.checked}", END]
    return "\n".join(lines)


def _read(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


def build(root: Path) -> tuple[dict[Path, str], list[str]]:
    root = Path(root)
    t, problems = load_tiers(root)
    if t is None:
        return {}, problems

    files: dict[Path, str] = {}
    agents_dir = root / "agents"
    on_disk = {p.stem for p in agents_dir.glob("*.md")} if agents_dir.is_dir() else set()
    declared = set(t.tiers)
    for name in sorted(declared - on_disk):
        problems.append(f"짝이 없다: {name}은 tiers.toml에만 있고 agents/{name}.md가 없다")
    for name in sorted(on_disk - declared):
        problems.append(f"짝이 없다: agents/{name}.md는 있으나 tiers.toml에 {name} 등급이 없다")

    for name, (model, effort) in t.tiers.items():
        if name not in on_disk:
            continue
        path = agents_dir / f"{name}.md"
        try:
            text = _read(path)
            fm = frontmatter(text)
            new_text = render_agent(text, model, effort)
            versions = compensation_versions(text)
        except (ValueError, UnicodeDecodeError) as e:
            problems.append(f"{name}: {e}")
            continue
        if fm.get("name") != name:
            problems.append(f"{name}: frontmatter name이 파일 이름과 다르다 ({fm.get('name')})")
        for v in versions:
            if v != t.models[model]:
                problems.append(f"다시 볼 것: {name} — 모델 보정 ({v}), 지금은 {t.models[model]}")
        files[path] = new_text

    cls = root / "docs" / "classification.md"
    try:
        text = _read(cls)
    except FileNotFoundError:
        problems.append("docs/classification.md: 파일이 없다 (tiers:begin 표시를 둘 곳)")
    except UnicodeDecodeError as e:
        problems.append(f"docs/classification.md: 읽을 수 없다 ({e})")
    else:
        b, e = text.find(BEGIN), text.find(END)
        if text.count(BEGIN) != 1 or text.count(END) != 1 or b > e:
            problems.append("docs/classification.md: tiers:begin, tiers:end 표시가 각각 하나씩, 이 순서로 있어야 한다")
        else:
            files[cls] = text[:b] + render_block(t) + text[e + len(END):]

    return files, problems


def main(argv: list[str] | None = None, root: Path | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args not in ([], ["--check"]):
        print("사용법: render.py [--check]")
        return 1
    root = Path(__file__).resolve().parents[1] if root is None else Path(root)
    for warning in unknown_keys(root):
        print(warning, file=sys.stderr)
    files, problems = build(root)
    if problems:
        print("\n".join(problems))
        return 1
    changed = [p for p, content in files.items() if not p.is_file() or _read(p) != content]
    if args:
        for p in changed:
            print(p)
        return 1 if changed else 0
    for p in changed:
        p.write_bytes(files[p].encode("utf-8"))
        print(p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
