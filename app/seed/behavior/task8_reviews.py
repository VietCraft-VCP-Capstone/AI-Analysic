import csv
import json
import os
import sys
from typing import Any, cast

import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    getattr(sys.stdout, "reconfigure")(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AI_ANALYSIC_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "..", ".."))


def resolve_path(rel_path: str) -> str:
    if os.path.exists(rel_path):
        return rel_path
    alt_path = os.path.join(AI_ANALYSIC_DIR, rel_path)
    if os.path.exists(alt_path):
        return alt_path
    return rel_path


ORDERS_PATH = resolve_path("data/seed_out/v1/orders.csv")
ORDER_ITEMS_PATH = resolve_path("data/seed_out/v1/order_items.csv")
DIST_OLIST_PATH = resolve_path("data/seed_out/v1/dist_olist.json")
OUT_PATH = resolve_path("data/seed_out/v1/reviews.csv")

TY_LE_DUOC_DANH_GIA = 0.30
TY_LE_CO_ANH = 0.20

BINH_LUAN_THEO_SAO = {
    5: [
        "Áo đẹp, vải mát, in sắc nét. Sẽ ủng hộ shop tiếp.",
        "Chất lượng vượt mong đợi, đóng gói cẩn thận.",
        "Giao hàng nhanh, đúng như hình, rất ưng ý.",
        "Sản phẩm tuyệt vời, sẽ giới thiệu cho bạn bè.",
    ],
    4: [
        "Sản phẩm ổn, giao hơi lâu một chút.",
        "Chất lượng tốt, đóng gói bình thường.",
        "Áo đẹp nhưng size hơi rộng so với bảng size.",
        "Ưng ý, chỉ tiếc là không có thêm màu khác.",
    ],
    3: [
        "Hàng tạm ổn, màu in hơi nhạt so với ảnh.",
        "Chất lượng trung bình, đúng giá tiền.",
        "Vải hơi mỏng nhưng dùng tạm được.",
        "Giao hàng chậm, sản phẩm thì bình thường.",
    ],
    2: [
        "Vải mỏng hơn mong đợi, giao sai màu.",
        "Đường may không chắc chắn, hơi thất vọng.",
        "Sản phẩm không giống mô tả, chất lượng kém.",
        "Giao thiếu phụ kiện đi kèm, phải liên hệ shop.",
    ],
    1: [
        "Hình in bị lệch, không giống hình mẫu.",
        "Chất lượng quá kém, không đáng tiền.",
        "Giao hàng sai sản phẩm, rất thất vọng.",
        "Vải rách ngay lần giặt đầu tiên.",
    ],
}


def load_diem_sao_va_do_tre() -> tuple[list[int], np.ndarray, list[int], np.ndarray]:
    with open(DIST_OLIST_PATH, encoding="utf-8") as f:
        dist = json.load(f)

    sao_dict = dist["diem_sao"]
    sao_list = sorted(int(k) for k in sao_dict.keys())
    ty_le_sao = np.array([sao_dict[str(s)] for s in sao_list])
    ty_le_sao = ty_le_sao / ty_le_sao.sum()

    tre_dict = dist["do_tre_danh_gia"]
    tre_list = sorted(int(k) for k in tre_dict.keys())
    ty_le_tre = np.array([tre_dict[str(t)] for t in tre_list])
    ty_le_tre = ty_le_tre / ty_le_tre.sum()

    return sao_list, ty_le_sao, tre_list, ty_le_tre


def main():
    rng = np.random.default_rng(42)
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)

    print(f"Đọc dữ liệu đơn hàng từ {ORDERS_PATH}...")
    orders = pd.read_csv(ORDERS_PATH, encoding="utf-8-sig",
                          parse_dates=["ordered_at", "delivered_at"])
    items = pd.read_csv(ORDER_ITEMS_PATH, encoding="utf-8-sig")

    listing_theo_don = items.drop_duplicates("order_id", keep="first").set_index("order_id")["listing_id"].to_dict()

    da_giao = orders[orders["status"] == "delivered"].reset_index(drop=True)
    duoc_chon = np.asarray(rng.random(len(da_giao)) < TY_LE_DUOC_DANH_GIA)
    don_duoc_danh_gia = pd.DataFrame(da_giao.loc[duoc_chon]).reset_index(drop=True)

    print(f"Số đơn đã giao: {len(da_giao):,}")
    print(f"Số đơn được đánh giá: {len(don_duoc_danh_gia):,}")

    sao_list, ty_le_sao, tre_list, ty_le_tre = load_diem_sao_va_do_tre()

    n = len(don_duoc_danh_gia)
    sao_bocc = np.asarray(rng.choice(sao_list, size=n, p=ty_le_sao))
    do_tre_bocc = np.asarray(rng.choice(tre_list, size=n, p=ty_le_tre))
    co_anh = np.asarray(rng.random(n) < TY_LE_CO_ANH)

    rows = []
    for i, row in enumerate(don_duoc_danh_gia.itertuples(index=False)):
        order_id = str(getattr(row, "order_id"))
        buyer_id = str(getattr(row, "buyer_id"))
        listing_id = str(listing_theo_don.get(order_id, ""))
        delivered_at = pd.Timestamp(cast(Any, getattr(row, "delivered_at")))

        sao = int(sao_bocc[i])
        do_tre = int(do_tre_bocc[i])

        # Cộng thêm vài giờ và phút ngẫu nhiên để đảm bảo LUÔN sau thời điểm giao hàng,
        # kể cả khi độ trễ bốc được là 0 ngày (viết đánh giá cùng ngày giao).
        so_gio_le = int(rng.integers(1, 24))
        so_phut_le = int(rng.integers(0, 60))
        reviewed_at = delivered_at + pd.Timedelta(days=do_tre, hours=so_gio_le, minutes=so_phut_le)

        comment_choices = BINH_LUAN_THEO_SAO[sao]
        idx_cmt = int(rng.integers(0, len(comment_choices)))
        comment = comment_choices[idx_cmt]

        rows.append(
            (
                f"rvw_{i+1:06d}", order_id, buyer_id, listing_id, sao,
                comment, bool(co_anh[i]),
                reviewed_at.strftime("%Y-%m-%d %H:%M:%S"),
            )
        )

    print(f"\nGhi {len(rows):,} đánh giá ra {OUT_PATH}...")
    with open(OUT_PATH, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["review_id", "order_id", "buyer_id", "listing_id", "star",
                    "comment", "has_image", "reviewed_at"])
        w.writerows(rows)

    df_reviews = pd.DataFrame(rows, columns=[
        "review_id", "order_id", "buyer_id", "listing_id", "star",
        "comment", "has_image", "reviewed_at",
    ])

    print(f"\nĐã lưu {OUT_PATH}")
    print(f"Tổng số đánh giá: {len(df_reviews):,}")
    print("\nPhân bố sao:")
    for s in sorted(df_reviews["star"].unique()):
        n_s = int(cast(Any, (df_reviews["star"] == s).sum()))
        print(f"  {s} sao: {n_s:>5,}  ({n_s / len(df_reviews) * 100:.1f}%)")
    so_anh = int(cast(Any, df_reviews["has_image"].sum()))
    print(f"\nCó ảnh: {so_anh:,} ({df_reviews['has_image'].mean() * 100:.1f}%)")

    print("\nTự kiểm:")
    status_map = dict(zip(orders["order_id"], orders["status"]))
    trang_thai_cua_don = df_reviews["order_id"].map(lambda oid: status_map.get(oid))
    if (trang_thai_cua_don == "delivered").all():
        print("  OK  không có đánh giá nào gắn với đơn huỷ/chưa giao")
    else:
        print("  !!  CÓ đánh giá gắn với đơn không phải delivered")

    delivery_map = dict(zip(orders["order_id"], orders["delivered_at"]))
    ngay_giao_cua_don = df_reviews["order_id"].map(lambda oid: delivery_map.get(oid))
    so_vi_pham_ngay = (pd.to_datetime(df_reviews["reviewed_at"]) <= pd.to_datetime(ngay_giao_cua_don)).sum()
    if so_vi_pham_ngay == 0:
        print("  OK  ngày viết đánh giá luôn sau ngày giao (độ trễ 0 ngày luôn cộng thêm giờ)")
    else:
        print(f"  !!  CÓ {so_vi_pham_ngay} đánh giá viết trước hoặc cùng lúc ngày giao")

    ty_le_5_sao = float((df_reviews["star"] == 5).mean())
    ty_le_1_sao = float((df_reviews["star"] == 1).mean())
    if ty_le_5_sao > ty_le_1_sao * 3:
        print(f"  OK  phân bố sao lệch về phía cao (5 sao {ty_le_5_sao:.1%} "
              f"> 1 sao {ty_le_1_sao:.1%} nhiều lần)")
    else:
        print(f"  !!  phân bố sao KHÔNG lệch rõ về phía cao - kiểm lại task 1")


if __name__ == "__main__":
    main()
