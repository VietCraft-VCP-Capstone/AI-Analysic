
import argparse
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from pymongo import MongoClient

from app.config import settings
from app.core.writer import MART_SCHEMA, finish_model_run, save_model_output, start_model_run

VERSION = "marts-1.0"

K_CO_NGOT = 10

# Chỉ số Google Trends dưới mức này thì % tăng không đáng tin (thang 0-100).
NEN_TOI_THIEU = 5.0

# Chuỗi ngày phải có ít nhất ngần này tỉ lệ ngày CÓ doanh thu thì z-score mới
# có nghĩa. Dưới ngưỡng, nền của chuỗi là 0 và mọi ngày bán được đều thành đột biến.
TOI_THIEU_NGAY_CO_BAN = 0.40


def _db():
    return MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=20000)[settings.MONGO_DB_SEED]


def _hom_nay(db) -> str:
    """Ngày mới nhất CÓ THẬT trong listing_daily. Không dùng ngày hệ thống:
    dữ liệu mồi dừng ở 2026-08-30, lấy hôm nay thì cửa sổ 90 ngày rỗng."""
    d = db["listing_daily"].find_one({}, {"date": 1}, sort=[("date", -1)])
    return d["date"] if d else datetime.now(timezone.utc).date().isoformat()


def _tach_tag(raw: Any) -> List[str]:
    """Tách chuỗi tag. Nhận cả `;` lẫn `,` cho chắc, bỏ khoảng trắng và ô rỗng."""
    if not raw:
        return []
    s = str(raw).replace(",", ";")
    return sorted({t.strip() for t in s.split(";") if t.strip()})


def _lui(ngay: str, so_ngay: int) -> str:
    return (datetime.strptime(ngay, "%Y-%m-%d").date() - timedelta(days=so_ngay)).isoformat()


# ---------------------------------------------------------------------------
# mart_competitor — một dòng cho mỗi listing. Nền của F32 · F33 · F34 · F35 · F36
# ---------------------------------------------------------------------------

def build_mart_competitor(db) -> List[Dict[str, Any]]:
    den = _hom_nay(db)
    tu = _lui(den, 90)

    ban = {r["_id"]: r for r in db["listing_daily"].aggregate([
        {"$match": {"date": {"$gte": tu, "$lte": den}}},
        {"$group": {"_id": "$listing_id",
                    "est_sales_90d": {"$sum": "$units_sold"},
                    "views_90d": {"$sum": "$views"},
                    "carts_90d": {"$sum": "$add_to_carts"},
                    "orders_90d": {"$sum": "$orders"},
                    "revenue_90d": {"$sum": "$revenue_vnd"}}},
    ])}

    danh_gia = {r["_id"]: r for r in db["reviews"].aggregate([
        {"$group": {"_id": "$listing_id", "n": {"$sum": 1},
                    "sao": {"$avg": {"$toDouble": "$star"}}}},
    ])}

    ten_shop = {s["shop_id"]: s.get("name") for s in db["shops"].find({}, {"shop_id": 1, "name": 1})}

    listings = list(db["listings"].find({}, {
        "_id": 0, "listing_id": 1, "shop_id": 1, "category_id": 1, "product_type_id": 1,
        "base_price_vnd": 1, "favorite_count": 1, "tags": 1, "title": 1, "status": 1,
    }))

    # Trung bình sao theo danh mục — mốc để co ngót về.
    tong_sao, tong_n = defaultdict(float), defaultdict(int)
    for l in listings:
        dg = danh_gia.get(l["listing_id"])
        if dg:
            tong_sao[l["category_id"]] += dg["sao"] * dg["n"]
            tong_n[l["category_id"]] += dg["n"]
    sao_danh_muc = {c: tong_sao[c] / tong_n[c] for c in tong_n if tong_n[c]}

    ban_ghi = []
    for l in listings:
        lid = l["listing_id"]
        b = ban.get(lid, {})
        dg = danh_gia.get(lid)
        cat = l.get("category_id")

        if dg and dg["n"]:
            moc = sao_danh_muc.get(cat, dg["sao"])
            rating = round((dg["sao"] * dg["n"] + moc * K_CO_NGOT) / (dg["n"] + K_CO_NGOT), 2)
            n_rv = dg["n"]
        else:
            # Chưa có đánh giá -> null, KHÔNG mặc định 4.0 sao (hợp đồng F29).
            rating, n_rv = None, 0

        ban_ghi.append({
            "listing_id": lid,
            "shop_id": l.get("shop_id"),
            "shop_name": ten_shop.get(l.get("shop_id")),
            "category_id": cat,
            "product_type_id": l.get("product_type_id"),
            "title": l.get("title"),
            "status": l.get("status"),
            "price_vnd": int(float(l.get("base_price_vnd") or 0)),
            "est_sales_90d": int(b.get("est_sales_90d") or 0),
            "views_90d": int(b.get("views_90d") or 0),
            "carts_90d": int(b.get("carts_90d") or 0),
            "orders_90d": int(b.get("orders_90d") or 0),
            "revenue_90d_vnd": int(round(float(b.get("revenue_90d") or 0))),
            "rating_shrunk": rating,
            "n_reviews": n_rv,
            "favorite_count": int(float(l.get("favorite_count") or 0)),
            # Dấu phân cách là `;` — kiểm trên 5.000 listing: 4.004 dòng có `;`,
            # KHÔNG dòng nào có `|`. Tách nhầm thì cả chuỗi "ao-thun;qua-tet" thành
            # MỘT tag, và F34 (phép trừ tập hợp) không bao giờ tìm thấy gì.
            "tags": _tach_tag(l.get("tags")),
            "window_from": tu,
            "window_to": den,
        })

    # rank_in_cat — xếp theo est_sales_90d giảm dần trong từng danh mục (BR-188).
    theo_cat = defaultdict(list)
    for r in ban_ghi:
        theo_cat[r["category_id"]].append(r)
    for rows in theo_cat.values():
        rows.sort(key=lambda r: (-r["est_sales_90d"], -r["revenue_90d_vnd"]))
        for i, r in enumerate(rows, 1):
            r["rank_in_cat"] = i
            r["n_in_cat"] = len(rows)

    return ban_ghi


# ---------------------------------------------------------------------------
# Nguồn cầu: Google Trends trong `data-collection.trend_interest`.
# Đây là dữ liệu THẬT duy nhất của dự án — cron vẫn đang chạy.
# ---------------------------------------------------------------------------

def _db_trends():
    return MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=20000)[settings.MONGO_DB_DATA]


def _chuoi_tuan(dbt) -> Dict[str, List[tuple]]:
    """{keyword: [(ngày, giá trị scaled), ...]} theo tuần, đã sắp xếp."""
    chuoi = defaultdict(list)
    for r in dbt["trend_interest"].find(
            {"granularity": "weekly", "is_anchor": {"$ne": True}},
            {"_id": 0, "keyword": 1, "observed_on": 1, "scaled": 1}):
        v = r.get("scaled")
        if v is None:
            continue
        ngay = str(r["observed_on"])[:10]
        chuoi[r["keyword"]].append((ngay, float(v)))
    for k in chuoi:
        chuoi[k].sort()
    return chuoi


def _tag_theo_keyword(db) -> Dict[str, List[str]]:
    m = defaultdict(list)
    for r in db["tag_keyword_map"].find({}, {"_id": 0, "keyword": 1, "tag_id": 1}):
        m[r["keyword"]].append(r["tag_id"])
    return m


def _cung_theo_tag(db) -> Dict[str, int]:
    """Số listing đang bán mang tag đó — phía CUNG của bài toán ngách."""
    dem = Counter()
    for l in db["listings"].find({"status": "active"}, {"_id": 0, "tags": 1}):
        for t in _tach_tag(l.get("tags")):
            dem[t] += 1
    return dem


def _phan_vi_xep_hang(gia_tri: Dict[str, float]) -> Dict[str, float]:
    """Đổi giá trị thô thành phân vị 0–100 trong cùng tập. So cầu với cung thì
    phải đưa về cùng thang: lượt tìm Google và số listing không cùng đơn vị."""
    if not gia_tri:
        return {}
    sap = sorted(gia_tri.values())
    n = len(sap)
    return {k: round(sum(1 for x in sap if x <= v) / n * 100, 1) for k, v in gia_tri.items()}


# ---------------------------------------------------------------------------
# niche_score — ngách nhiều người tìm mà ít người bán. Nền của F39 · F41
# ---------------------------------------------------------------------------

def build_niche_score(db) -> List[Dict[str, Any]]:
    dbt = _db_trends()
    chuoi = _chuoi_tuan(dbt)
    tag_map = _tag_theo_keyword(db)
    cung = _cung_theo_tag(db)
    den = _hom_nay(db)

    # Cầu = trung bình 12 tuần gần nhất. Lấy trung bình chứ không lấy điểm cuối:
    # một tuần lễ Tết có thể vọt gấp 5 lần và làm ngách đó trông như cơ hội quanh năm.
    cau_tho, xu_huong, tia = {}, {}, {}
    for kw, diem in chuoi.items():
        if len(diem) < 16:
            continue
        gan = [v for _, v in diem[-12:]]
        truoc = [v for _, v in diem[-24:-12]] or gan
        cau_tho[kw] = sum(gan) / len(gan)
        tb_truoc = sum(truoc) / len(truoc)
        tang = (cau_tho[kw] - tb_truoc) / tb_truoc * 100 if tb_truoc else 0.0
        xu_huong[kw] = ("rising" if tang > 10 else "falling" if tang < -10 else "flat", round(tang, 1))
        tia[kw] = [round(v, 1) for _, v in diem[-7:]]

    cau_pct = _phan_vi_xep_hang(cau_tho)
    cung_tho = {kw: sum(cung.get(t, 0) for t in tag_map.get(kw, [])) for kw in cau_tho}
    cung_pct = _phan_vi_xep_hang(cung_tho)

    ban_ghi = []
    for kw in cau_tho:
        tags = tag_map.get(kw, [])
        gap = round(cau_pct[kw] - cung_pct[kw], 1)
        huong, tang = xu_huong[kw]
        ban_ghi.append({
            "keyword": kw,
            "date": den,
            "tag_id": tags[0] if tags else None,
            "tag_ids": tags,
            "demand_pct": cau_pct[kw],
            "supply_pct": cung_pct[kw],
            "gap_score": gap,
            "n_listings": cung_tho[kw],
            "demand_index": round(cau_tho[kw], 2),
            "trend": huong,
            "growth_pct": tang,
            "sparkline_7d": tia[kw],
            "quadrant": ("opportunity" if cau_pct[kw] >= 50 and cung_pct[kw] < 50 else
                         "crowded" if cau_pct[kw] >= 50 else
                         "niche_quiet" if cung_pct[kw] < 50 else "oversupplied"),
        })

    ban_ghi.sort(key=lambda r: -r["gap_score"])
    for i, r in enumerate(ban_ghi, 1):
        r["rank"] = i
    return ban_ghi


# ---------------------------------------------------------------------------
# mart_demand — nhu cầu tìm kiếm theo TAG. Nền của F40 (và F38/F39 tham chiếu)
# ---------------------------------------------------------------------------

def build_mart_demand(db) -> List[Dict[str, Any]]:
    dbt = _db_trends()
    chuoi = _chuoi_tuan(dbt)
    tag_map = _tag_theo_keyword(db)
    cung = _cung_theo_tag(db)
    den = _hom_nay(db)
    tuan_iso = datetime.strptime(den, "%Y-%m-%d").date().isocalendar()

    gom = defaultdict(list)
    for kw, diem in chuoi.items():
        for t in tag_map.get(kw, []):
            gom[t].append(diem)

    ten_tag = {t["tag_id"]: t.get("name_vi") for t in db["tags"].find({}, {"tag_id": 1, "name_vi": 1})}

    ban_ghi = []
    for tag, cac_chuoi in gom.items():
        gan, truoc = [], []
        for diem in cac_chuoi:
            if len(diem) < 16:
                continue
            gan += [v for _, v in diem[-4:]]
            truoc += [v for _, v in diem[-8:-4]]
        if not gan:
            continue
        tb_gan = sum(gan) / len(gan)
        tb_truoc = sum(truoc) / len(truoc) if truoc else tb_gan

        nen_du = max(tb_gan, tb_truoc) >= NEN_TOI_THIEU
        tang = (round((tb_gan - tb_truoc) / tb_truoc * 100, 1)
                if nen_du and tb_truoc else None)

        ban_ghi.append({
            "tag_id": tag,
            "name_vi": ten_tag.get(tag, tag),
            "week": f"{tuan_iso[0]}-W{tuan_iso[1]:02d}",
            "demand_index": round(tb_gan, 2),
            "searches_per_week": None,
            "demand_scale_note": "chỉ số Google Trends 0-100, không phải số lượt tìm tuyệt đối",
            "growth_pct": tang,
            "momentum": round(max(0.0, min(1.0, tang / 100 + 0.5)), 3) if tang is not None else None,
            "supply_n_listings": cung.get(tag, 0),
            "trend": ("rising" if tang > 10 else "falling" if tang < -10 else "flat")
                     if tang is not None else "unknown",
            "low_base": not nen_du,
            "n_keywords": len(cac_chuoi),
        })
    # Tag nền yếu xếp xuống dưới, không cho chen lên đầu bảng "nóng nhất".
    ban_ghi.sort(key=lambda r: (r["low_base"], -(r["growth_pct"] or -999)))
    return ban_ghi


# ---------------------------------------------------------------------------
# seasonal_profile — phân rã mùa vụ bằng STL. Nền của F38
# ---------------------------------------------------------------------------

def build_seasonal_profile(db) -> List[Dict[str, Any]]:
    from app.services.stl_service import STLService

    dbt = _db_trends()
    chuoi = _chuoi_tuan(dbt)
    tag_map = _tag_theo_keyword(db)

    ban_ghi = []
    for kw, diem in chuoi.items():
        # BR-208: cần >= 12 tháng. Chuỗi tuần -> 52 điểm. Dưới ngưỡng thì BỎ QUA,
        # không phân rã bừa rồi gọi là mùa vụ.
        if len(diem) < 104:          # 2 năm, để STL thấy được ít nhất 2 chu kỳ
            continue
        gia_tri = [v for _, v in diem]
        try:
            pr = STLService.decompose(gia_tri, period=52, robust=True)
        except Exception:
            continue
        mua = pr["seasonal"]
        bien_do = round(max(mua) - min(mua), 2)
        dinh = max(range(len(mua)), key=lambda i: mua[i])
        ban_ghi.append({
            "entity_type": "keyword",
            "entity_id": kw,
            "period_type": "week_of_year",
            "period_value": str(datetime.strptime(diem[dinh][0], "%Y-%m-%d").date().isocalendar()[1]),
            "tag_ids": tag_map.get(kw, []),
            "trend": [round(x, 3) for x in pr["trend"][-52:]],
            "seasonal": [round(x, 3) for x in mua[-52:]],
            "residual": [round(x, 3) for x in pr["residual"][-52:]],
            "amplitude": bien_do,
            "peak_date_sample": diem[dinh][0],
            "n_points": len(diem),
            "has_seasonality": bien_do > 5.0,
        })
    ban_ghi.sort(key=lambda r: -r["amplitude"])
    return ban_ghi


# ---------------------------------------------------------------------------
# mart_listing_quality — phễu mua hàng từng listing. Nền của F28
# ---------------------------------------------------------------------------

def _phan_tram(tu: float, mau: float):
    """tu/mau × 100. Mẫu bằng 0 -> None, KHÔNG phải 0: 'chưa ai xem' khác
    'có người xem mà không ai mua'."""
    return round(tu / mau * 100, 2) if mau else None


def build_mart_listing_quality(db) -> List[Dict[str, Any]]:
    den = _hom_nay(db)
    tu = _lui(den, 90)

    pheu = {r["_id"]: r for r in db["listing_daily"].aggregate([
        {"$match": {"date": {"$gte": tu, "$lte": den}}},
        {"$group": {"_id": "$listing_id", "views": {"$sum": "$views"},
                    "carts": {"$sum": "$add_to_carts"}, "orders": {"$sum": "$orders"},
                    "category_id": {"$first": "$category_id"}}},
    ])}
    if not pheu:
        return []

    # Trung bình CR của danh mục — mốc để nói listing này khoẻ hay yếu.
    gom = defaultdict(lambda: {"v": 0, "o": 0})
    for r in pheu.values():
        g = gom[r["category_id"]]
        g["v"] += r["views"]
        g["o"] += r["orders"]
    cr_danh_muc = {c: _phan_tram(g["o"], g["v"]) for c, g in gom.items()}

    ban_ghi = []
    for lid, r in pheu.items():
        v2c = _phan_tram(r["carts"], r["views"])
        c2o = _phan_tram(r["orders"], r["carts"])
        v2o = _phan_tram(r["orders"], r["views"])
        moc = cr_danh_muc.get(r["category_id"])
        chi_so = round(v2o / moc, 2) if (v2o is not None and moc) else None

        # Khâu yếu nhất: so mỗi bước với chính danh mục, không so hai bước với nhau —
        # xem->giỏ và giỏ->mua có thang khác hẳn, so thẳng là luôn ra cùng một kết luận.
        yeu = None
        if v2c is not None and c2o is not None:
            yeu = "view_to_cart" if v2c < c2o / 4 else "cart_to_order"
        elif v2c is not None:
            yeu = "view_to_cart"

        # BR-179: CHỈ gợi ý khi CR thấp hơn danh mục >= 20%. Không thì mảng rỗng.
        tips = []
        if chi_so is not None and chi_so <= 0.8:
            if yeu == "view_to_cart":
                tips.append({"issue": f"Chỉ {v2c}% người xem thêm vào giỏ",
                             "action": "Ảnh đầu tiên nên chụp sản phẩm đang được dùng thật"})
            else:
                tips.append({"issue": f"Chỉ {c2o}% người đã thêm giỏ thì đặt hàng",
                             "action": "Kiểm lại phí vận chuyển và thời gian giao hiển thị ở trang sản phẩm"})

        ban_ghi.append({
            "listing_id": lid,
            "funnel": {"views": int(r["views"]), "carts": int(r["carts"]), "orders": int(r["orders"])},
            "view_to_cart_pct": v2c,
            "cart_to_order_pct": c2o,
            "view_to_order_pct": v2o,
            "category_avg_pct": moc,
            "cr_index": chi_so,
            "weakest_step": yeu,
            "tips": tips,
            "category_id": r["category_id"],
            "window_from": tu, "window_to": den,
        })
    return ban_ghi


# ---------------------------------------------------------------------------
# listing_health — điểm 0-100 trên 5 trục. Nền của F29
# ---------------------------------------------------------------------------

TRONG_SO = {"conversion": 0.30, "rating": 0.25, "content": 0.20, "stock": 0.15, "freshness": 0.10}


def build_listing_health(db) -> List[Dict[str, Any]]:
    assert abs(sum(TRONG_SO.values()) - 1.0) < 1e-9, "trọng số phải cộng đúng 1.0 — cổng ra kiểm"

    den = _hom_nay(db)
    chat_luong = {r["listing_id"]: r for r in build_mart_listing_quality(db)}
    if not chat_luong:
        return []

    danh_gia = {r["_id"]: r for r in db["reviews"].aggregate([
        {"$group": {"_id": "$listing_id", "n": {"$sum": 1},
                    "sao": {"$avg": {"$toDouble": "$star"}}}}])}
    ton = {r["_id"]: r["tong"] for r in db["listing_variants"].aggregate([
        {"$group": {"_id": "$listing_id", "tong": {"$sum": {"$toDouble": "$stock_qty"}}}}])}

    hom_nay_d = datetime.strptime(den, "%Y-%m-%d").date()
    ban_ghi = []
    for l in db["listings"].find({}, {"_id": 0, "listing_id": 1, "images": 1, "description": 1,
                                      "created_at": 1, "title": 1, "category_id": 1}):
        lid = l["listing_id"]
        cl = chat_luong.get(lid)
        if not cl:
            continue

        # conversion: chỉ số so danh mục, 1.0 = ngang mặt bằng -> 50 điểm
        ci = cl.get("cr_index")
        d_cr = None if ci is None else round(min(100.0, ci * 50), 1)

        dg = danh_gia.get(lid)
        # Chưa có đánh giá -> null, KHÔNG mặc định 4.0 sao (hợp đồng F29).
        d_sao = round((dg["sao"] - 1) / 4 * 100, 1) if dg else None
        sao_co = round(dg["sao"], 2) if dg else None

        n_anh = len([x for x in str(l.get("images") or "").split(";") if x.strip()])
        dai_mo_ta = len(str(l.get("description") or ""))
        d_nd = round(min(100.0, n_anh / 5 * 60 + min(dai_mo_ta, 400) / 400 * 40), 1)

        tk = ton.get(lid, 0)
        d_ton = round(min(100.0, tk / 50 * 100), 1)

        try:
            tuoi = (hom_nay_d - datetime.strptime(str(l["created_at"])[:10], "%Y-%m-%d").date()).days
        except Exception:
            tuoi = None
        d_moi = None if tuoi is None else round(max(0.0, 100 - max(0, tuoi) / 365 * 100), 1)

        truc = {"conversion": d_cr, "rating": d_sao, "content": d_nd,
                "stock": d_ton, "freshness": d_moi}

        # Trục thiếu dữ liệu thì BỎ khỏi phép tính và chia lại trọng số, chứ không
        # cho 0 điểm — cho 0 là phạt listing vì chưa ai đánh giá, không phải vì kém.
        co = {k: v for k, v in truc.items() if v is not None}
        tong_ts = sum(TRONG_SO[k] for k in co)
        diem = round(sum(co[k] * TRONG_SO[k] for k in co) / tong_ts, 1) if tong_ts else None

        ban_ghi.append({
            "listing_id": lid,
            "date": den,
            "title": l.get("title"),
            "health_score": diem,
            "band": (None if diem is None else
                     "tốt" if diem >= 80 else "cần cải thiện" if diem >= 50 else "kém"),
            "conversion_rate": cl.get("view_to_order_pct"),
            "category_avg_cr": cl.get("category_avg_pct"),
            "cr_index": ci,
            "rating_shrunk": sao_co,
            "n_reviews": dg["n"] if dg else 0,
            "breakdown": {k: {"score": truc[k], "weight": TRONG_SO[k],
                              "counted": truc[k] is not None} for k in TRONG_SO},
            "axes_missing": sorted(k for k in truc if truc[k] is None),
            "todo": _viec_can_lam(truc, n_anh, tk),
        })
    return ban_ghi


def _viec_can_lam(truc, n_anh, ton_kho):
    viec = []
    if truc["content"] is not None and truc["content"] < 70:
        viec.append({"priority": 1, "action": f"Thêm ảnh: hiện có {n_anh}, nên từ 5 ảnh",
                     "expected_gain": "+8 điểm"})
    if truc["stock"] is not None and truc["stock"] < 50:
        viec.append({"priority": 2, "action": f"Bổ sung tồn kho: còn {int(ton_kho)} sản phẩm",
                     "expected_gain": "+6 điểm"})
    if truc["conversion"] is not None and truc["conversion"] < 40:
        viec.append({"priority": 1, "action": "Tỉ lệ chuyển đổi dưới mặt bằng danh mục — xem F28 để biết hỏng ở khâu nào",
                     "expected_gain": "+10 điểm"})
    return sorted(viec, key=lambda v: v["priority"])


# ---------------------------------------------------------------------------
# anomaly_event — ngày doanh thu tụt/vọt bất thường. Nền của F30
# ---------------------------------------------------------------------------

def build_anomaly_event(db) -> List[Dict[str, Any]]:
    from app.services.zscore_service import ZScoreService

    chuoi = defaultdict(list)
    for r in db["listing_daily"].aggregate([
        {"$group": {"_id": {"s": "$shop_id", "d": "$date"}, "rev": {"$sum": "$revenue_vnd"}}},
        {"$sort": {"_id.d": 1}},
    ]):
        chuoi[r["_id"]["s"]].append((r["_id"]["d"], float(r["rev"])))

    ban_ghi = []
    bo_qua = {"qua_ngan": 0, "qua_thua": 0, "khong_tin_cay": 0, "loi": 0}

    for shop, diem in chuoi.items():
        if len(diem) < 60:          # dưới ~2 tháng thì z-score không có nghĩa
            bo_qua["qua_ngan"] += 1
            continue

        ngay = [d for d, _ in diem]
        gia_tri = [v for _, v in diem]

        # CHẶN CHUỖI QUÁ THƯA. Đo thật 21/09: shp_00018 có 297/380 ngày doanh thu
        # bằng 0 (78%). Trên chuỗi như vậy mọi ngày CÓ bán đều thành "đột biến" —
        # z-score giả định phần dư phân bố quanh một mức nền, mà ở đây nền là 0.
        # Chạy bừa cho ra 4.423 cảnh báo trên 80 shop, tỉ lệ 10%, gấp đôi ngưỡng
        # MAX_ANOMALY_RATE. Cảnh báo sai nhiều thì người bán tắt thông báo, và
        # tính năng chết hẳn — tệ hơn là không có tính năng.
        ty_le_khac_0 = sum(1 for v in gia_tri if v) / len(gia_tri)
        if ty_le_khac_0 < TOI_THIEU_NGAY_CO_BAN:
            bo_qua["qua_thua"] += 1
            continue

        try:
            kq = ZScoreService.analyze(gia_tri, dates=ngay, period=7)
        except Exception:
            bo_qua["loi"] += 1
            continue

        # Chính service đã tự chấm chuỗi này không đáng tin -> KHÔNG ghi gì cả.
        # Ghi kèm cờ cảnh báo vẫn là ghi: API đọc ra và người bán vẫn thấy.
        if kq.get("status") == "unreliable_high_rate":
            bo_qua["khong_tin_cay"] += 1
            continue

        for p in kq.get("points", []):
            if not p.get("is_anomaly"):
                continue
            i = p["index"]
            ban_ghi.append({
                "entity_type": "shop",
                "entity_id": shop,
                "event_date": ngay[i],
                "direction": "drop" if p["score"] < 0 else "spike",
                "z": round(float(p["score"]), 2),
                "expected": int(round(float(p.get("trend", 0)) + float(p.get("seasonal", 0)))),
                "actual": int(round(float(p["value"]))),
                "severity": ("high" if abs(p["score"]) >= 15 else
                             "medium" if abs(p["score"]) >= 10 else "low"),
                "calendar_sensitive": bool(p.get("calendar_sensitive")),
                # Cờ tin cậy của CẢ CHUỖI, không phải của riêng điểm này — chuỗi ít
                # chu kỳ thì mọi điểm trên nó đều kém tin, phải nói ra.
                "confidence": kq.get("status", "ok"),
                "reliability_note": kq.get("reliability_note"),
                "cycles_observed": round(float(kq.get("cycles_observed", 0)), 1),
            })
    ban_ghi.sort(key=lambda r: (r["event_date"], -abs(r["z"])))
    print(f"   [anomaly] {len(chuoi)} shop -> bỏ qua: {bo_qua}")
    return ban_ghi


# ---------------------------------------------------------------------------
# mart_shop_hour — nhịp đặt hàng theo thứ/giờ. Nền của F31
# ---------------------------------------------------------------------------

def build_mart_shop_hour(db) -> List[Dict[str, Any]]:
    """Nối orders -> order_items -> listings để quy đơn về shop.

    Phải nối vòng vèo vì `orders.shop_id` là float NaN ở CẢ 24.736 dòng — không
    phải chuỗi "nan", nên mọi phép đếm bằng chuỗi đều báo bảng sạch. Kiểm bằng:
        db.orders.distinct("shop_id")  ->  [nan]

    BR-185: thứ/giờ quy về giờ Việt Nam (GMT+7) NGAY Ở ĐÂY, FE không phải đổi nữa.
    `ordered_at` trong dữ liệu mồi đã là giờ địa phương, nên không cộng trừ thêm.
    """
    shop_cua_listing = {l["listing_id"]: l.get("shop_id")
                        for l in db["listings"].find({}, {"_id": 0, "listing_id": 1, "shop_id": 1})}

    don_cua_shop = defaultdict(set)
    sl_cua_don = defaultdict(float)
    tien_cua_don = defaultdict(float)
    for it in db["order_items"].find({}, {"_id": 0, "order_id": 1, "listing_id": 1,
                                          "quantity": 1, "unit_price": 1}):
        shop = shop_cua_listing.get(it.get("listing_id"))
        if not shop:
            continue
        sl = float(it.get("quantity") or 0)
        don_cua_shop[shop].add(it["order_id"])
        sl_cua_don[(shop, it["order_id"])] += sl
        tien_cua_don[(shop, it["order_id"])] += sl * float(it.get("unit_price") or 0)

    luc_dat = {}
    for o in db["orders"].find({}, {"_id": 0, "order_id": 1, "ordered_at": 1, "status": 1}):
        luc_dat[o["order_id"]] = (str(o.get("ordered_at") or ""), o.get("status"))

    gom = defaultdict(lambda: {"orders": 0, "units": 0.0, "revenue": 0.0})
    tong_don = Counter()
    for shop, cac_don in don_cua_shop.items():
        for oid in cac_don:
            khi, _ = luc_dat.get(oid, ("", None))
            try:
                t = datetime.strptime(khi[:19], "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
            k = (shop, t.isoweekday(), t.hour)        # isoweekday: 1=Thứ Hai ... 7=Chủ Nhật
            g = gom[k]
            g["orders"] += 1
            g["units"] += sl_cua_don[(shop, oid)]
            g["revenue"] += tien_cua_don[(shop, oid)]
            tong_don[shop] += 1

    return [{
        "shop_id": shop, "dow": dow, "hour": gio,
        "orders": v["orders"],
        "units": int(round(v["units"])),
        "revenue_vnd": int(round(v["revenue"])),
        "share_pct": round(v["orders"] / tong_don[shop] * 100, 2) if tong_don[shop] else None,
        "tz": "Asia/Ho_Chi_Minh",
    } for (shop, dow, gio), v in sorted(gom.items())]


# ---------------------------------------------------------------------------
# forecast_point — dự báo doanh thu 30/60/90 ngày. Nền của F37
#
# Quyết định E20: dự báo ở CẤP SHOP, không cấp listing. Benchmark M5 của chính
# nhóm đã đo: ARIMA cấp listing MASE 1,12 (THUA cách ngây thơ), cấp nhóm 0,89.
# Chuỗi cấp listing trung vị 41 ngày, chỉ 3 ngày có bán — quá thưa để mô hình hoá.
#
# BR-205 ghi: ARIMA khi lịch sử < 90 ngày, LSTM khi >= 90. Chọn LSTM hay không là
# việc của SPEC-03 (CHƯA LÀM) — job này chạy `seasonal_naive` và `arima`, ghi số
# thật cho cả hai. Bảng so sánh thiếu LSTM là một dòng trong mục Hạn chế; bịa số
# cho LSTM thì tệ hơn nhiều.
# ---------------------------------------------------------------------------

# Lưu MỘT chuỗi dài nhất, API cắt ra 30/60/90 lúc đọc.
#
# Không lưu ba bản riêng vì khoá của forecast_point là
# (entity_type, entity_id, forecast_date) — KHÔNG có horizon_days. Ghi ba bản cho
# cùng ngày thì chúng upsert đè lên nhau: đã mất 7.200/14.400 dòng trong im lặng
# đúng như vậy. Và cắt ra là ĐÚNG về mặt mô hình: ARIMA dự báo 90 bước cho ra
# đúng 30 giá trị đầu giống hệt khi dự báo 30 bước.
HORIZON_MAX = 90
CHU_KY = 7               # nhịp tuần
TOI_THIEU_LICH_SU = 90   # ngày; dưới ngưỡng này không dự báo


def _seasonal_naive(chuoi: List[float], h: int, period: int = CHU_KY) -> List[float]:
    """Mốc so sánh: lặp lại đúng giá trị của chu kỳ trước. Mọi mô hình phải
    thắng được cái này, nếu không thì báo cáo thẳng."""
    return [chuoi[-period + (i % period)] for i in range(h)]


def _arima(chuoi: List[float], h: int):
    try:
        import numpy as np
        from statsmodels.tsa.statespace.sarimax import SARIMAX
        m = SARIMAX(np.asarray(chuoi, dtype=float), order=(1, 1, 1),
                    seasonal_order=(1, 0, 1, CHU_KY),
                    enforce_stationarity=False, enforce_invertibility=False)
        kq = m.fit(disp=False)
        du = kq.get_forecast(steps=h)
        tb = du.predicted_mean
        ci = du.conf_int(alpha=0.05)
        return ([float(x) for x in tb],
                [float(x) for x in ci[:, 0]],
                [float(x) for x in ci[:, 1]])
    except Exception:
        return None


def build_forecast_point(db) -> List[Dict[str, Any]]:
    from app.core.metrics import mase

    chuoi_shop = defaultdict(list)
    for r in db["listing_daily"].aggregate([
        {"$group": {"_id": {"s": "$shop_id", "d": "$date"}, "rev": {"$sum": "$revenue_vnd"}}},
        {"$sort": {"_id.d": 1}},
    ]):
        chuoi_shop[r["_id"]["s"]].append((r["_id"]["d"], float(r["rev"])))

    ban_ghi, bo_qua, so_sanh = [], 0, {}
    for shop, diem in chuoi_shop.items():
        if len(diem) < TOI_THIEU_LICH_SU:
            bo_qua += 1
            continue
        ngay = [d for d, _ in diem]
        y = [v for _, v in diem]

        # Đo trên phần GIỮ LẠI, không đo trên phần đã học — đo trên dữ liệu đã
        # thấy thì mọi mô hình đều "chính xác" và con số vô nghĩa.
        cat = max(TOI_THIEU_LICH_SU, len(y) - 30)
        hoc, giu = y[:cat], y[cat:]
        if len(giu) < 7:
            bo_qua += 1
            continue

        sn_giu = _seasonal_naive(hoc, len(giu))
        mase_sn = mase(giu, sn_giu, hoc, period=CHU_KY)
        ar_giu = _arima(hoc, len(giu))
        mase_ar = mase(giu, ar_giu[0], hoc, period=CHU_KY) if ar_giu else None

        # Chọn mô hình theo SỐ ĐO, không theo ý thích. ARIMA thua mốc ngây thơ thì
        # dùng mốc ngây thơ và ghi rõ — đó là kết quả hợp lệ, không phải thất bại.
        dung_arima = mase_ar is not None and mase_ar < mase_sn
        ten_mo_hinh = "arima" if dung_arima else "seasonal_naive"

        # Bảng so sánh mô hình ghi MỘT LẦN cho mỗi shop, vào model_run.
        # Gắn cả khối này lên từng dòng dự báo thì 46% dung lượng mart là bản sao
        # y hệt nhau — đúng cái đã làm cụm Atlas M0 tràn ngày 21/09.
        so_sanh[shop] = {
            "chosen": ten_mo_hinh,
            "holdout_days": len(giu),
            "seasonal_naive_mase": round(mase_sn, 4),
            "arima_mase": round(mase_ar, 4) if mase_ar is not None else None,
            "lstm_mase": None,      # SPEC-03 chưa chốt — để null, KHÔNG bịa số
        }

        cuoi = datetime.strptime(ngay[-1], "%Y-%m-%d").date()
        for h in (HORIZON_MAX,):
            du = _arima(y, h) if dung_arima else None
            if du:
                tb, lo, hi = du
            else:
                tb = _seasonal_naive(y, h)
                # Dải tin cậy của mốc ngây thơ: ±1,96 độ lệch chuẩn phần dư trong mẫu.
                import statistics
                sai = [y[i] - y[i - CHU_KY] for i in range(CHU_KY, len(y))]
                sd = statistics.pstdev(sai) if len(sai) > 1 else 0.0
                lo = [v - 1.96 * sd for v in tb]
                hi = [v + 1.96 * sd for v in tb]

            for i in range(h):
                ban_ghi.append({
                    "entity_type": "shop",
                    "entity_id": shop,
                    "forecast_date": (cuoi + timedelta(days=i + 1)).isoformat(),
                    "yhat": max(0.0, round(tb[i], 2)),
                    "lo95": max(0.0, round(lo[i], 2)),        # BR-207: kẹp ở 0
                    "hi95": round(hi[i], 2),
                    "model": ten_mo_hinh,
                    "horizon_days": h,
                    "horizon_index": i + 1,       # thứ tự bước, để API cắt cửa sổ
                    # Chỉ 2 số trên mỗi dòng; bảng đầy đủ nằm ở model_run.
                    "mase": round(mase_ar if dung_arima else mase_sn, 4),
                    "mase_baseline": round(mase_sn, 4),
                })

    print(f"   [forecast] {len(chuoi_shop)} shop, bỏ qua {bo_qua} vì lịch sử < {TOI_THIEU_LICH_SU} ngày")
    build_forecast_point.so_sanh = so_sanh      # main() ghi kèm vào model_run
    return ban_ghi


JOBS = {
    "mart_competitor": build_mart_competitor,
    "mart_listing_quality": build_mart_listing_quality,
    "listing_health": build_listing_health,
    "anomaly_event": build_anomaly_event,
    "mart_shop_hour": build_mart_shop_hour,
    "forecast_point": build_forecast_point,
    "niche_score": build_niche_score,
    "mart_demand": build_mart_demand,
    "seasonal_profile": build_seasonal_profile,
}


def main() -> int:
    ap = argparse.ArgumentParser(description="Job đổ dữ liệu vào mart")
    ap.add_argument("bang", nargs="*", help="tên mart cần dựng; bỏ trống thì dùng --all")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="tính nhưng KHÔNG ghi lên Atlas")
    a = ap.parse_args()

    ten = list(JOBS) if a.all else a.bang
    if not ten:
        ap.error("cho tên mart, hoặc --all")
    la = [t for t in ten if t not in JOBS]
    if la:
        print(f"✗ chưa có job cho: {la}. Đang có: {', '.join(JOBS)}")
        return 1

    db = _db()
    print(f"=== DỰNG {len(ten)} MART ===")
    if a.dry_run:
        print("(--dry-run: tính xong in kết quả, KHÔNG ghi lên Atlas)\n")

    for t in ten:
        print(f"── {t}")
        ban_ghi = JOBS[t](db)
        print(f"   tính được {len(ban_ghi):,} dòng")
        if ban_ghi:
            mau = ban_ghi[0]
            print(f"   mẫu: {({k: v for k, v in list(mau.items())[:7]})}")
            thieu = [c for c in MART_SCHEMA[t].get("fields_bat_buoc", []) if c not in mau]
            print(f"   cột bắt buộc: {'ĐỦ' if not thieu else 'THIẾU ' + str(thieu)}")

        if a.dry_run or not ban_ghi:
            continue

        tham_so = {"rows": len(ban_ghi)}
        if getattr(JOBS[t], "so_sanh", None):
            tham_so["model_comparison"] = JOBS[t].so_sanh
        run_id = start_model_run(t, VERSION, tham_so)
        n = save_model_output(t, run_id, VERSION, ban_ghi)
        finish_model_run(run_id, "COMPLETED", {"rows_written": n})
        print(f"   ✓ đã ghi {n:,} dòng  (run_id {run_id})")

    print("\n✅ XONG")
    return 0


if __name__ == "__main__":
    sys.exit(main())
