import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from bson import ObjectId

from app.api.v1 import _live
from app.api.v1._live import LOC_DON_THAT, LOC_SP_THAT, _so, la_shop_live
from app.api.v1._mart import db
from app.api.v1._template import build_meta, mart_not_ready, meta_from_record, not_found, ok
from app.config import settings

MART = "mart_competitor"
MODEL = "competitor-live-1.0"
CUA_SO_BAN_NGAY = 90
CUA_SO_MOI_NGAY = 7
K_CO_NGOT = 10              # giống build_marts.K_CO_NGOT của dữ liệu mồi
DA_GIAO = "DELIVERED"
DANG_BAN = {"status": "PUBLISHED", "is_hidden": {"$ne": True}}   # = PUBLIC_QUERY của BE
SO_CANH_BAO_TOI_DA = 50


def db_live():
    return _live.db_live()      # gọi qua module để test vá `_live.db_live` thì F32–F36 cũng đọc DB giả


def _bay_gio() -> datetime:
    return datetime.now(timezone.utc)


def _ma(x: Any) -> Optional[str]:
    return str(x) if x is not None else None


def _utc(x: Any) -> Optional[datetime]:
    """datetime / chuỗi ISO -> datetime UTC (pymongo trả datetime không kèm múi giờ)."""
    if isinstance(x, str):
        try:
            x = datetime.fromisoformat(x.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(x, datetime):
        return None
    return (x if x.tzinfo else x.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def _iso(x: Any) -> Optional[str]:
    d = _utc(x)
    return d.replace(microsecond=0).isoformat().replace("+00:00", "Z") if d else None


def lam_slug(chu: Any) -> str:
    """'Áo cặp đôi' -> 'ao-cap-doi', dùng khi sản phẩm có tên tag/danh mục mà thiếu id."""
    s = unicodedata.normalize("NFD", str(chu or "").lower().replace("đ", "d"))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def _danh_muc(ma_dm: Optional[str], theo_ma: Dict[str, dict]) -> Tuple[Optional[dict], Optional[dict]]:
    """(cấp 1, lá) của một danh mục. Leo tối đa 5 bậc để dữ liệu hỏng không lặp vô hạn."""
    la = theo_ma.get(ma_dm) if ma_dm else None
    if la is None:
        return None, None
    goc = la
    for _ in range(5):
        cha = theo_ma.get(_ma(goc.get("parent_id")))
        if cha is None:
            break
        goc = cha
    return goc, la


def _khoa_dm(dm: dict) -> str:
    return dm.get("slug") or _ma(dm["_id"])


def tinh_dong_doi_thu(products: Iterable[dict], variants: Iterable[dict], orders: Iterable[dict],
                      reviews: Iterable[dict], wishlists: Iterable[dict], shops: Iterable[dict],
                      categories: Iterable[dict], tags: Iterable[dict],
                      now: Any) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Mỗi sản phẩm đang bán một dòng, cùng cột với `mart_competitor`; thiếu giá hoặc danh mục thì bỏ."""
    now = _utc(now)
    tu = now - timedelta(days=CUA_SO_BAN_NGAY)
    bo_qua: Counter = Counter()

    gia: Dict[str, float] = {}
    for v in variants:
        p, pid = _so(v.get("retail_price")), _ma(v.get("product_id"))
        if v.get("is_active") is not False and pid and p and p > 0:
            gia[pid] = min(p, gia.get(pid, p))

    so_cai: Counter = Counter()
    doanh_thu: Counter = Counter()
    don: Dict[str, set] = defaultdict(set)
    for o in orders:
        tao = _utc(o.get("created_at"))
        if (o.get("order_status") != DA_GIAO or o.get("is_simulated") is True
                or tao is None or not tu <= tao <= now):
            bo_qua["don_khong_tinh"] += 1
            continue
        for it in o.get("items") or []:
            pid, sl = _ma(it.get("product_id")), int(it.get("quantity") or 0)
            if pid and sl > 0:
                so_cai[pid] += sl
                doanh_thu[pid] += sl * (_so(it.get("retail_price")) or 0)
                don[pid].add(_ma(o.get("_id")))

    n_dg: Counter = Counter()
    tong_sao: Counter = Counter()
    for r in reviews:
        sao, pid = _so(r.get("rating")), _ma(r.get("product_id"))
        if pid and sao is not None:
            n_dg[pid] += 1
            tong_sao[pid] += sao

    yeu_thich: Counter = Counter(pid for w in wishlists for pid in {_ma(x) for x in w.get("product_ids") or []})
    shop_theo_ma = {_ma(s["_id"]): s for s in shops}
    dm_theo_ma = {_ma(c["_id"]): c for c in categories}
    tag_theo_ma = {_ma(t["_id"]): t for t in tags}

    dong: List[Dict[str, Any]] = []
    for p in products:
        if p.get("status") != "PUBLISHED" or p.get("is_hidden") is True:
            bo_qua["khong_dang_ban"] += 1
            continue
        pid, sid = _ma(p.get("_id")), _ma(p.get("shop_id"))
        if not sid:
            bo_qua["thieu_shop"] += 1
            continue
        if pid not in gia:
            bo_qua["thieu_gia"] += 1
            continue

        goc, la = _danh_muc(_ma((p.get("category_ids") or [None])[0]), dm_theo_ma)
        if goc is not None:
            ma_dm, ten_dm, ma_loai, ten_loai = _khoa_dm(goc), goc.get("name"), _khoa_dm(la), la.get("name")
        elif p.get("categories") and lam_slug(p["categories"][0]):
            ten_dm = ten_loai = str(p["categories"][0])
            ma_dm = ma_loai = lam_slug(ten_dm)
        else:
            bo_qua["thieu_danh_muc"] += 1
            continue

        tag = {tag_theo_ma[_ma(t)].get("slug") for t in p.get("tag_ids") or [] if _ma(t) in tag_theo_ma} - {None}
        if not tag:
            tag = {lam_slug(t) for t in p.get("tags") or []} - {""}

        shop = shop_theo_ma.get(sid) or {}
        phan_hoi = _so(shop.get("average_response_time_seconds"))
        dong.append({
            "listing_id": pid,      # = product_id: FE mở thẳng trang sức khoẻ sản phẩm (F27–F29)
            "product_id": pid,
            "shop_id": sid,
            "shop_name": shop.get("shop_name"),
            "category_id": ma_dm,
            "category_name": ten_dm,
            "product_type_id": ma_loai,
            "product_type_name": ten_loai,
            "title": p.get("title"),
            "price_vnd": int(round(gia[pid])),
            "est_sales_90d": int(so_cai[pid]),
            "orders_90d": len(don.get(pid, ())),
            "revenue_90d_vnd": int(round(doanh_thu[pid])),
            "favorite_count": int(yeu_thich[pid]),
            "tags": sorted(tag),
            "created_at": _iso(p.get("created_at")),
            # 0 giây là mặc định của model Shop, tức CHƯA ĐO.
            "shop_response_seconds": phan_hoi if phan_hoi and phan_hoi > 0 else None,
            "computed_at": _iso(now),
            "model_version": MODEL,
        })

    # Co ngót đánh giá về trung bình danh mục cấp 1; 0 đánh giá thì null, không lấy 5.0 mặc định.
    tong_dm: Counter = Counter()
    n_dm: Counter = Counter()
    for r in dong:
        tong_dm[r["category_id"]] += tong_sao[r["product_id"]]
        n_dm[r["category_id"]] += n_dg[r["product_id"]]
    for r in dong:
        n = n_dg[r["product_id"]]
        r["n_reviews"] = int(n)
        r["rating_shrunk"] = (round((tong_sao[r["product_id"]] + tong_dm[r["category_id"]] / n_dm[r["category_id"]]
                                     * K_CO_NGOT) / (n + K_CO_NGOT), 2) if n else None)

    theo_dm: Dict[str, List[dict]] = defaultdict(list)
    for r in dong:
        theo_dm[r["category_id"]].append(r)
    for nhom in theo_dm.values():
        nhom.sort(key=lambda r: (-r["est_sales_90d"], -r["revenue_90d_vnd"], r["listing_id"]))   # BR-188
        for i, r in enumerate(nhom, 1):
            r["rank_in_cat"], r["n_in_cat"] = i, len(nhom)

    return dong, dict(bo_qua)


def tinh_canh_bao(dong: Iterable[dict], shops: Iterable[dict], followers: Iterable[dict],
                  now: Any, cua_so_ngay: int = CUA_SO_MOI_NGAY) -> List[Dict[str, Any]]:
    """F36: sản phẩm đăng trong `cua_so_ngay` ngày của shop đang được theo dõi, trùng tag hoặc danh mục (BR-203)."""
    now = _utc(now)
    moc = now - timedelta(days=cua_so_ngay)

    shop_cua_chu = {_ma(s.get("owner_id")): _ma(s["_id"]) for s in shops if s.get("owner_id") is not None}
    theo_doi: Dict[str, set] = defaultdict(set)
    for f in followers:
        bi = _ma(f.get("shop_id"))
        for u in f.get("buyer_ids") or []:
            w = shop_cua_chu.get(_ma(u))
            if w and bi and w != bi:
                theo_doi[w].add(bi)

    tag_ngach: Dict[str, set] = defaultdict(set)
    dm_ngach: Dict[str, set] = defaultdict(set)
    sp_theo_shop: Dict[str, List[dict]] = defaultdict(list)
    for r in dong:
        sp_theo_shop[r["shop_id"]].append(r)
        tag_ngach[r["shop_id"]].update(r.get("tags") or [])
        dm_ngach[r["shop_id"]].add(r.get("category_id"))

    canh_bao: List[Dict[str, Any]] = []
    for w in sorted(theo_doi):
        for bi in sorted(theo_doi[w]):
            for r in sp_theo_shop.get(bi, []):
                dang_luc = _utc(r.get("created_at"))
                if dang_luc is None or not moc <= dang_luc <= now:
                    continue
                trung = sorted(set(r.get("tags") or []) & tag_ngach[w])
                dm = r.get("category_id") if r.get("category_id") in dm_ngach[w] else None
                if not trung and dm is None:
                    continue
                canh_bao.append({
                    "watcher_shop_id": w,
                    "shop_id": bi,
                    "shop_name": r.get("shop_name"),
                    "listing_id": r["listing_id"],
                    "product_id": r.get("product_id"),
                    "title": r.get("title"),
                    "listed_at": _iso(dang_luc),
                    "detected_at": _iso(now),
                    "in_my_niche": True,
                    "matched_tags": trung,
                    "matched_category": dm,
                    "category_name": r.get("category_name") if dm else None,
                    "est_sales_90d": r.get("est_sales_90d") or 0,
                })
    return canh_bao


def _doc_nguon(live, now: datetime) -> Dict[str, List[dict]]:
    products = list(live["products"].find({**DANG_BAN, **LOC_SP_THAT}, {
        "shop_id": 1, "title": 1, "status": 1, "is_hidden": 1, "category_ids": 1, "categories": 1,
        "tag_ids": 1, "tags": 1, "created_at": 1}))
    ma_sp = [p["_id"] for p in products]
    return {
        "products": products,
        "variants": list(live["product_variants"].find(
            {"product_id": {"$in": ma_sp}}, {"product_id": 1, "retail_price": 1, "is_active": 1})),
        "orders": list(live["orders"].find(
            {**LOC_DON_THAT, "order_status": DA_GIAO, "created_at": {"$gte": now - timedelta(days=CUA_SO_BAN_NGAY)}},
            {"order_status": 1, "is_simulated": 1, "created_at": 1,
             "items.product_id": 1, "items.quantity": 1, "items.retail_price": 1})),
        "reviews": list(live["reviews"].find({"product_id": {"$in": ma_sp}}, {"product_id": 1, "rating": 1})),
        "wishlists": list(live["wishlists"].find({}, {"product_ids": 1})),
        "shops": list(live["shops"].find({}, {"shop_name": 1, "owner_id": 1, "average_response_time_seconds": 1})),
        "categories": list(live["categories"].find({}, {"name": 1, "slug": 1, "parent_id": 1})),
        "tags": list(live["tags"].find({}, {"name": 1, "slug": 1})),
    }


def mo_ta_live(ids: Iterable[str]) -> Dict[str, str]:
    oid = [ObjectId(i) for i in ids if ObjectId.is_valid(i)]
    return {str(p["_id"]): p.get("description") or "" for p in db_live()["products"].find({"_id": {"$in": oid}}, {"description": 1})}


def dong_live(now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    # shortcut: tính lại mỗi request từ cả sàn; sàn lớn thì cần cache hoặc job đêm.
    now = now or _bay_gio()
    return tinh_dong_doi_thu(**_doc_nguon(db_live(), now), now=now)[0]


class _Bang(list):
    """Dòng tính tại chỗ, trả lời đúng hai lệnh F32–F34 gọi trên bảng mart (lọc bằng ==)."""

    def find(self, loc, _chieu=None):
        return [r for r in self if all(r.get(k) == v for k, v in loc.items())]

    def distinct(self, truong, loc):
        return list({r.get(truong) for r in self.find(loc)})


def nguon_doi_thu(shop_id: str) -> Dict[str, Any]:
    """Shop thật so với shop thật (tính từ DB sàn), shop mồi đọc `mart_competitor`. Hai miền không trộn."""
    if la_shop_live(shop_id):
        return {"live": True, "bang": _Bang(dong_live()), "collection": "products",
                "mode": "live", "database": settings.MONGO_DB_LIVE}
    coll = db()[MART]
    if coll.estimated_document_count() == 0:
        mart_not_ready(MART)
    return {"live": False, "bang": coll, "collection": MART, "mode": "seed_demo", "database": settings.MONGO_DB_SEED}


def danh_muc_cua_toi(coll, shop_id: str) -> Tuple[List[str], Optional[str], Dict[str, Optional[str]]]:
    """(danh mục shop có hàng, danh mục chính = nơi có nhiều sản phẩm nhất, tên danh mục)."""
    dem: Counter = Counter()
    ten: Dict[str, Optional[str]] = {}
    for r in coll.find({"shop_id": shop_id}, {"_id": 0, "category_id": 1, "category_name": 1}):
        dem[r["category_id"]] += 1
        ten[r["category_id"]] = r.get("category_name")
    return sorted(dem), (min(dem, key=lambda c: (-dem[c], c)) if dem else None), ten


def meta_doi_thu(ng: Dict[str, Any], record: Dict[str, Any], *, scope: str, scope_id: str,
                 sample_size: int) -> Dict[str, Any]:
    return meta_from_record(record, scope=scope, scope_id=scope_id, collection=ng["collection"],
                            database=ng["database"], mode=ng["mode"],
                            attributed_to_live_shop=ng["live"], identity_linked=ng["live"],
                            sample_size=sample_size)


def ten_tag_live(slugs: Iterable[str]) -> Dict[str, str]:
    slugs = sorted({s for s in slugs if s})
    if not slugs:
        return {}
    return {t["slug"]: t.get("name") or t["slug"]
            for t in db_live()["tags"].find({"slug": {"$in": slugs}}, {"_id": 0, "slug": 1, "name": 1})}


def theo_doi_live(shop_id: str, gioi_han: int) -> Dict[str, Any]:
    """F36 · GET cho shop thật. Danh sách theo dõi là follow của sàn (BE ghi); cảnh báo tính tại chỗ."""
    live = db_live()
    shop = live["shops"].find_one({"_id": ObjectId(shop_id)}, {"owner_id": 1})
    if shop is None:
        not_found("shop")

    chu = shop.get("owner_id")
    followers = [] if chu is None else [
        f for f in live["shop_followers"].find({"buyer_ids": chu}, {"shop_id": 1, "buyer_ids": 1})
        if f.get("shop_id") is not None and str(f["shop_id"]) != shop_id]
    ma = [str(f["shop_id"]) for f in followers]
    ten = {str(s["_id"]): s.get("shop_name")
           for s in live["shops"].find({"_id": {"$in": [f["shop_id"] for f in followers]}}, {"shop_name": 1})}

    now = _bay_gio()
    dong = dong_live(now)
    so_sp = Counter(r["shop_id"] for r in dong)
    tag_toi = sorted({t for r in dong if r["shop_id"] == shop_id for t in r["tags"]})
    canh_bao = tinh_canh_bao(dong, [{"_id": shop_id, "owner_id": chu}], followers, now)
    canh_bao.sort(key=lambda a: a["listed_at"] or "", reverse=True)

    return ok({
        "tracked": [{
            "shop_id": m,
            "shop_name": ten.get(m),
            "added_at": None,           # follow của sàn không lưu lúc bắt đầu theo dõi
            "listings_total": so_sp.get(m, 0),
        } for m in ma],
        "slots_used": len(ma),
        "slots_limit": gioi_han,
        "alerts": canh_bao[:SO_CANH_BAO_TOI_DA],
        "alerts_total": len(canh_bao),
        "my_niche_tags": tag_toi,
        "tag_names": ten_tag_live(tag_toi + [t for a in canh_bao for t in a["matched_tags"]]),
        "alerts_computed_at": _iso(now),
        "limitation": (f"Cảnh báo tính lại mỗi lần mở trang, từ sản phẩm đối thủ đăng trong {CUA_SO_MOI_NGAY} "
                       "ngày gần nhất. Bỏ theo dõi một shop thì cảnh báo của shop đó cũng không hiện nữa."),
    }, build_meta(model_version=MODEL, scope="shop", scope_id=shop_id, computed_at=_iso(now),
                  database=settings.MONGO_DB_LIVE, collection="shop_followers", mode="live",
                  attributed_to_live_shop=True, identity_linked=True, sample_size=len(ma)))
