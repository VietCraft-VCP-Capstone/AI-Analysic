import json
import os
import random
import statistics
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from app.api.v1 import f29_health
from app.api.v1._live import db_live
from app.core.f29 import scheduler
from app.core.f29.score.calculator import HealthScoreCalculator
from scripts.f29.register.learn import ROOT

OUT = ROOT / "notes/f29/qa/perf.json"
SHOP = "6ad3c8198dcc4a925b5594a5"
BASE = "http://localhost:8081/api"
LIMIT_MS = 2000
THREADS, CALLS = 10, 20


def pct(xs, p):
    xs = sorted(xs)
    return xs[max(0, -(-len(xs) * p // 100) - 1)]


def stats(ms):
    return {"n": len(ms), "p50": round(statistics.median(ms), 1), "p95": round(pct(ms, 95), 1), "max": round(max(ms), 1)}


def has_score(d):
    score = d.get("score") if isinstance(d, dict) and "error" not in d else None
    return isinstance(score, (int, float)) and not isinstance(score, bool) and score == score


def is_ok(env):
    return isinstance(env, dict) and (env.get("meta") or {}).get("status") == "ok" and has_score(env.get("data"))


def timed(fn, *a):
    t = time.perf_counter()
    r = fn(*a)
    return (time.perf_counter() - t) * 1000, r


def section(res):
    out = stats([t for t, _ in res])
    out["errors"] = sum(1 for _, ok in res if not ok)
    return out


def hammer(fn, items):
    t = time.perf_counter()
    with ThreadPoolExecutor(THREADS) as ex:
        out = list(ex.map(fn, items))
    return out, (time.perf_counter() - t) * 1000


def call_http(req):
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status == 200 and is_ok(json.loads(r.read()))
    except Exception:
        return False


def http_part(shop_ids):
    email, pw = os.environ.get("T_EMAIL"), os.environ.get("T_PASS")
    if not email or not pw:
        return {"skipped": "T_EMAIL/T_PASS not set"}
    login = urllib.request.Request(f"{BASE}/auth/login", json.dumps({"email": email, "password": pw}).encode(), {"content-type": "application/json"})
    try:
        with urllib.request.urlopen(login, timeout=15) as r:
            token = json.load(r)["token"]
    except Exception as e:
        return {"skipped": f"backend login failed: {type(e).__name__}"}
    reqs = [urllib.request.Request(f"{BASE}/seller/analytics/listings/{i}/health", headers={"authorization": f"Bearer {token}"}) for i in shop_ids]
    for r in reqs:
        call_http(r)
    rng = random.Random(42)
    work = [rng.choice(reqs) for _ in range(THREADS * CALLS)]
    res, wall = hammer(lambda r: timed(call_http, r), work)
    return {**section(res), "wall_ms": round(wall)}


def ok_call(pid, shop):
    return timed(lambda: is_ok(f29_health.health_score(pid, shop)))


def cold_call(calc, pid):
    def run():
        r = calc.calculate(pid)
        good = has_score(r)
        if good:
            calc.save(r)
        return good
    return timed(run)


def main() -> int:
    prods = list(db_live()["products"].find(scheduler.LOC_SP_THAT, {"shop_id": 1}))
    pairs = [(str(p["_id"]), str(p["shop_id"])) for p in prods]
    seller = [i for i, s in pairs if s == SHOP]
    for pid, shop in pairs:
        f29_health.health_score(pid, shop)
    warm = section([ok_call(pid, shop) for pid, shop in pairs for _ in range(5)])
    calc = HealthScoreCalculator()
    cold = section([cold_call(calc, pid) for pid, _ in random.Random(42).sample(pairs, min(10, len(pairs)))])
    rng = random.Random(42)
    res, wall = hammer(lambda a: ok_call(*a), [rng.choice(pairs) for _ in range(THREADS * CALLS)])
    conc = {**section(res), "wall_ms": round(wall)}
    http = http_part(seller) if seller else {"skipped": "no seller products"}
    out = {"warm": warm, "cold": cold, "concurrent": conc, "http": http, "n_products": len(pairs), "measured_at": datetime.now(timezone.utc).isoformat()}
    errors = sum(x.get("errors", 0) for x in (warm, cold, conc, http))
    gated = [warm, conc] + ([] if "skipped" in http else [http])
    out["limit_ms"], out["failed"] = LIMIT_MS, errors > 0 or any(x["p95"] >= LIMIT_MS for x in gated)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2))
    print(f"warm p95={warm['p95']}ms cold p95={cold['p95']}ms concurrent p95={conc['p95']}ms http={http.get('p95', http.get('skipped'))} errors={errors} n={len(pairs)}")
    if "skipped" in http:
        print(f"HTTP SKIPPED: {http['skipped']}")
    return 1 if out["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
