"""Toàn cảnh cạnh tranh trong một danh mục (F32): mỗi shop một dòng cho bản đồ vị thế và bảng so sánh,
mỗi sản phẩm một điểm (giá, số bán, chất liệu) cho biểu đồ giá. Hàm thuần, không đọc DB.

Chọn cách tính cho sàn ít shop, ít dữ liệu:
- Đối thủ trực tiếp = cùng loại hàng × cùng tầm giá với tôi (không chỉ giống mẫu mã): shop bán hoodie cùng giá
  là đối thủ dù tên sản phẩm khác hẳn.
- "Đang lên/xuống" so THỊ PHẦN 4 tuần gần với 4 tuần trước (kiểm định hai tỉ lệ), vì sàn mới thì shop nào
  cũng tăng đơn; tăng đột biến tuần này dùng đúng z bền của F36.
- Giá dùng trung vị và khoảng 25–75%, không dùng trung bình (vài sản phẩm lệch là kéo lệch cả shop).
"""
import math
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from statistics import median
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
from scipy.stats import binomtest, false_discovery_control, mannwhitneyu

from app.api.v1._materials import chuan_hoa
from app.api.v1._competitor_ai import tang_dot_bien

SO_TUAN = 8
CUA_SO_MOI_NGAY = 56          # 8 tuần, cùng cửa sổ với phần Theo dõi
Z_THI_PHAN = 1.96          # thị phần đổi thật ở mức tin cậy 95%, không phải dao động ngẫu nhiên
TOI_THIEU_XU_HUONG = 10    # OpenIntro: mỗi nửa 4 tuần cần ≥ 10 lần "của shop" và ≥ 10 lần "của shop khác" (tỉ lệ gộp)
CUNG_PHAN_KHUC = 0.10      # định nghĩa "cùng tầm giá"; Olist: mọi mức 5–30% đều cho ≥ 80% shop chọn ra vẫn bán hơn
GAP_THAM_KHAO = 2.0        # Olist 2018: 85,4% shop được chọn vẫn bán hơn bạn sau 90 ngày (RESULT_OLIST_REFERENCE_SHOP)
TOI_THIEU_VUNG_GIA = 3     # dưới 3 sản phẩm có đơn thì chưa nói được vùng giá bán chạy
IT_DU_LIEU_VUNG = 10       # Olist: khoảng từ 3–9 sản phẩm chỉ chứa 36,9% lượng bán, từ 10–29 sản phẩm 52,3% (lý thuyết 50%)
MUC_Y_NGHIA = 0.05         # bảng so sánh chỉ tô màu khi khác biệt có ý nghĩa thống kê 5%, cùng mức với xu hướng


def _ngay(x: Any) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(x).replace("Z", "+00:00")) if x else None
    except ValueError:
        return None


def _loai(r: dict) -> str:
    return r.get("product_type_name") or r.get("product_type_id") or "Khác"


def _xu_huong(tuan_shop: Sequence[int], tuan_tong: Sequence[int]) -> Dict[str, Any]:
    vot = tang_dot_bien({"_": list(tuan_shop)})
    if vot:
        return {"kind": "surge", "last_week": vot[0]["last_week"], "baseline": vot[0]["baseline"]}
    a0, a1 = sum(tuan_shop[:SO_TUAN // 2]), sum(tuan_shop[SO_TUAN // 2:])
    n0, n1 = sum(tuan_tong[:SO_TUAN // 2]), sum(tuan_tong[SO_TUAN // 2:])
    if not n0 or not n1:
        return {"kind": None}
    p = (a0 + a1) / (n0 + n1)
    if min(n0, n1) * min(p, 1 - p) < TOI_THIEU_XU_HUONG:
        return {"kind": None}
    se = math.sqrt(p * (1 - p) * (1 / n0 + 1 / n1))
    z = (a1 / n1 - a0 / n0) / se if se else 0.0
    return {"kind": "up" if z >= Z_THI_PHAN else "down" if z <= -Z_THI_PHAN else "stable",
            "share_before_pct": round(100 * a0 / n0, 1), "share_after_pct": round(100 * a1 / n1, 1), "z": round(z, 2)}


def tong_hop_shop(rows: List[dict], toi: str, tuan: Dict[str, List[int]], trung: Dict[str, int],
                  now: datetime) -> Dict[str, Any]:
    """`rows` = dòng quét của một danh mục; `tuan` = số bán theo tuần trong danh mục; `trung` = số sản phẩm của tôi
    mà shop đó có hàng giống (MayGiong). Trả {shops, concentration_top3_pct}."""
    theo_shop: Dict[str, List[dict]] = defaultdict(list)
    for r in rows:
        theo_shop[r["shop_id"]].append(r)
    tong_ban = sum(r["est_sales_90d"] for r in rows)
    tuan_tong = [sum(v[k] for v in tuan.values()) for k in range(SO_TUAN)]
    moc_moi = now - timedelta(days=CUA_SO_MOI_NGAY)
    gia_loai = {sid: {t: float(np.median([r["price_vnd"] for r in ds if _loai(r) == t])) for t in {_loai(r) for r in ds}}
                for sid, ds in theo_shop.items()}
    cua_toi = theo_shop.get(toi, [])
    loai_toi = Counter(_loai(r) for r in cua_toi)

    shops, mau_tl = [], {}
    for sid, ds in theo_shop.items():
        gia = [r["price_vnd"] for r in ds]
        co_dg = [r for r in ds if r.get("n_reviews") and r.get("rating_shrunk") is not None]
        cl = Counter(c for r in ds for c in {c for m in r.get("materials") or [] for c in chuan_hoa(m)})
        ban = sum(r["est_sales_90d"] for r in ds)
        phan_hoi = next((r["shop_response_seconds"] for r in ds if r.get("shop_response_seconds")), None)
        mau_tl[sid] = next((r["shop_response_samples"] for r in ds if r.get("shop_response_samples")), [])
        n_dg = sum(r.get("n_reviews") or 0 for r in ds)
        ti_le = next((r["shop_reply_rate"] for r in ds if r.get("shop_reply_rate") is not None), None)
        w = tuan.get(sid) or [0] * SO_TUAN
        d: Dict[str, Any] = {
            "shop_id": sid, "shop_name": ds[0].get("shop_name"), "is_me": sid == toi,
            "n_listings": len(ds),
            "types": [{"name": t, "count": n} for t, n in Counter(_loai(r) for r in ds).most_common()],
            "materials": [c for c, _ in cl.most_common(3)],
            "new_8w": sum(1 for r in ds if (_ngay(r.get("created_at")) or moc_moi) > moc_moi),
            "price_vnd": {"p25": int(np.percentile(gia, 25)), "median": int(np.median(gia)), "p75": int(np.percentile(gia, 75))},
            "units_90d": ban,
            "share_pct": round(100 * ban / tong_ban, 1) if tong_ban else 0.0,
            # Sao đã co ngót theo số lượt (rating_shrunk), gộp theo số lượt đánh giá của từng sản phẩm.
            "rating": round(sum(r["rating_shrunk"] * r["n_reviews"] for r in co_dg) / sum(r["n_reviews"] for r in co_dg), 2) if co_dg else None,
            # Sao thật (trung bình mọi lượt, không co ngót) để hiện cho người bán, khớp trang shop.
            "rating_real": round(sum(r.get("rating_sum") or 0 for r in ds) / n_dg, 2) if n_dg else None,
            "n_reviews": n_dg,
            "favorites": sum(r.get("favorite_count") or 0 for r in ds),
            "response_minutes": round(phan_hoi / 60) if phan_hoi else None,
            "reply_rate": ti_le,
            "weekly_units": list(w),
            "trend": _xu_huong(w, tuan_tong),
            "similar_listings": trung.get(sid, 0),
            "rivalry": None, "shared_types": [], "is_peer": False,
            "response_better": None, "more_new": False,
        }
        if sid != toi and cua_toi:
            # Mức đối đầu: với từng loại hàng tôi bán, họ có bán không và giá gần tới đâu (min/max của hai giá trung vị).
            diem, cung = 0.0, []
            for t, n in loai_toi.items():
                if t in gia_loai[sid]:
                    a, b = gia_loai[sid][t], gia_loai[toi][t]
                    diem += n / len(cua_toi) * (min(a, b) / max(a, b) if max(a, b) else 0)
                    cung.append(t)
            d["rivalry"], d["shared_types"] = round(100 * diem), cung
        shops.append(d)

    me = next((d for d in shops if d["is_me"]), None)
    kiem = []      # (shop, ô, p, giá trị khi có ý nghĩa)
    for d in shops:
        if me is None or d["is_me"]:
            continue
        # Thời gian trả lời từng lượt hỏi: Mann–Whitney (1947), không cần giả định phân phối chuẩn.
        a, b = mau_tl[d["shop_id"]], mau_tl[me["shop_id"]]
        if a and b and median(a) != median(b):
            kiem.append((d, "response_better", mannwhitneyu(a, b, alternative="two-sided").pvalue,
                         "them" if median(a) < median(b) else "me"))
        # Số sản phẩm mới trong cùng 8 tuần: so hai số đếm Poisson (Przyborowski & Wilenski 1940) = kiểm định nhị thức p = 0,5.
        if d["new_8w"] > me["new_8w"]:
            kiem.append((d, "more_new", binomtest(d["new_8w"], d["new_8w"] + me["new_8w"], 0.5).pvalue, True))
    # Nhiều ô kiểm cùng lúc: hiệu chỉnh Benjamini–Hochberg (1995), trong các ô được tô trung bình ≤ 5% là tô nhầm.
    if kiem:
        for (d, o, _, v), q in zip(kiem, false_discovery_control([x[2] for x in kiem], method="bh")):
            if q < MUC_Y_NGHIA:
                d[o] = v
    if me and me["price_vnd"]["median"]:
        m = me["price_vnd"]["median"]
        ung = [d for d in shops if not d["is_me"] and abs(d["price_vnd"]["median"] - m) / m <= CUNG_PHAN_KHUC
               and d["units_90d"] >= GAP_THAM_KHAO * max(me["units_90d"], 1)]
        if ung:
            max(ung, key=lambda d: d["units_90d"])["is_peer"] = True
    shops.sort(key=lambda d: (-d["units_90d"], d["shop_id"]))
    return {"shops": shops,
            "concentration_top3_pct": round(sum(sorted((d["share_pct"] for d in shops), reverse=True)[:3]), 1)}


def diem_gia(rows: List[dict], toi: str) -> List[Dict[str, Any]]:
    """Mỗi sản phẩm một điểm, chất liệu đã quy về tên chuẩn; cách gõ chưa có trong từ điển để riêng, không đoán."""
    ra = []
    for r in rows:
        chuan, la = set(), set()
        for m in r.get("materials") or []:
            c = chuan_hoa(m)
            if c:
                chuan.update(c)
            else:
                la.add(str(m).strip().lower())
        # Biến thể khác chất liệu có giá riêng: lọc theo chất liệu nào thì FE dùng giá của chất liệu đó.
        gia_cl: Dict[str, int] = {}
        for c in r.get("material_prices") or []:
            for t in chuan_hoa(c["material"]):
                gia_cl[t] = min(c["price_vnd"], gia_cl.get(t, c["price_vnd"]))
        ra.append({"listing_id": r["listing_id"], "title": r.get("title"), "shop_name": r.get("shop_name"),
                   "is_mine": r["shop_id"] == toi, "product_type_id": r.get("product_type_id"),
                   "product_type_name": _loai(r), "price_vnd": r["price_vnd"], "units_90d": r["est_sales_90d"],
                   "materials": sorted(chuan), "materials_unknown": sorted(la),
                   "price_by_material": {t: g for t, g in gia_cl.items() if g != r["price_vnd"]}})
    return ra


def vung_ban_chay(diem: List[dict]) -> Optional[Dict[str, int]]:
    """Khoảng giá chứa 50% LƯỢNG BÁN (phân vị có trọng số theo số bán), không phải 50% số sản phẩm."""
    co = sorted((d["price_vnd"], d["units_90d"]) for d in diem if d["units_90d"] > 0)
    if len(co) < TOI_THIEU_VUNG_GIA:
        return None
    tong = sum(w for _, w in co)

    def pv(q: float) -> int:
        cong = 0
        for g, w in co:
            cong += w
            if cong / tong >= q:
                return int(g)
        return int(co[-1][0])

    return {"p25": pv(0.25), "median": pv(0.5), "p75": pv(0.75), "n": len(co)}
