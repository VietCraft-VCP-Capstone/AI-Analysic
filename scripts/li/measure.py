import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import ndcg_score, roc_auc_score

from scripts.f29_ml.evaluate import delta_ci, score_all

MIN_GROUP = 10


def sellers(df):
    solo = df["source"].astype(str) + "-row-" + df["listing_id"].astype(str)
    return df["seller"].astype("string").fillna(solo).astype(str).to_numpy()


def target(df):
    return (df["rank_target"] if "rank_target" in df else df["sold"]).astype(float).to_numpy()


def two_classes(df):
    return len(df) > 0 and 0 < df["top25"].sum() < len(df)


def rank_metrics(df, s):
    t, sp, nd = target(df), [], []
    for idx in df.groupby(["source", "group"], observed=True).indices.values():
        if len(idx) < MIN_GROUP or np.ptp(t[idx]) == 0 or np.ptp(s[idx]) == 0:
            continue
        sp.append(spearmanr(s[idx], t[idx]).statistic)
        rel = pd.Series(t[idx]).rank(pct=True).to_numpy()
        nd.append(ndcg_score([rel], [s[idx]], k=10))
    mean = lambda v: round(float(np.mean(v)), 3) if v else None
    return {"spearman": mean(sp), "ndcg10": mean(nd)}


def top_hit(y, s, frac=0.2):
    k = max(1, int(len(s) * frac))
    cut = np.sort(s)[::-1][k - 1]
    above, tied = s > cut, s == cut
    return round(float((y[above].sum() + (k - above.sum()) * y[tied].mean()) / k), 3)


def measure(df, s):
    if not two_classes(df):
        return None
    s = np.asarray(s, dtype=float)
    out = score_all(df["top25"].to_numpy(), s, df["group"].astype(str), sellers(df))
    out["top20_hit"] = top_hit(df["top25"].to_numpy(), s)
    out |= rank_metrics(df, s) | {"n": int(len(df)), "n_sellers": int(len(set(sellers(df))))}
    return {k: None if isinstance(v, float) and np.isnan(v) else v for k, v in out.items()}


def auc(df, s):
    return float(roc_auc_score(df["top25"].to_numpy(), s))


def paired(df, a, b):
    if not two_classes(df):
        return None, None
    y = df["top25"].to_numpy()
    return round(auc(df, a) - auc(df, b), 4), delta_ci(y, a, b, sellers(df))
