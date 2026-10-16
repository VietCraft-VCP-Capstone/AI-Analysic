import json
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from scipy.stats import pearsonr, spearmanr

from f29_olist_axes import OlistAxes

HERE = Path(__file__).resolve().parent
DOCS = HERE.parent / "docs"
N_TOP = 500


def main():
    ax = OlistAxes()

    # Xếp theo số dòng order_items trước T (khớp "≥13 đơn mỗi sản phẩm" ở §6.1 kế hoạch).
    pre_counts = ax.pre.groupby("product_id").size().sort_values(ascending=False)
    top500 = pre_counts.head(N_TOP).index.tolist()
    print(f"[top {N_TOP}] số dòng order_items trước T, nhỏ nhất trong top: "
          f"{pre_counts.loc[top500].min()} (kỳ vọng >=13)")

    def score_row(pid):
        r, c = ax.rating(pid), ax.content(pid)
        return {"product_id": pid, "category": ax.category_of.get(pid),
                "rating_score": r, "content_score": c, "health_score": ax.health(r, c),
                "pre_T_order_rows": int(pre_counts.get(pid, 0)),
                "sales_after_T_normalized": float(ax.sales_after_t.get(pid, 0.0))}

    rows = [score_row(pid) for pid in top500]
    df = pd.DataFrame(rows)
    n_scored = df["health_score"].notna().sum()
    print(f"[điểm] {n_scored}/{len(df)} sản phẩm có điểm (còn lại thiếu cả 2 trục -> n/a)")

    scored = df.dropna(subset=["health_score"]).copy()
    x = scored["health_score"].to_numpy(dtype=float)
    y = scored["sales_after_T_normalized"].to_numpy(dtype=float)
    n = len(scored)

    pear_r, pear_p = pearsonr(x, y)
    spear_r, spear_p = spearmanr(x, y)
    print(f"\nPearson = {pear_r:.4f}  (p = {pear_p:.4g}, n = {n})")
    print(f"Spearman = {spear_r:.4f}  (p = {spear_p:.4g})")

    # --- §6.3: "Báo cáo thêm số trên toàn bộ sản phẩm có ≥1 đơn trước T" ---
    all_pre_products = sorted(ax.pre["product_id"].unique())
    rows_all = [score_row(pid) for pid in all_pre_products]
    df_all = pd.DataFrame(rows_all).dropna(subset=["health_score"])
    x_all = df_all["health_score"].to_numpy(dtype=float)
    y_all = df_all["sales_after_T_normalized"].to_numpy(dtype=float)
    pear_r_all, pear_p_all = pearsonr(x_all, y_all)
    spear_r_all, spear_p_all = spearmanr(x_all, y_all)
    print(f"\n[toàn bộ {len(all_pre_products):,} sản phẩm có >=1 đơn trước T, "
          f"{len(df_all):,} có điểm] Pearson = {pear_r_all:.4f} (p={pear_p_all:.4g}), "
          f"Spearman = {spear_r_all:.4f} (p={spear_p_all:.4g})")

    # --- biểu đồ phân tán ---
    fig, plt_ax = plt.subplots(figsize=(7, 5.5), dpi=150)
    plt_ax.scatter(x, y, s=18, alpha=0.55, color="#2563eb", edgecolors="none")
    plt_ax.set_xlabel("Điểm health-1.0 (chỉ 2 trục đo được trên Olist: đánh giá + nội dung)")
    plt_ax.set_ylabel("Doanh số sau T, chuẩn hoá theo tháng (BRL/tháng)")
    plt_ax.set_title(f"F29c — health-1.0 vs doanh số sau T, top {N_TOP} sản phẩm Olist bán chạy nhất trước T\n"
                 f"Pearson r={pear_r:.3f} (p={pear_p:.3g}, n={n}) · Spearman ρ={spear_r:.3f} (p={spear_p:.3g})")
    plt_ax.grid(True, alpha=0.25)
    fig.tight_layout()
    out_png = DOCS / "HEALTH_SCATTER_OLIST.png"
    fig.savefig(out_png)
    plt.close(fig)
    print(f"Đã lưu biểu đồ: {out_png}")

    # --- cập nhật RESULTS.json ---
    results_path = DOCS / "RESULTS.json"
    with open(results_path, "r", encoding="utf-8") as f:
        results = json.load(f)

    results["metrics"]["health_pearson"] = {
        "value": round(float(pear_r), 4),
        "threshold": 0.65,
        "passed": bool(pear_r >= 0.65),
        "source": "olist_real",
        "p_value": float(pear_p),
        "n": int(n),
        "spearman": round(float(spear_r), 4),
        "spearman_p_value": float(spear_p),
        "scope": f"top {N_TOP} sản phẩm Olist bán chạy nhất trước T=2018-01-01, "
                 "điểm tính bằng chính engine health-1.0 (app/core/f29/scoring.py) "
                 "trên 2/5 trục (đánh giá + nội dung ảnh/mô tả; Olist không có tag, "
                 "event, tồn kho, độ mới), so với doanh số sau T (cắt 2018-08-31), "
                 "chuẩn hoá theo cửa sổ 7,95 tháng",
        "explanation": "Chưa đạt 0,65 vì: (1) trên Olist chỉ đo được 2/5 trục (đánh giá, "
                       "nội dung) — thiếu trục chuyển đổi (nặng nhất, 0,30), tồn kho, độ mới; "
                       "(2) đo so với doanh số sau T chứ không phải tỷ lệ mua như SRS, vì Olist "
                       "không có lượt xem; (3) Olist là sàn đa ngành hàng Brazil, khác thị "
                       "trường thủ công VietCraft. Công thức không được chỉnh để làm đẹp số. "
                       "Sẽ đo lại trên dữ liệu live (đủ 5 trục, so với tỷ lệ mua) ở giai đoạn S2.",
        "caveat": "Cổng ra chỉ cần CÓ SỐ THẬT (D-theo §2 bản đăng ký); đạt ngưỡng "
                  "0,65 không bắt buộc. Olist đa ngành hàng Brazil, không phải "
                  "VietCraft — xem LIMITATIONS.md. Pearson đo trên Olist chỉ phản "
                  "ánh 2 trục, không đại diện đầy đủ 5 trục của health-1.0 khi có "
                  "event thật trên live.",
        "plot": "docs/HEALTH_SCATTER_OLIST.png",
        "detail": f"Toàn bộ {len(all_pre_products):,} sản phẩm có >=1 đơn trước T "
                  f"(không giới hạn top {N_TOP}), {len(df_all):,} có điểm: "
                  f"Pearson={round(float(pear_r_all), 4)} (p={float(pear_p_all):.4g}), "
                  f"Spearman={round(float(spear_r_all), 4)} (p={float(spear_p_all):.4g})",
        "computed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }

    results["metrics"]["health_pearson_seed"] = {
        "value": None,
        "threshold": 0.65,
        "passed": False,
        "reason": "chưa đo được, cần Mongo access — vc-ai/vc-data chỉ có mẫu 100 "
                  "dòng cho orders/order_items/reviews/listing_daily (không đủ để "
                  "tính tỷ lệ mua trên 500 listing seed theo §6.4). listings.parquet "
                  "và listing_variants.parquet có đủ 5.000 listing nhưng không có "
                  "lượt xem/đơn hàng đầy đủ offline.",
    }
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"Đã ghi {results_path} -> metrics.health_pearson, metrics.health_pearson_seed")

    # CSV kiểm tra tay
    out_csv = HERE / "health_score_olist_top500.csv"
    df.to_csv(out_csv, index=False, encoding="utf-8-sig")
    print(f"Đã ghi {out_csv}")

    return {"pearson": pear_r, "p_value": pear_p, "spearman": spear_r, "n": n}


if __name__ == "__main__":
    main()
