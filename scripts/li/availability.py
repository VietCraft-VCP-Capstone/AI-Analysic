import numpy as np
import pandas as pd

from app.core.listing_intel import features as F
from scripts.li.fit import FULL, predict

PROBE_ROWS = 200
IMPUTE_RULE = ("listing không có ảnh được điền các feature ảnh bằng vector của một ảnh train thật trong cùng nhóm, chọn "
               f"là ảnh làm điểm trung bình của model gộp thấp nhất khi thay vào {PROBE_ROWS} dòng train của nhóm (cột "
               "thị hiếu để trống như lúc phục vụ); chỉ dùng train")


def feature_availability(train) -> dict:
    return {str(g): {c: round(float(df[c].notna().mean()), 4) for c in F.FEATURE_COLS}
            for g, df in train.groupby("group", observed=True)}


def no_image(df, fill: dict):
    return df.assign(**fill, **dict.fromkeys(F.MARKET_COLS, np.nan))


def image_impute(train, fusion) -> dict:
    out = {}
    for g, df in train.groupby("group", observed=True):
        rows = df[df[F.IMAGE_COLS].notna().all(axis=1)]
        if rows.empty:
            continue
        probe = rows.sample(min(PROBE_ROWS, len(rows)), random_state=0)
        cand = rows[F.IMAGE_COLS].to_numpy(float)
        means = [predict(fusion, no_image(probe, dict(zip(F.IMAGE_COLS, v))), FULL).mean() for v in cand]
        out[str(g)] = {c: round(float(v), 6) for c, v in zip(F.IMAGE_COLS, cand[int(np.argmin(means))])}
    return out


def q10_fill(train) -> dict:
    out = {}
    for g, df in train.groupby("group", observed=True):
        q = df[F.IMAGE_COLS].quantile(0.1).dropna()
        if len(q):
            out[str(g)] = q.round(6).to_dict()
    return out


def impute_check(table, fusion, chosen) -> dict:
    fills = {"q10": q10_fill(table[table["split"] == "train"]), "chosen": chosen}
    out = {}
    for split in ("val", "test"):
        d = table[(table["source"] == "tiki26") & (table["split"] == split) & table["emb_pca_0"].notna()]
        p0 = predict(fusion, d, FULL)
        out[split] = {"n": int(len(d))}
        for k, fill in fills.items():
            p1 = pd.concat([pd.Series(predict(fusion, no_image(x, fill[str(g)]), FULL), x.index)
                            for g, x in d.groupby("group", observed=True)]).loc[d.index]
            out[split][k] = round(float((p1.to_numpy() > p0).mean()), 3)
    return out


def feature_constants(train) -> dict:
    out = {}
    for g, df in train.groupby("group", observed=True):
        one = {c: float(df[c].iloc[0]) for c in F.FEATURE_COLS if df[c].notna().all() and df[c].nunique() == 1}
        if one:
            out[str(g)] = one
    return out
