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
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from app.api.v1._chat_lieu import chuan_hoa
from app.api.v1._doi_thu_ai import tang_dot_bien

SO_TUAN = 8
CUA_SO_MOI_NGAY = 30
Z_THI_PHAN = 1.96          # thị phần đổi thật ở mức tin cậy 95%, không phải dao động ngẫu nhiên
TOI_THIEU_XU_HUONG = 10    # dưới 10 sản phẩm bán trong 8 tuần thì chưa nói lên hay xuống
CUNG_PHAN_KHUC = 0.10      # giá trung vị lệch dưới 10% là cùng phân khúc giá
GAP_THAM_KHAO = 2.0        # shop đáng tham khảo: cùng phân khúc mà bán gấp từ 2 lần bạn
TOI_THIEU_VUNG_GIA = 3     # dưới 3 sản phẩm có đơn thì chưa nói được vùng giá bán chạy


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
    if a0 + a1 < TOI_THIEU_XU_HUONG or not n0 or not n1:
        return {"kind": None}
    p = (a0 + a1) / (n0 + n1)
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

    shops = []
    for sid, ds in theo_shop.items():
        gia = [r["price_vnd"] for r in ds]
        co_dg = [r for r in ds if r.get("n_reviews") and r.get("rating_shrunk") is not None]
        cl = Counter(c for r in ds for c in {c for m in r.get("materials") or [] for c in chuan_hoa(m)})
        ban = sum(r["est_sales_90d"] for r in ds)
        phan_hoi = next((r["shop_response_seconds"] for r in ds if r.get("shop_response_seconds")), None)
        w = tuan.get(sid) or [0] * SO_TUAN
        d: Dict[str, Any] = {
            "shop_id": sid, "shop_name": ds[0].get("shop_name"), "is_me": sid == toi,
            "n_listings": len(ds),
            "types": [{"name": t, "count": n} for t, n in Counter(_loai(r) for r in ds).most_common()],
            "materials": [c for c, _ in cl.most_common(3)],
            "new_30d": sum(1 for r in ds if (_ngay(r.get("created_at")) or moc_moi) > moc_moi),
            "price_vnd": {"p25": int(np.percentile(gia, 25)), "median": int(np.median(gia)), "p75": int(np.percentile(gia, 75))},
            "units_90d": ban,
            "share_pct": round(100 * ban / tong_ban, 1) if tong_ban else 0.0,
            # Sao đã co ngót theo số lượt (rating_shrunk), gộp theo số lượt đánh giá của từng sản phẩm.
            "rating": round(sum(r["rating_shrunk"] * r["n_reviews"] for r in co_dg) / sum(r["n_reviews"] for r in co_dg), 2) if co_dg else None,
            "n_reviews": sum(r.get("n_reviews") or 0 for r in ds),
            "favorites": sum(r.get("favorite_count") or 0 for r in ds),
            "response_minutes": round(phan_hoi / 60) if phan_hoi else None,
            "weekly_units": list(w),
            "trend": _xu_huong(w, tuan_tong),
            "similar_listings": trung.get(sid, 0),
            "rivalry": None, "shared_types": [], "is_peer": False,
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
