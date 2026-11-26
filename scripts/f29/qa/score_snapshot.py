import argparse
import json
import sys

from app.core.f29 import constants
from app.core.f29.score.calculator import LOC_SP_THAT, HealthScoreCalculator
from scripts.f29.qa.memory_store import _FakeDB


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    fake = _FakeDB()
    constants.store_db = lambda: fake
    calc = HealthScoreCalculator()
    query = {**LOC_SP_THAT, "images.0": {"$exists": True}}
    ids = [str(p["_id"]) for p in calc.live_db["products"].find(query, {"_id": 1}).sort("_id", 1).limit(args.n)]
    out = {}
    for pid in ids:
        result = calc.calculate(pid, image_budget=60.0)
        out[pid] = {k: v for k, v in result.items() if k != "computed_at"}
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1, sort_keys=True, default=str)
    print({pid: r["score"] for pid, r in out.items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
