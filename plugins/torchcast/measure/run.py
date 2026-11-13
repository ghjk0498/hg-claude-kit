"""라벨 표본으로 실서버 정확도와 지연을 잰다. classify 도구와 같은 경로(core.run_classify)를 쓴다.

uv run python measure/run.py [samples.json]
"""

from __future__ import annotations

import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

import httpx

from torchcast_mcp import core
from torchcast_mcp.prep import Entry


async def latency(cfg: core.Config, n: int = 20) -> list[float]:
    body = {"state": "FAILED test_x - AssertionError", "questions": {"q": {"type": "noul", "instructions": "환경 문제인가?"}}}
    out = []
    async with cfg.client() as c:
        for _ in range(n):
            t = time.perf_counter()
            r = await c.post("/v1/systemone", json=body)
            r.raise_for_status()
            out.append((time.perf_counter() - t) * 1000)
    return out


def norm(label):
    if isinstance(label, bool):
        return "yes" if label else "no"
    return label


async def main(path: Path) -> None:
    cfg = core.Config.from_env()
    data = json.loads(path.read_text())
    report = {"model": None, "tasks": []}
    async with cfg.client() as c:
        report["model"] = (await c.get("/health")).json().get("model")
    tot = cor = unc = unc_wrong = conf_wrong = 0
    for t in data["tasks"]:
        items = [x[0] for x in t["items"]]
        labels = [norm(x[1]) for x in t["items"]]
        entries = [Entry(i=k, value=v) for k, v in enumerate(items)]
        run = await core.run_classify(cfg, entries, t["question"], t["type"], t.get("options"))
        rows = []
        for r, lab, it in zip(run.results, labels, items):
            ok = r.get("answer") == lab
            rows.append({"item": it, "label": lab, **{k: v for k, v in r.items() if k != "probabilities"}, "correct": ok})
            tot += 1
            cor += ok
            if r.get("uncertain"):
                unc += 1
                unc_wrong += not ok
            elif not ok:
                conf_wrong += 1
        report["tasks"].append({"name": t["name"], "n": len(items),
                                "correct": sum(x["correct"] for x in rows),
                                "elapsed_ms": round(run.elapsed_ms, 1), "rows": rows,
                                "unreachable": run.unreachable})
    lat = await latency(cfg)
    report["overall"] = {"n": tot, "correct": cor, "uncertain": unc, "uncertain_wrong": unc_wrong,
                         "confident_wrong": conf_wrong}
    report["latency_ms"] = {"n": len(lat), "median": round(statistics.median(lat), 1),
                            "p90": round(sorted(lat)[int(len(lat) * 0.9) - 1], 1),
                            "min": round(min(lat), 1), "max": round(max(lat), 1)}
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = path.parent / f"results-{stamp}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1))
    for t in report["tasks"]:
        print(f"{t['name']}: {t['correct']}/{t['n']}  ({t['elapsed_ms']}ms total)")
        for r in t["rows"]:
            if not r["correct"] or r.get("uncertain"):
                print(f"   label={r['label']} got={r.get('answer', r.get('error'))} conf={r.get('confidence')} "
                      f"unc={r.get('uncertain')} | {r['item'][:70]}")
    print("overall", report["overall"])
    print("latency", report["latency_ms"])
    print("saved", out)


if __name__ == "__main__":
    try:
        asyncio.run(main(Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).with_name("samples.json"))))
    except httpx.ConnectError:
        print(core.UNREACHABLE)
        sys.exit(1)
