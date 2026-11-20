import json
import math
from datetime import datetime, timezone
from pathlib import Path
from statistics import quantiles

import numpy as np
import pandas as pd

from app.core.f29.material import materials_of
from app.core.f29.price_peers import trim
from app.core.listing_intel.normalize import fold
from scripts.f29_price import data

OUT = Path(__file__).resolve().parents[2] / "app/core/f29/price_params.json"
SIZES = (5, 8, 10, 15, 20, 30, 40, 50, 80)
DRAWS = 2000
MAX_ERROR = 5.0
FULL_ERROR = 3.0
MIN_POOL = 200
SEED = 42


def _materials(df):
    return df["title"].map(lambda t: sorted(fold(m) for m in materials_of({"title": t})))


def residuals(df):
    logs = np.log(df["price"])
    return logs - logs.groupby(df["group"]).transform("median")


def material_factors(mats, resid):
    rows = pd.DataFrame([(m, r) for ms, r in zip(mats, resid) for m in ms], columns=["m", "r"])
    by = rows.groupby("m")["r"]
    n, mean = by.size(), by.mean()
    within = float(by.var().dropna().mean())
    between = max(float(mean.var() - (within / n).mean()), 1e-6)
    shrunk = mean * n / (n + within / between)
    return {m: round(math.exp(v), 3) for m, v in shrunk.items()}, n.to_dict(), round(within / between, 1)


def adjusted_logs(df, mats, factors):
    f = mats.map(lambda ms: max([factors[m] for m in ms if m in factors], default=1.0))
    return np.log(df["price"].to_numpy() / f.to_numpy())


def _deciles(logs):
    q = quantiles(logs, n=10, method="inclusive")
    return q[0], q[8]


def _true_pct(pool, value):
    return 100 * np.searchsorted(pool, value) / len(pool)


def stability(groups, logs, rng):
    pools = [np.sort(v) for v in (logs[groups == g] for g in np.unique(groups)) if len(v) >= MIN_POOL]
    table = {}
    for n in SIZES:
        errs = []
        for _ in range(DRAWS):
            pool = pools[rng.integers(len(pools))]
            lo, hi = _deciles(trim(sorted(rng.choice(pool, n, replace=False))))
            errs += [abs(_true_pct(pool, lo) - 10), abs(_true_pct(pool, hi) - 90)]
        table[n] = round(float(np.median(errs)), 1)
    return table


def first_size(table, tol):
    return next((n for n, err in table.items() if err <= tol), SIZES[-1])


def main():
    df = data.load()["train"].reset_index(drop=True)
    mats = _materials(df)
    factors, counts, shrink = material_factors(mats, residuals(df))
    table = stability(df["group"].to_numpy(), adjusted_logs(df, mats, factors), np.random.default_rng(SEED))
    payload = {
        "materials": factors,
        "material_counts": counts,
        "shrink_k": shrink,
        "min_peers": first_size(table, MAX_ERROR),
        "full_n": first_size(table, FULL_ERROR),
        "stability": {"max_error": MAX_ERROR, "full_error": FULL_ERROR, "median_error_by_n": table},
        "trained_on": {"source": data.SOURCES, "split": "train", "rows": len(df),
                       "with_material": int((mats.map(len) > 0).sum())},
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: payload[k] for k in ("min_peers", "full_n", "shrink_k", "stability")}, ensure_ascii=False))
    print(sorted(factors.items(), key=lambda kv: kv[1]))


if __name__ == "__main__":
    main()
