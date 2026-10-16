import numpy as np
import pandas as pd
from scipy.optimize import nnls
from scipy.stats import pearsonr, ttest_rel, wilcoxon

from f29_olist_axes import OlistAxes, T
from app.core.f29.constants import WEIGHTS

W_RATING_HAND = WEIGHTS["rating"]
W_CONTENT_HAND = WEIGHTS["content"]
W_SHARED = W_RATING_HAND + W_CONTENT_HAND   # 0.45
W_MIN_AXIS = 0.05
N_SPLITS = 200
TEST_FRACTION = 0.30
RANDOM_SEED = 42


def build_dataset():
    ax = OlistAxes()
    pre_products = set(ax.pre["product_id"].unique())
    post_products = set(ax.post["product_id"].unique())
    # sort: set của Python đổi thứ tự theo PYTHONHASHSEED, làm chia train/test không lặp lại được.
    both = sorted(pre_products & post_products)
    print(f"[dữ liệu] bán trước T={T.date()}: {len(pre_products):,} · sau T: {len(post_products):,} "
          f"· cả 2 phía: {len(both):,} (kỳ vọng 4.909)")

    y = ax.sales_after_t.reindex(both).fillna(0.0)
    rows = [{"product_id": pid, "rating": ax.rating(pid), "content": ax.content(pid), "y": y[pid]}
            for pid in both if pid in ax.prod.index]
    return pd.DataFrame(rows)


def fit_nnls(X, y):
    """NNLS -> (b_rating, b_content) không âm, rồi quy về tỉ lệ * 0.45, kẹp [0.05, 0.40]."""
    b, _resid = nnls(X, y)
    b_rating, b_content = b[0], b[1]
    if b_rating + b_content <= 0:
        return W_RATING_HAND, W_CONTENT_HAND   # thoái hoá -> giữ gán tay
    ratio_rating = b_rating / (b_rating + b_content)
    w_rating = W_SHARED * ratio_rating
    w_rating = min(max(w_rating, W_MIN_AXIS), W_SHARED - W_MIN_AXIS)
    w_content = W_SHARED - w_rating
    return w_rating, w_content


def main():
    df = build_dataset()
    both_axes = df.dropna(subset=["rating", "content"]).reset_index(drop=True)
    print(f"[dữ liệu] sản phẩm đủ CẢ 2 trục (rating trước T có n>=1 và content không n/a): "
          f"{len(both_axes):,} / {len(df):,}")

    X = both_axes[["rating", "content"]].to_numpy(dtype=float)
    y = both_axes["y"].to_numpy(dtype=float)

    rng = np.random.default_rng(RANDOM_SEED)
    n = len(both_axes)
    learned_ws, pear_learned, pear_hand = [], [], []

    for _ in range(N_SPLITS):
        idx = rng.permutation(n)
        cut = int(n * (1 - TEST_FRACTION))
        train_idx, test_idx = idx[:cut], idx[cut:]
        X_train, y_train = X[train_idx], y[train_idx]
        X_test, y_test = X[test_idx], y[test_idx]

        w_rating, w_content = fit_nnls(X_train, y_train)
        learned_ws.append(w_rating)

        score_learned_test = w_rating * X_test[:, 0] + w_content * X_test[:, 1]
        score_hand_test = W_RATING_HAND * X_test[:, 0] + W_CONTENT_HAND * X_test[:, 1]

        pear_learned.append(pearsonr(score_learned_test, y_test)[0])
        pear_hand.append(pearsonr(score_hand_test, y_test)[0])

    learned_ws = np.array(learned_ws)
    pear_learned = np.array(pear_learned)
    pear_hand = np.array(pear_hand)

    print(f"\n[{N_SPLITS} lần chia ngẫu nhiên 70/30]")
    print(f"w_rating học được: trung bình={learned_ws.mean():.4f}  std={learned_ws.std():.4f}  "
          f"min={learned_ws.min():.4f}  max={learned_ws.max():.4f}")
    print(f"w_content học được: trung bình={W_SHARED - learned_ws.mean():.4f}")
    print(f"Pearson (test) — bộ HỌC ĐƯỢC: trung bình={pear_learned.mean():.4f}  std={pear_learned.std():.4f}")
    print(f"Pearson (test) — bộ GÁN TAY : trung bình={pear_hand.mean():.4f}  std={pear_hand.std():.4f}")
    print(f"Số lần bộ học được thắng bộ gán tay: {(pear_learned > pear_hand).sum()}/{N_SPLITS}")

    diff = pear_learned - pear_hand
    t_stat, t_p = ttest_rel(pear_learned, pear_hand)
    try:
        w_stat, w_p = wilcoxon(pear_learned, pear_hand)
    except ValueError:
        w_stat, w_p = float("nan"), float("nan")
    print(f"Chênh lệch Pearson (học-tay) từng cặp: trung bình={diff.mean():.4f}  std={diff.std():.4f}")
    print(f"Paired t-test: t={t_stat:.3f}  p={t_p:.4f}")
    print(f"Wilcoxon signed-rank: W={w_stat:.1f}  p={w_p:.4f}")

    # fit cuối cùng trên TOÀN BỘ tập đủ 2 trục, để báo cáo một bộ trọng số duy nhất
    w_rating_full, w_content_full = fit_nnls(X, y)
    score_full_learned = w_rating_full * X[:, 0] + w_content_full * X[:, 1]
    score_full_hand = W_RATING_HAND * X[:, 0] + W_CONTENT_HAND * X[:, 1]
    print(f"\n[fit trên toàn bộ {n:,} sản phẩm, để báo cáo 1 bộ số]")
    print(f"w_rating={w_rating_full:.4f}  w_content={w_content_full:.4f}")
    print(f"Pearson (toàn bộ, không phải test) — học được: {pearsonr(score_full_learned, y)[0]:.4f} "
          f"· gán tay: {pearsonr(score_full_hand, y)[0]:.4f}")

    return {
        "n_both_axes": n,
        "learned_ws": learned_ws,
        "pear_learned": pear_learned,
        "pear_hand": pear_hand,
        "w_rating_full": w_rating_full,
        "w_content_full": w_content_full,
    }


if __name__ == "__main__":
    main()
