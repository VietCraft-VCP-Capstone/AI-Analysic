import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.metrics import roc_auc_score

from app.core.f29 import constants
from app.core.f29.score.scoring import pct_within
from scripts.f29.eval_kit import delta_ci, group_split, score_all


ROOT = Path(__file__).resolve().parents[4]
SIM = ROOT / "agent-skills/ai-data-train-prod/register/s0"
TIKI = ROOT / "agent-skills/ai-data-train-prod/data-li/features/table.parquet"
MIN_VIEWS = 200
TEST_N = 500
FACTORS = ["image", "description", "tags", "review", "price"]
TIKI_FACTORS = ["image", "description", "price"]


def synthetic(path=SIM) -> pd.DataFrame:
    lst = pd.read_csv(path / "listings.csv")
    met = pd.read_csv(path / "listing_daily_metrics.csv", usecols=["listing_id", "views", "orders"])
    df = (lst.merge(met.groupby("listing_id")[["views", "orders"]].sum().reset_index(), on="listing_id")
             .merge(pd.read_csv(path / "gt_listing_quality.csv"), on="listing_id"))
    df = df[df["views"] >= MIN_VIEWS].reset_index(drop=True)
    return pd.DataFrame({
        "group": df["shop_id"], "y": df["orders"] / df["views"], "q": df["latent_quality"],
        "image": pct_within(df["n_images"], df["category"]),
        "description": pct_within(df["desc_length"], df["category"]),
        "tags": pct_within(df["n_tags"], df["category"]),
        "review": pct_within(df["avg_rating"], df["category"]),
        "price": 1 - pct_within(df["price"], df["product_type"]),
    })


def split_synthetic(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    tr, va, te = group_split(df["group"].to_numpy(), seed=0)
    te = np.random.default_rng(0).choice(te, size=min(TEST_N, len(te)), replace=False)
    return tr, va, np.sort(te)


def tiki(path=TIKI) -> pd.DataFrame:
    cols = ["seller", "group", "split", "top25", "n_images", "desc_words", "price_rel"]
    t = pd.read_parquet(path, columns=cols).dropna().reset_index(drop=True)
    return pd.DataFrame({
        "group": t["seller"], "category": t["group"], "split": t["split"], "y": t["top25"].astype(int),
        "image": pct_within(t["n_images"], t["group"]),
        "description": pct_within(t["desc_words"], t["group"]),
        "price": 1 - pct_within(t["price_rel"], t["group"]),
    })


N_BOOT = 1000


def _boot(groups, n=N_BOOT, seed=0):
    _, inv = np.unique(np.asarray(groups, dtype=str), return_inverse=True)
    members = [np.flatnonzero(inv == k) for k in range(inv.max() + 1)]
    rng = np.random.default_rng(seed)
    for _ in range(n):
        yield np.concatenate([members[j] for j in rng.integers(0, len(members), len(members))])


def _r(y, s) -> float:
    return float(np.corrcoef(y, s)[0, 1])


def _ci(vals) -> list:
    return [round(float(v), 3) for v in np.percentile(vals, [2.5, 97.5])]


def r_report(y, s, groups) -> dict:
    return {"r": round(_r(y, s), 3), "ci95": _ci([_r(y[i], s[i]) for i in _boot(groups)])}


def r_delta(y, a, b, groups) -> dict:
    return {"diff": round(_r(y, a) - _r(y, b), 3), "ci95": _ci([_r(y[i], a[i]) - _r(y[i], b[i]) for i in _boot(groups)])}


def auc_report(y, s, cat, groups) -> dict:
    return score_all(y, s, cat, groups)


def auc_delta(y, a, b, groups) -> dict:
    return {"diff": round(float(roc_auc_score(y, a) - roc_auc_score(y, b)), 3), "ci95": delta_ci(y, a, b, groups)}


HAND = {"image": 30, "description": 30, "tags": 15, "review": 10, "price": 15}
VERSION = "health-5.0"


def fit(X: pd.DataFrame, y) -> dict:
    coef = np.clip(Ridge(alpha=1.0, positive=True).fit(X, y).coef_, 0, None)
    total = coef.sum()
    return {c: float(v / total) if total > 0 else 0.0 for c, v in zip(X.columns, coef)}


def compose(sim_w: dict, tiki_w: dict) -> dict:
    base = tiki_w if sum(tiki_w.values()) > 0 else {k: sim_w[k] for k in TIKI_FACTORS}
    rest, total = 1 - sim_w["tags"] - sim_w["review"], sum(base.values())
    return {"tags": sim_w["tags"], "review": sim_w["review"], **{k: rest * base[k] / total for k in TIKI_FACTORS}}


def score(X: pd.DataFrame, w: dict) -> np.ndarray:
    cols = [c for c in FACTORS if c in X.columns and c in w]
    v = np.array([w[c] for c in cols], dtype=float)
    return X[cols].to_numpy() @ v / v.sum() * 100


def percents(w: dict) -> dict:
    p = {k: round(w[k] * 100, 1) for k in FACTORS}
    top = max(p, key=lambda k: p[k])
    p[top] = round(100 - sum(v for k, v in p.items() if k != top), 1)
    return p


def write_weights(w: dict, summary: dict, source: dict | None = None, version: str = VERSION,
                  protocol: str = "notes/f29/PROTOCOL.md mục 8") -> dict:
    data = json.loads(constants.WEIGHTS_PATH.read_text("utf-8"))
    data.update(model_version=version, weights=percents(w), learned={
        "date": date.today().isoformat(),
        "source": source or {"image": "tiki", "description": "tiki", "price": "tiki", "tags": "synthetic", "review": "synthetic"},
        "protocol": protocol, "metrics": "notes/f29/register/metrics.json", **summary})
    constants.WEIGHTS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", "utf-8")
    return data
