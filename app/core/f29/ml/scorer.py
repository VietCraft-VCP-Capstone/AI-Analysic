import json
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn

from app.core.f29.ml import features
from app.core.f29.ml.live_data import load_tables

DIR = Path(__file__).parent
MIN_PEERS = 5
MIN_GAIN = 0.005
MIN_LIFT = 0.005
MIN_OTHER_SHOPS = 3
COUNTS = {"photos", "description_length", "name_length"}
COMPARABLE = ["days_since_last", "log_sales_90d", "log_sales_180d", "log_reviews", "rating",
              "log_seller_sales", "log_seller_listings", "seller_rating"]
NO_SALES = "Sản phẩm chưa có đơn nào trong 180 ngày nên model chưa chấm được"
FEW_PEERS = "Sàn mới có {n} sản phẩm có đơn trong 180 ngày, cần ít nhất {k} sản phẩm để so sánh"


@lru_cache(maxsize=1)
def load_model():
    meta = json.loads((DIR / "listing_model.json").read_text())
    if meta["sklearn"] != sklearn.__version__:
        raise RuntimeError(f"Model F29 học bằng scikit-learn {meta['sklearn']}, đang chạy {sklearn.__version__}")
    return joblib.load(DIR / "listing_model.joblib"), meta


@lru_cache(maxsize=1)
def _tables_at(hour):
    return load_tables(hour)


def _num(v, digits=1):
    return None if pd.isna(v) else round(float(v), digits)


def _human(feature, v):
    if feature == "log_price_rel":
        return round(float(np.expm1(v)) * 100)
    if feature in COUNTS:
        return round(float(v))
    return _num(v)


def _peers(df, row):
    same = df[df["category"] == row["category"]]
    if len(same) >= MIN_PEERS:
        return same, {"type": "category", "name": row["category"], "size": len(same)}
    return df, {"type": "platform", "name": None, "size": len(df)}


def _options(feature, current, peers, meta):
    vals = peers[feature].dropna()
    qs = meta["quantiles"][feature] + (vals.quantile([0.25, 0.5, 0.75]).tolist() if len(vals) >= MIN_PEERS else [])
    sign = features.ACTIONABLE[feature]
    return [] if pd.isna(current) else sorted({q for q in qs if (q - current) * sign > 0})


def _proven(meta):
    return [f for f in features.ACTIONABLE
            if any(f in cols and meta["group_lift"].get(g, 0) >= MIN_LIFT for g, cols in meta["groups"].items())]


def _advice(clf, x, base, peers, meta):
    out = []
    for f in _proven(meta):
        options = _options(f, x[f].iloc[0], peers, meta)
        if not options:
            continue
        trial = pd.concat([x] * len(options), ignore_index=True)
        trial[f] = options
        if f == "log_price_rel":
            trial["freight_ratio"] = x["freight_ratio"].iloc[0] * np.exp(x[f].iloc[0] - trial[f])
        prob = clf.predict_proba(trial)[:, 1]
        best = int(np.argmax(prob))
        if prob[best] - base >= MIN_GAIN:
            out.append({"feature": f, "current": _human(f, x[f].iloc[0]), "target": _human(f, options[best]),
                        "gain": round(float(prob[best] - base), 3)})
    return sorted(out, key=lambda a: -a["gain"])[:3]


def _compare(row, peers, meta):
    keys = [f for f in meta["importance"] if f in COMPARABLE][:4]
    others = peers.loc[peers["seller_id"] != row["seller_id"], "seller_id"].nunique()
    hide = 0 < others < MIN_OTHER_SHOPS
    return [{"feature": f, "value": _num(row[features.LOGS.get(f, f)]),
             "peer_median": None if hide else _num(peers[features.LOGS.get(f, f)].median())} for f in keys]


def _model_card(meta):
    base = meta["test_baselines"]
    return {"version": meta["model_version"], "trained_on": meta["trained_on"], "horizon_days": meta["horizon_days"],
            "test_auc": meta["test"]["roc_auc"], "test_auc_ci95": meta["test"]["auc_ci95"],
            "baseline_auc": {k: v["roc_auc"] for k, v in base.items()},
            "delta_vs_best_baseline": meta["delta_vs_best_baseline"], "group_lift": meta["group_lift"]}


def score_frame(df, product_id):
    clf, meta = load_model()
    cols = meta["features"]
    df = df.reset_index(drop=True)
    hit = df.index[df["product_id"] == product_id]
    if len(hit) == 0:
        return NO_SALES
    df["probability"] = clf.predict_proba(df[cols].astype(float))[:, 1]
    row = df.loc[hit[0]]
    peers, group = _peers(df, row)
    if group["size"] < MIN_PEERS:
        return FEW_PEERS.format(n=group["size"], k=MIN_PEERS)
    p = row["probability"]
    pct = (peers["probability"] < p).mean() + 0.5 * (peers["probability"] == p).mean()
    x = df.loc[[hit[0]], cols].astype(float).reset_index(drop=True)
    return {
        "product_id": product_id,
        "score": round(float(pct) * 100),
        "probability": round(float(p), 3),
        "peer_group": group,
        "advice": _advice(clf, x, float(p), peers, meta),
        "compare": _compare(row, peers, meta),
        "model": _model_card(meta),
    }


def score_listing(product_id, now=None):
    now = now or datetime.now(timezone.utc).replace(tzinfo=None, minute=0, second=0, microsecond=0)
    sales, products, rated = _tables_at(now)
    if sales.empty:
        return NO_SALES
    return score_frame(features.snapshot(sales, products, rated, now), product_id)
