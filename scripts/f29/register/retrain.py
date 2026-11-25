import argparse
import json
from collections import defaultdict
from datetime import date

import pandas as pd
from bson import ObjectId

from app.api.v1._live import db_live
from app.core.f29 import constants
from app.core.f29.score.scoring import COUNTED
from app.core.f29.score.calculator import HealthScoreCalculator
from scripts.f29.eval_kit import group_split
from scripts.f29.register import learn
from scripts.f29.register.learn import FACTORS, ROOT


BUDGET = 8.0
NEUTRAL = 0.5


def eligible(min_views: int) -> dict:
    tot = defaultdict(lambda: [0.0, 0.0])
    for m in db_live()["product_daily_metrics"].find({}, {"product_id": 1, "views": 1, "orders_count": 1}):
        t = tot[str(m["product_id"])]
        t[0] += m.get("views") or 0
        t[1] += m.get("orders_count") or 0
    return {pid: (v, o) for pid, (v, o) in tot.items() if v >= min_views}


def _shops(pids) -> dict:
    found = db_live()["products"].find({"_id": {"$in": [ObjectId(p) for p in pids]}}, {"shop_id": 1})
    return {str(p["_id"]): str(p.get("shop_id") or p["_id"]) for p in found}


def _value(f: dict | None) -> float:
    ok = f is not None and f["state"] in COUNTED and f["sub_score"] is not None
    return f["sub_score"] / 100 if ok else NEUTRAL


def collect(min_views: int) -> pd.DataFrame:
    pool = eligible(min_views)
    shops = _shops(pool)
    calc, rows = HealthScoreCalculator(), []
    for pid, (views, orders) in pool.items():
        r = calc.calculate(pid, image_budget=BUDGET)
        if r and "error" not in r:
            by_key = {f["key"]: f for f in r["factors"]}
            rows.append({"group": shops.get(pid, pid), "y": orders / views,
                         **{k: _value(by_key.get(k)) for k in FACTORS}})
    return pd.DataFrame(rows, columns=["group", "y", *FACTORS])


HISTORY = ROOT / "notes/f29/register/history.json"
MIN_LISTINGS = 200
MIN_VIEWS = 200
SOURCE = dict.fromkeys(FACTORS, "vietcraft")


def _log(entry: dict) -> None:
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    hist = json.loads(HISTORY.read_text("utf-8")) if HISTORY.exists() else []
    hist.append({"date": date.today().isoformat(), **entry})
    HISTORY.write_text(json.dumps(hist, ensure_ascii=False, indent=2) + "\n", "utf-8")


def _current() -> dict:
    return {k: v / 100 for k, v in json.loads(constants.WEIGHTS_PATH.read_text("utf-8"))["weights"].items()}


def _insufficient(n: int, min_listings: int) -> None:
    _log({"n": n, "status": "insufficient"})
    print(f"chưa đủ dữ liệu: {n}/{min_listings} tin")


def _compare(df, dry_run: bool) -> None:
    tr, _, te = group_split(df["group"].to_numpy(), seed=0)
    new = learn.fit(df.iloc[tr][FACTORS], df.iloc[tr]["y"])
    test = df.iloc[te]
    y, g, X = test["y"].to_numpy(), test["group"].to_numpy(), test[FACTORS]
    s_new, s_cur = learn.score(X, new), learn.score(X, _current())
    ci = learn.r_delta(y, s_new, s_cur, g)["ci95"]
    r_new, r_cur = learn.r_report(y, s_new, g)["r"], learn.r_report(y, s_cur, g)["r"]
    replace = ci[0] > 0
    written = replace and not dry_run
    if written:
        learn.write_weights(new, {"n": len(df), "r_test_vietcraft": r_new, "r_current": r_cur, "ci95": ci,
                                  "metrics": "notes/f29/register/history.json"}, source=SOURCE)
    _log({"n": len(df), "status": "replaced" if replace else "kept", "written": written,
          "r_new": r_new, "r_current": r_cur, "ci": ci})
    kept = "dry-run: sẽ thay trọng số" if replace else "giữ trọng số cũ"
    msg = "đã ghi trọng số mới (khởi động lại dịch vụ AI để dùng)" if written else kept
    print(f"{msg}: n={len(df)}, r mới={r_new}, r cũ={r_cur}, cận dưới CI={ci[0]}")


def run(min_listings: int, min_views: int, dry_run: bool) -> None:
    pool = len(eligible(min_views))
    if pool < min_listings:
        _insufficient(pool, min_listings)
        return
    df = collect(min_views)
    if len(df) < min_listings:
        _insufficient(len(df), min_listings)
        return
    _compare(df, dry_run)


def main(argv=None) -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--min-listings", type=int, default=MIN_LISTINGS)
    p.add_argument("--min-views", type=int, default=MIN_VIEWS)
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args(argv)
    run(a.min_listings, a.min_views, a.dry_run)


if __name__ == "__main__":
    main()
