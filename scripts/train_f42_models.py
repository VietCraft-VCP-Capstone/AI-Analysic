"""Script huấn luyện các mô hình Machine Learning cho F42 Smart Suggestion.

Mô hình 1: Phân loại danh mục / ngành hàng (Text Classifier: TF-IDF + SGDClassifier log_loss)
Mô hình 2: Định giá phân vị thông minh P25 - P50 - P75 (Quantile Regression: HistGradientBoostingRegressor)
Mô hình 3: Khai phá cụm từ n-gram Lift từ nhóm sản phẩm bán chạy nhất (Top 25 Selling Lift)
"""

import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.decomposition import TruncatedSVD
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import SGDClassifier
from sklearn.metrics import accuracy_score, classification_report, f1_score

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    getattr(sys.stdout, "reconfigure")(encoding="utf-8")

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

MODEL_DIR = ROOT_DIR / "app" / "models" / "f42"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

TIKI23_PATH = ROOT_DIR.parent / "data-li" / "data-li" / "clean" / "tiki23.parquet"
TIKI26_PATH = ROOT_DIR.parent / "data-li" / "data-li" / "clean" / "tiki26.parquet"


def load_dataset():
    print("[1/5] Đang nạp dữ liệu từ data-li (tiki23 + tiki26)...")
    df23 = pd.read_parquet(TIKI23_PATH)
    df26 = pd.read_parquet(TIKI26_PATH)

    common_cols = ["group", "title", "price", "top25", "split"]
    df = pd.concat([df23[common_cols], df26[common_cols]], ignore_index=True)
    df = df.dropna(subset=["group", "title", "price"])
    df = df[df["price"] > 0]

    # Đảm bảo có train / val split
    if "split" not in df.columns or (df["split"] == "val").sum() == 0:
        np.random.seed(42)
        shuffled = np.random.permutation(len(df))
        val_size = int(len(df) * 0.20)
        df["split"] = "train"
        df.iloc[shuffled[:val_size], df.columns.get_loc("split")] = "val"

    train_df = df[df["split"] == "train"].copy()
    val_df = df[df["split"] == "val"].copy()

    print(f"      Tổng mẫu: {len(df):,} (Train: {len(train_df):,}, Val: {len(val_df):,})")
    print(f"      Các nhóm ngành: {sorted(df['group'].unique())}")
    return train_df, val_df, sorted(df["group"].unique())


def train_category_classifier(train_df, val_df):
    print("\n[2/5] Đang huấn luyện Mô hình Phân loại ngành hàng (Category Classifier)...")
    t0 = time.time()

    vec = TfidfVectorizer(ngram_range=(1, 2), max_features=10000, sublinear_tf=True)
    X_tr = vec.fit_transform(train_df["title"])
    X_val = vec.transform(val_df["title"])

    y_tr = train_df["group"].values
    y_val = val_df["group"].values

    clf = SGDClassifier(loss="log_loss", penalty="l2", alpha=1e-4, max_iter=1000, random_state=42)
    clf.fit(X_tr, y_tr)

    val_preds = clf.predict(X_val)
    acc = accuracy_score(y_val, val_preds)
    f1_macro = f1_score(y_val, val_preds, average="macro")
    elapsed = time.time() - t0

    print(f"      -> Hoàn thành trong {elapsed:.2f}s")
    print(f"      -> Accuracy trên tập Val: {acc * 100:.2f}% | Macro F1: {f1_macro:.4f}")

    model_artifact = {
        "vectorizer": vec,
        "classifier": clf,
        "classes": [str(c) for c in getattr(clf, "classes_", np.unique(y_tr))],
        "metrics": {"accuracy": float(acc), "f1_macro": float(f1_macro)}
    }
    joblib.dump(model_artifact, MODEL_DIR / "category_classifier.joblib")
    print(f"      -> Đã lưu artifact tại: {MODEL_DIR / 'category_classifier.joblib'}")

    return model_artifact


def train_quantile_price_regressors(train_df, val_df, groups):
    print("\n[3/5] Đang huấn luyện Mô hình Định giá hồi quy phân vị P25 - P50 - P75...")
    t0 = time.time()

    vec = TfidfVectorizer(ngram_range=(1, 2), max_features=5000, sublinear_tf=True)
    X_tr_tfidf = vec.fit_transform(train_df["title"])
    X_val_tfidf = vec.transform(val_df["title"])

    svd = TruncatedSVD(n_components=40, random_state=42)
    X_tr_svd = svd.fit_transform(X_tr_tfidf)
    X_val_svd = svd.transform(X_val_tfidf)

    group_to_idx = {g: i for i, g in enumerate(groups)}

    def make_group_onehot(df_split):
        mat = np.zeros((len(df_split), len(groups)))
        for i, g in enumerate(df_split["group"]):
            if g in group_to_idx:
                mat[i, group_to_idx[g]] = 1.0
        return mat

    X_tr_g = make_group_onehot(train_df)
    X_val_g = make_group_onehot(val_df)

    X_tr = np.hstack([X_tr_svd, X_tr_g])
    X_val = np.hstack([X_val_svd, X_val_g])

    y_tr = np.log(train_df["price"].values)
    y_val = val_df["price"].values

    models = {}
    val_preds = {}

    for q in [0.25, 0.50, 0.75]:
        print(f"      Huấn luyện quantile={q}...")
        m = HistGradientBoostingRegressor(loss="quantile", quantile=q, max_iter=120, random_state=42)
        m.fit(X_tr, y_tr)
        models[f"p{int(q*100)}"] = m
        val_preds[f"p{int(q*100)}"] = np.exp(m.predict(X_val))

    # Đảm bảo tính đơn điệu p25 <= p50 <= p75
    p25 = np.minimum(val_preds["p25"], val_preds["p50"])
    p50 = val_preds["p50"]
    p75 = np.maximum(val_preds["p75"], p50)

    mdape = float(np.median(np.abs(y_val - p50) / y_val) * 100)
    coverage = float(np.mean((y_val >= p25) & (y_val <= p75)) * 100)
    elapsed = time.time() - t0

    print(f"      -> Hoàn thành trong {elapsed:.2f}s")
    print(f"      -> Val MdAPE (Median Error): {mdape:.2f}% (Cũ: 174.5%)")
    print(f"      -> P25-P75 Coverage: {coverage:.2f}% (Mục tiêu ~50%, Cũ: 19.1%)")

    pricing_artifact = {
        "vectorizer": vec,
        "svd": svd,
        "group_to_idx": group_to_idx,
        "models": models,
        "metrics": {"mdape": mdape, "coverage": coverage}
    }
    joblib.dump(pricing_artifact, MODEL_DIR / "pricing_quantile_model.joblib")
    print(f"      -> Đã lưu artifact tại: {MODEL_DIR / 'pricing_quantile_model.joblib'}")

    return pricing_artifact


def extract_top_selling_lift(train_df, groups):
    print("\n[4/5] Đang khai phá cụm từ n-gram Lift từ nhóm sản phẩm Bán Chạy (Top 25)...")
    lift_by_group = {}

    for g in groups:
        gdf = train_df[train_df["group"] == g]
        if len(gdf) == 0:
            continue

        top_df = gdf[gdf["top25"] == 1]
        other_df = gdf[gdf["top25"] == 0]

        def get_word_freqs(df_sub):
            counter = Counter()
            for title in df_sub["title"]:
                words = [w.lower() for w in str(title).split() if len(w) >= 3]
                # 1-gram và 2-gram
                counter.update(words)
                if len(words) >= 2:
                    counter.update([f"{words[i]} {words[i+1]}" for i in range(len(words)-1)])
            return counter

        top_counts = get_word_freqs(top_df)
        all_counts = get_word_freqs(gdf)
        n_top = max(len(top_df), 1)
        n_all = max(len(gdf), 1)

        scores = []
        for word, cnt in top_counts.items():
            if cnt < 3:
                continue
            all_cnt = all_counts.get(word, cnt)
            p_top = cnt / n_top
            p_all = all_cnt / n_all
            lift = p_top / p_all
            scores.append({"keyword": word.title(), "lift": round(lift, 2), "freq": cnt})

        scores.sort(key=lambda x: (x["lift"], x["freq"]), reverse=True)
        lift_by_group[g] = scores[:25]
        print(f"      Nhóm {g:<12}: {len(scores[:25])} cụm từ hot (VD: {[s['keyword'] for s in scores[:3]]})")

    with open(MODEL_DIR / "top_selling_lift.json", "w", encoding="utf-8") as f:
        json.dump(lift_by_group, f, ensure_ascii=False, indent=2)

    print(f"      -> Đã lưu artifact tại: {MODEL_DIR / 'top_selling_lift.json'}")
    return lift_by_group


def save_summary_metrics(cat_metrics, price_metrics):
    print("\n[5/5] Tổng kết báo cáo chất lượng mô hình...")
    summary = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "category_classification": cat_metrics,
        "quantile_pricing": price_metrics,
    }
    with open(MODEL_DIR / "model_metrics.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 70)
    print(" BÁO CÁO KẾT QUẢ HUẤN LUYỆN MACHINE LEARNING F42")
    print("=" * 70)
    print(f"1. Phân loại danh mục: Accuracy = {cat_metrics['accuracy']*100:.2f}% | F1-macro = {cat_metrics['f1_macro']:.4f}")
    print(f"2. Định giá phân vị : MdAPE (Sai số trung vị) = {price_metrics['mdape']:.2f}% (Cũ: 174.5%)")
    print(f"                      Độ phủ thực tế [P25, P75] = {price_metrics['coverage']:.2f}% (Mục tiêu: ~50%)")
    print("=" * 70)


def main():
    train_df, val_df, groups = load_dataset()
    cat_artifact = train_category_classifier(train_df, val_df)
    price_artifact = train_quantile_price_regressors(train_df, val_df, groups)
    extract_top_selling_lift(train_df, groups)
    save_summary_metrics(cat_artifact["metrics"], price_artifact["metrics"])


if __name__ == "__main__":
    main()
