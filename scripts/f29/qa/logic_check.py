import json
import sys
import random
import time

from app.api.v1._live import db_live
from app.core.f29 import scheduler
from app.core.f29.score.calculator import HealthScoreCalculator
from scripts.f29.qa import logic_edge, logic_preview, logic_rules
from scripts.f29.register.learn import ROOT

OUT = ROOT / "notes/f29/qa/logic_check.json"
N_PREVIEW = 10


def result_of(calc, pid: str) -> dict:
    result = calc.stored_result(pid)
    if result is None:
        result = calc.calculate(pid)
        if not result or "error" in result:
            raise RuntimeError(f"no result: {result}")
        calc.save(result)
    return result


def guarded(bucket: list, pid: str, fn) -> None:
    try:
        bucket += [{"product_id": pid, "problem": p} for p in fn()]
    except Exception as e:
        bucket.append({"product_id": pid, "problem": f"exception {type(e).__name__}: {e}"})


def main() -> int:
    calc = HealthScoreCalculator()
    ids = sorted(str(p["_id"]) for p in db_live()["products"].find(scheduler.LOC_SP_THAT, {"_id": 1}))
    recompute, gain, preview, edge, results = [], [], [], {}, {}
    for i, pid in enumerate(ids):
        print(f"{i}/{len(ids)}", file=sys.stderr, flush=True)
        def one(pid=pid):
            results[pid] = result_of(calc, pid)
            logic_edge.check(calc, results[pid], edge)
            return []
        guarded(recompute, pid, one)
        if pid in results:
            guarded(recompute, pid, lambda: logic_rules.recompute(results[pid]))
            guarded(gain, pid, lambda: logic_rules.gains(results[pid]))
    pool = [p for p in ids if p in results and logic_preview.eligible(results[p])]
    sample = random.Random(0).sample(pool, min(N_PREVIEW, len(pool)))
    start = time.time()
    for pid in sample:
        print(f"preview {pid}", file=sys.stderr, flush=True)
        guarded(preview, pid, lambda: logic_preview.violations(calc, results[pid]))
    total = len(recompute) + len(gain) + len(preview) + sum(len(c["violations"]) for c in edge.values())
    report = {"n": len(ids), "recompute_violations": recompute, "gain_violations": gain,
              "preview_violations": preview, "preview_sample": sample, "preview_seconds": round(time.time() - start, 1),
              "edge_cases": edge, "violations_total": total}
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1), "utf-8")
    print(json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in report.items() if k != "edge_cases"}))
    print({c: v["n"] for c, v in edge.items()})
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main())
