import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.f29.scoring import bayes_shrunk_rating  # noqa: E402

BASE = "/home/rio/Documents/CODE/nodejs/vietcraft/preparied-olist-data"
M_THU = (10, 20, 50)


def nap_review() -> pd.DataFrame:
    rev = pd.read_csv(f"{BASE}/olist_order_reviews_dataset.csv")
    items = pd.read_csv(f"{BASE}/olist_order_items_dataset.csv")

    # Chỉ đơn một sản phẩm để review gán đúng một product_id
    so_sp = items.groupby("order_id")["product_id"].nunique()
    don_mot_sp = so_sp[so_sp == 1].index
    tong_don = items["order_id"].nunique()
    print(f"tổng đơn trong order_items: {tong_don:,}")
    print(f"đơn 1 sản phẩm: {len(don_mot_sp):,} ({len(don_mot_sp) / tong_don * 100:.1f}%)")

    sp_cua_don = (items[items["order_id"].isin(don_mot_sp)]
                  .drop_duplicates("order_id")[["order_id", "product_id"]])
    gan = rev.merge(sp_cua_don, on="order_id", how="inner").dropna(subset=["review_score", "product_id"])
    gan["review_creation_date"] = pd.to_datetime(gan["review_creation_date"])
    print(f"review gán được: {len(gan):,} cho {gan['product_id'].nunique():,} sản phẩm")
    return gan


def chia_doi(gan: pd.DataFrame, toi_thieu: int) -> pd.DataFrame:
    dong = []
    for pid, g in gan.groupby("product_id"):
        if len(g) < toi_thieu:
            continue
        sao = g.sort_values("review_creation_date")["review_score"].to_numpy()
        giua = len(sao) // 2
        dong.append({"product_id": pid,
                     "n1": giua, "sum1": float(sao[:giua].sum()),
                     "n2": len(sao) - giua, "sum2": float(sao[giua:].sum())})
    return pd.DataFrame(dong)


def do_on_dinh(df: pd.DataFrame, C: float, m: int) -> dict:
    s1 = np.array([bayes_shrunk_rating(s, n, C, m) for s, n in zip(df["sum1"], df["n1"])])
    s2 = np.array([bayes_shrunk_rating(s, n, C, m) for s, n in zip(df["sum2"], df["n2"])])
    return {"m": m,
            "pearson": np.corrcoef(s1, s2)[0, 1],
            "mae": np.mean(np.abs(s1 - s2)),
            "rmse": np.sqrt(np.mean((s1 - s2) ** 2)),
            "var_half1": s1.var(ddof=1)}


def main():
    gan = nap_review()
    C = gan["review_score"].mean()
    print(f"C (trung bình toàn sàn) = {C:.3f}")

    for toi_thieu, nhan in ((4, "ngưỡng chính >=4 review"), (2, "ngưỡng phụ >=2 review")):
        df = chia_doi(gan, toi_thieu)
        print(f"\n[{nhan}] số sản phẩm: {len(df):,}")
        bang = pd.DataFrame([do_on_dinh(df, C, m) for m in M_THU])
        print(bang.to_string(index=False, float_format=lambda x: f"{x:.4f}"))


if __name__ == "__main__":
    main()
