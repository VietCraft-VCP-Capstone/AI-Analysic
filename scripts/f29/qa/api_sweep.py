import json
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from bson import ObjectId
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder

from app.api.v1 import f29_health
from app.api.v1._live import db_live
from app.core.f29 import constants
from app.core.f29 import scheduler
from scripts.f29.qa.invariants import check_health, check_preview

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "notes/f29/qa/api_sweep.json"
PREVIEWS = [{}, {"n_images": 0}, {"description_length": 0}, {"n_tags": 0}, {"price": 150000}]
WORKERS = 8


class Sweep:
    def __init__(self):
        self.violations, self.errors, self.times, self.calls = [], Counter(), {}, 0

    def flag(self, pid, endpoint, problem):
        self.violations.append({"product_id": pid, "endpoint": endpoint, "problem": problem})
        print(f"VIOLATION {pid} [{endpoint}] {problem}", flush=True)

    def call(self, pid, endpoint, fn, expect_status=None):
        self.calls += 1
        start = time.perf_counter()
        try:
            res, status = fn(), None
        except HTTPException as e:
            res, status = None, e.status_code
        except Exception as e:
            self.errors[type(e).__name__] += 1
            self.flag(pid, endpoint, f"unexpected {type(e).__name__}: {str(e)[:200]}")
            return None
        self.times.setdefault(endpoint.split(" {")[0], []).append(time.perf_counter() - start)
        if status != expect_status:
            self.flag(pid, endpoint, f"expected HTTP {expect_status or 200}, got {status or 200}")
        if res is not None:
            self.check(pid, endpoint, lambda: json.dumps(jsonable_encoder(res), allow_nan=False) and [])
        return res

    def check(self, pid, endpoint, fn):
        try:
            msgs = fn()
        except Exception as e:
            msgs = [f"check crashed: {type(e).__name__}: {str(e)[:200]}"]
        for m in msgs:
            self.flag(pid, endpoint, m)

    def data(self, pid, endpoint, res):
        if res is None:
            return None
        meta = res.get("meta", {})
        if meta.get("status") != "ok" or not res.get("data"):
            self.flag(pid, endpoint, f"non-ok envelope: {meta.get('status')} {meta.get('reason')}")
            return None
        return res["data"]


def sweep_product(s: Sweep, pid: str, shop: str, weights: dict, other: str):
    d = s.data(pid, "health", s.call(pid, "health", lambda: f29_health.health_score(pid, shop)))
    if d:
        s.check(pid, "health", lambda: check_health(d, weights))
    for body in PREVIEWS:
        name = f"preview {body or '{}'}"
        res = s.call(pid, name, lambda: f29_health.health_preview(pid, f29_health.HealthPreviewBody(**body), shop))
        p = s.data(pid, name, res)
        if p:
            s.check(pid, name, lambda: check_preview(p, not body))
            if d and not body:
                s.check(pid, name, lambda: [f"current_score {p['current_score']} != GET score {d['score']}"]
                        if abs(p["current_score"] - d["score"]) > 0.11 else [])
    s.call(pid, "health other shop", lambda: f29_health.health_score(pid, other), 403)


def write_report(s: Sweep, n_products: int, crashed: str = "") -> dict:
    flat = [x for v in s.times.values() for x in v] or [0.0]
    stat = lambda v: {"p50": float(np.percentile(v, 50)), "p95": float(np.percentile(v, 95)), "max": float(max(v))}
    report = {"n_products": n_products, "n_calls": s.calls, "ok": not s.violations and not crashed,
              "violations": s.violations, "timing": {**stat(flat), "by_endpoint": {k: stat(v) for k, v in s.times.items()}},
              "errors_by_type": dict(s.errors), "crashed": crashed}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1))
    return report


def main() -> int:
    s, prods, crashed = Sweep(), [], ""
    try:
        weights = constants.load()["weights"]
        prods = list(db_live()["products"].find(scheduler.LOC_SP_THAT, {"shop_id": 1}))
        shops = sorted({str(p["shop_id"]) for p in prods})

        def one(item):
            n, p = item
            pid, shop = str(p["_id"]), str(p["shop_id"])
            try:
                sweep_product(s, pid, shop, weights, next(x for x in shops if x != shop))
            except Exception as e:
                s.flag(pid, "sweep", f"crashed: {type(e).__name__}: {str(e)[:200]}")
            print(f"{n}/{len(prods)} {pid} violations={len(s.violations)}", flush=True)

        with ThreadPoolExecutor(WORKERS) as pool:
            list(pool.map(one, enumerate(prods, 1)))
        for bad in ("abc", str(ObjectId())):
            s.call(bad, "health bad id", lambda: f29_health.health_score(bad, shops[0]), 404)
    except BaseException as e:
        crashed = f"{type(e).__name__}: {str(e)[:200]}"
        raise
    finally:
        report = write_report(s, len(prods), crashed)
        print(json.dumps({k: v for k, v in report.items() if k != "violations"}), f"violations={len(s.violations)}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
