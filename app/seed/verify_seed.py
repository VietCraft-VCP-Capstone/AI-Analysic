import argparse
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Tuple

import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = Path(__file__).resolve().parent
AI_ANALYSIC_DIR = BASE_DIR.parent.parent


def resolve_file(cli_path: str, default_rel: str) -> Path:
    if cli_path:
        p = Path(cli_path).resolve()
        if p.exists():
            return p

    candidates = [
        AI_ANALYSIC_DIR / default_rel,
        Path.cwd() / default_rel,
    ]
    for c in candidates:
        if c.is_file():
            return c.resolve()

    return AI_ANALYSIC_DIR / default_rel


def calculate_density_metrics(
    listings_path: Path,
    orders_path: Path,
    order_items_path: Path,
) -> Tuple[Dict[str, Dict[str, float]], pd.Timestamp, pd.Timestamp, int]:
    if not listings_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file listings: {listings_path}")
    if not orders_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file orders: {orders_path}")
    if not order_items_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file order_items: {order_items_path}")

    df_listings = pd.read_csv(listings_path, usecols=["listing_id", "tier"])
    df_orders = pd.read_csv(orders_path, usecols=["order_id", "ordered_at"])
    df_items = pd.read_csv(order_items_path, usecols=["order_id", "listing_id"])

    df_orders["ordered_at"] = pd.to_datetime(df_orders["ordered_at"])
    max_date = df_orders["ordered_at"].max()
    min_12m = max_date - pd.DateOffset(years=1)

    merged_orders = df_items.merge(df_orders[["order_id", "ordered_at"]], on="order_id", how="inner")
    orders_12m = merged_orders[merged_orders["ordered_at"] >= min_12m]

    orders_per_listing = (
        orders_12m.groupby("listing_id")["order_id"]
        .nunique()
        .reset_index(name="orders_12m")
    )

    full_listings = df_listings.merge(orders_per_listing, on="listing_id", how="left").fillna({"orders_12m": 0.0})

    results = {}
    for tier in ["hot", "medium", "tail"]:
        sub = full_listings[full_listings["tier"] == tier]["orders_12m"]
        total = len(sub)
        p25 = float(sub.quantile(0.25))
        median = float(sub.median())
        p75 = float(sub.quantile(0.75))
        mean = float(sub.mean())
        zero_pct = float((sub == 0).mean() * 100)
        min_v = float(sub.min())
        max_v = float(sub.max())

        results[tier] = {
            "total_listings": total,
            "median_orders": median,
            "q1_25pct": p25,
            "q3_75pct": p75,
            "mean_orders": mean,
            "zero_orders_pct": round(zero_pct, 2),
            "min_orders": min_v,
            "max_orders": max_v,
        }

    sub_all = full_listings["orders_12m"]
    results["all"] = {
        "total_listings": len(sub_all),
        "median_orders": float(sub_all.median()),
        "q1_25pct": float(sub_all.quantile(0.25)),
        "q3_75pct": float(sub_all.quantile(0.75)),
        "mean_orders": float(sub_all.mean()),
        "zero_orders_pct": round(float((sub_all == 0).mean() * 100), 2),
        "min_orders": float(sub_all.min()),
        "max_orders": float(sub_all.max()),
    }

    total_orders_counted = int(orders_12m["order_id"].nunique())
    return results, min_12m, max_date, total_orders_counted


def generate_density_report(
    metrics: Dict[str, Dict[str, float]],
    min_date: pd.Timestamp,
    max_date: pd.Timestamp,
    total_orders: int,
    output_path: Path,
    is_passed: bool,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    status_text = "ĐẠT (PASS)" if is_passed else "CHƯA ĐẠT (FAIL)"

    md = f"""# Báo Cáo Kiểm Định Mật Độ Đơn Hàng Seed Data (Density Verification)

> **Mô tả phép kiểm**: Phép kiểm mật độ đơn hàng theo tầng sản phẩm (`verify_seed.py`)  
> **Khung thời gian 12 tháng**: Từ {min_date.strftime('%d/%m/%Y')} đến {max_date.strftime('%d/%m/%Y')}  
> **Tổng số đơn trong 12 tháng**: {total_orders:,} đơn hàng  
> **Tiêu chuẩn nghiệm thu**: Trung vị (Median) tầng `hot` $\\ge$ 12 đơn/năm  
> **Kết luận chung**: **{status_text}** (Trung vị hot = {metrics['hot']['median_orders']:.1f} đơn/năm)

---

## 1. Bảng Thống Kê Mật Độ Đơn Hàng Theo Tầng (In TRUNG VỊ)

| Tầng sản phẩm (Tier) | Số lượng Listing | TRUNG VỊ đơn/năm (Median) | Khoảng phân bố (IQR: Q1 - Q3) | Tỷ lệ không có đơn (0 đơn) | Ngưỡng kiểm tra | Đánh giá |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| **Tầng Hot** | {metrics['hot']['total_listings']:,} | **{metrics['hot']['median_orders']:.1f} đơn/năm** | {metrics['hot']['q1_25pct']:.1f} - {metrics['hot']['q3_75pct']:.1f} | {metrics['hot']['zero_orders_pct']}% | $\\ge 12$ đơn/năm | **{'ĐẠT' if is_passed else 'LỖI'}** |
| **Tầng Medium** | {metrics['medium']['total_listings']:,} | **{metrics['medium']['median_orders']:.1f} đơn/năm** | {metrics['medium']['q1_25pct']:.1f} - {metrics['medium']['q3_75pct']:.1f} | {metrics['medium']['zero_orders_pct']}% | — | — |
| **Tầng Tail** | {metrics['tail']['total_listings']:,} | **{metrics['tail']['median_orders']:.1f} đơn/năm** | {metrics['tail']['q1_25pct']:.1f} - {metrics['tail']['q3_75pct']:.1f} | {metrics['tail']['zero_orders_pct']}% | — | — |
| **Toàn bộ sàn (Overall)** | {metrics['all']['total_listings']:,} | **{metrics['all']['median_orders']:.1f} đơn/năm** | {metrics['all']['q1_25pct']:.1f} - {metrics['all']['q3_75pct']:.1f} | {metrics['all']['zero_orders_pct']}% | — | — |

---

## 2. Lý Do Khoa Học: Tại Sao Bắt Buộc Dùng TRUNG VỊ Thay Vì TRUNG BÌNH?

1. **Phân bố lệch phải nghiêm trọng (Heavy Right-Skewed Distribution)**:
   - Trong thương mại điện tử thực tế, doanh số tuân theo quy luật Pareto (Power-law): một số ít sản phẩm bán chạy có thể đạt hàng trăm đơn hàng, trong khi phần lớn sản phẩm dài đuôi (tail) bán rất ít hoặc thậm chí 0 đơn.
2. **Nguy cơ sai lệch của số trung bình (Mean Fallacy)**:
   - Nếu chỉ đo lường bằng **trung bình**, vài listing bán chạy cá biệt sẽ kéo số trung bình của toàn tầng lên cao, che lấp hoàn toàn thực tế rằng đa số listing trong tầng có thể bị rỗng.
   - Ví dụ: Ở tầng `hot`, số trung bình là **{metrics['hot']['mean_orders']:.2f} đơn/năm**, cao hơn trung vị (**{metrics['hot']['median_orders']:.1f} đơn/năm**).
3. **Ý nghĩa của tiêu chuẩn Trung vị $\\ge$ 12 đơn/năm**:
   - Tiêu chuẩn trung vị $\\ge 12$ đơn/năm bảo đảm rằng **ít nhất 50% sản phẩm trong tầng hot bán được tối thiểu 1 đơn mỗi tháng**, phản ánh sức sống thực tế và tính liên tục của dữ liệu hành vi người dùng trên sàn VietCraft.
"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(md)


def main():
    parser = argparse.ArgumentParser(description="Phép kiểm mật độ đơn hàng seed data VietCraft.")
    parser.add_argument("--listings", type=str, default="", help="Đường dẫn file listings.csv")
    parser.add_argument("--orders", type=str, default="", help="Đường dẫn file orders.csv")
    parser.add_argument("--order-items", type=str, default="", help="Đường dẫn file order_items.csv")
    parser.add_argument("--out", type=str, default="", help="Đường dẫn xuất file báo cáo QC")

    args = parser.parse_args()

    listings_path = resolve_file(args.listings, "data/external/products/listings.csv")
    orders_path = resolve_file(args.orders, "data/seed_out/v1/orders.csv")
    order_items_path = resolve_file(args.order_items, "data/seed_out/v1/order_items.csv")

    qc_out_path = Path(args.out).resolve() if args.out else AI_ANALYSIC_DIR / "docs" / "qc" / "seed_density.md"

    print("=" * 75)
    print("      VIETCRAFT QA VERIFICATION: PHÉP KIỂM MẬT ĐỘ ĐƠN HÀNG (SEED DATA)")
    print("=" * 75)
    print(f"Nguồn listings   : {listings_path}")
    print(f"Nguồn orders     : {orders_path}")
    print(f"Nguồn order_items: {order_items_path}")

    metrics, min_12m, max_date, total_orders = calculate_density_metrics(
        listings_path, orders_path, order_items_path
    )

    print(f"\nKhung thời gian 12 tháng gần nhất: {min_12m.strftime('%d/%m/%Y')} -> {max_date.strftime('%d/%m/%Y')}")
    print(f"Tổng số đơn phát sinh: {total_orders:,} đơn hàng\n")

    print(f"{'TẦNG SẢN PHẨM':<15}{'SỐ LISTING':<12}{'TRUNG VỊ':<16}{'IQR (Q1 - Q3)':<18}{'TỶ LỆ 0 ĐƠN':<15}")
    print("-" * 75)
    for tier in ["hot", "medium", "tail"]:
        m = metrics[tier]
        iqr_str = f"{m['q1_25pct']:.1f} - {m['q3_75pct']:.1f}"
        print(f"{tier.upper():<15}{m['total_listings']:<12}{m['median_orders']:>5.1f} đơn/năm   {iqr_str:<18}{m['zero_orders_pct']:>5.1f}%")

    all_m = metrics["all"]
    all_iqr = f"{all_m['q1_25pct']:.1f} - {all_m['q3_75pct']:.1f}"
    print("-" * 75)
    print(f"{'TOÀN SÀN':<15}{all_m['total_listings']:<12}{all_m['median_orders']:>5.1f} đơn/năm   {all_iqr:<18}{all_m['zero_orders_pct']:>5.1f}%")
    print("-" * 75)

    hot_median = metrics["hot"]["median_orders"]
    is_passed = hot_median >= 12.0

    print("\n[GIẢI THÍCH THỐNG KÊ]:")
    print("  * In TRUNG VỊ chứ không in trung bình — trung bình bị vài listing bán chạy")
    print("    kéo lên (ví dụ tầng hot có listing lên tới 114 đơn) và che mất chuyện đa số listing rỗng.")
    print("  * Tiêu chí nghiệm thu: TRUNG VỊ TẦNG HOT >= 12.0 đơn/năm")
    print(f"  * Giá trị thực tế đo được: {hot_median:.1f} đơn/năm")

    if is_passed:
        print(f"\n✅ KẾT QUẢ ĐÁNH GIÁ: [ĐẠT] ({hot_median:.1f} >= 12 đơn/năm)")
    else:
        print(f"\n❌ KẾT QUẢ ĐÁNH GIÁ: [CHƯA ĐẠT] ({hot_median:.1f} < 12 đơn/năm)")

    generate_density_report(metrics, min_12m, max_date, total_orders, qc_out_path, is_passed)
    print(f"✓ Đã xuất báo cáo kiểm định ra: {qc_out_path}")
    print("=" * 75)

    sys.exit(0 if is_passed else 1)


if __name__ == "__main__":
    main()
