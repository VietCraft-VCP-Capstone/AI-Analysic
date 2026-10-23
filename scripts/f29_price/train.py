import json
import sys
from pathlib import Path

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline

from scripts.f29_price import data

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "app/core/f29"
TESTS = ("tiki23_test", "tiki26_test")
TRAINED_ON = ["tiki23", "tiki26"]


def text(df):
    return (df["group"] + " " + df["title"]).tolist()


def build():
    return make_pipeline(
        TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=3, max_features=50000),
        Ridge(alpha=1.0),
    )


def predict(model, df):
    return np.exp(model.predict(text(df)))


def residual_quantiles(model, val):
    resid = np.log(val["price"].to_numpy(float)) - model.predict(text(val))
    return float(np.quantile(resid, 0.25)), float(np.quantile(resid, 0.75))


def group_median(train):
    med = {str(g): float(p) for g, p in train.groupby("group")["price"].median().items()}
    return med | {"all": float(train["price"].median())}


def mdape(y, pred):
    return float(np.median(np.abs(y - pred) / y))


def evaluate(model, q, df, gm):
    y = df["price"].to_numpy(float)
    pred = predict(model, df)
    base = df["group"].map(gm).fillna(gm["all"]).to_numpy(float)
    lo, hi = pred * np.exp(q[0]), pred * np.exp(q[1])
    return {
        "n": int(len(df)),
        "mdape_model": mdape(y, pred),
        "mdape_group": mdape(y, base),
        "in_range": float(np.mean((y >= lo) & (y <= hi))),
    }


def gate(metrics):
    return all(metrics[t]["mdape_model"] <= 0.9 * metrics[t]["mdape_group"] for t in TESTS)


def _pct(x):
    return f"{100 * x:.1f}%".replace(".", ",")


def _num(x):
    return f"{x:.3f}".replace(".", ",")


def markdown(metrics):
    rows = [
        f"| {name} | {m['n']} | {_num(m['mdape_model'])} | {_num(m['mdape_group'])} | {_pct(m['in_range'])} |"
        for name, m in metrics.items()
    ]
    head = [
        "| Tập kiểm tra | Số mẫu | MdAPE mô hình | MdAPE trung vị nhóm | Giá thật nằm trong khoảng |",
        "|---|---:|---:|---:|---:|",
    ]
    return "\n".join(["## 7. Mô hình gợi ý giá", *head, *rows])


def write(model, q, gm, metrics):
    OUT.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, OUT / "price_model.joblib")
    body = {
        "version": "price-1.0",
        "q25": q[0],
        "q75": q[1],
        "group_median": gm,
        "metrics": metrics,
        "trained_on": TRAINED_ON,
    }
    (OUT / "price_model.json").write_text(json.dumps(body, ensure_ascii=False, indent=1), encoding="utf-8")


def main():
    splits = data.load()
    train = splits["train"]
    model = build().fit(text(train), np.log(train["price"].to_numpy(float)))
    q = residual_quantiles(model, splits["val"])
    gm = group_median(train)
    metrics = {t: evaluate(model, q, splits[t], gm) for t in TESTS}
    print(markdown(metrics))
    if not gate(metrics):
        print("Không đạt cổng: mô hình phải có MdAPE ≤ 0,9 × trung vị nhóm trên cả hai tập kiểm tra.", file=sys.stderr)
        sys.exit(2)
    write(model, q, gm, metrics)


if __name__ == "__main__":
    main()
