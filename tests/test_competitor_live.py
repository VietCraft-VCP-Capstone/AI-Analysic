"""F32–F36 cho shop thật, chạy trên DB giả trong bộ nhớ."""

import copy
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from bson import ObjectId
from bson.decimal128 import Decimal128
from fastapi import HTTPException

from app.api.v1 import _competitor_live as cl
from app.api.v1 import f32_competitors as f32
from app.api.v1 import f33_shop_comparison as f33
from app.api.v1 import f34_tag_gap as f34
from app.api.v1 import f36_competitor_tracking as f36
from app.api.v1._competitor_live import K_CO_NGOT, lam_slug, tinh_canh_bao, tinh_dong_doi_thu
from app.api.v1._live import la_shop_live

NOW = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
CU = NOW - timedelta(days=30)
MODULES = (f32, f33, f34, f36, cl)
_GOC = {(m, t): getattr(m, t) for m in MODULES for t in ("db", "db_live", "_bay_gio") if hasattr(m, t)}


# A: shop đang xem; B..H: 7 đối thủ ở Áo; I, J: Cốc ly chưa đủ đối thủ; A theo dõi B, B vừa đăng 1 Áo + 1 Tranh.
def _san_mau():
    dm = {}
    for slug, ten, cha in (("ao", "Áo", None), ("coc-ly", "Cốc ly", None), ("tranh", "Tranh", None),
                           ("ao-thun", "Áo thun", "ao"), ("hoodie", "Hoodie", "ao"),
                           ("coc-su", "Cốc sứ", "coc-ly"), ("tranh-canvas", "Tranh canvas", "tranh")):
        dm[slug] = {"_id": ObjectId(), "slug": slug, "name": ten, "parent_id": dm[cha]["_id"] if cha else None}
    tag = {s: {"_id": ObjectId(), "slug": s, "name": n} for s, n in (
        ("ao-thun", "Áo thun"), ("ao-cap-doi", "Áo cặp đôi"), ("qua-tang", "Quà tặng"), ("trang-tri", "Trang trí"))}
    shop = {ma: {"_id": ObjectId(), "owner_id": ObjectId(), "shop_name": f"Shop {ma}",
                 "average_response_time_seconds": giay}
            for ma, giay in (("A", 600), ("E", 0), ("B", 300), ("C", 900), ("D", 1200), ("F", 450),
                             ("G", 1500), ("H", 700), ("I", 800), ("J", 650))}
    products, variants, orders, reviews = [], [], [], []

    def sp(ma_shop, loai, tags, gia, tao=CU, **them):
        p = {"_id": ObjectId(), "shop_id": shop[ma_shop]["_id"], "title": f"{dm[loai]['name']} {ma_shop}{len(products)}",
             "status": "PUBLISHED", "category_ids": [dm[loai]["_id"]], "categories": [dm[loai]["name"]],
             "tag_ids": [tag[t]["_id"] for t in tags], "tags": [tag[t]["name"] for t in tags],
             "created_at": tao, "_gia": gia, **them}
        products.append(p)
        variants.append({"product_id": p["_id"], "retail_price": Decimal128(str(gia)), "is_active": True})
        return p

    def ban(*dong, trang_thai="DELIVERED", tao=None, **them):
        orders.append({"_id": ObjectId(), "order_status": trang_thai, "created_at": tao or NOW - timedelta(days=10),
                       "items": [{"product_id": p["_id"], "quantity": sl, "retail_price": Decimal128(str(p["_gia"]))}
                                 for p, sl in dong], **them})

    a = [sp("A", "ao-thun", ["ao-thun", "qua-tang"], 480000) for _ in range(3)]
    a += [sp("A", "hoodie", ["ao-thun", "qua-tang"], 520000) for _ in range(2)]
    a.append(sp("A", "coc-su", ["qua-tang"], 150000))
    ban((a[0], 2), (a[3], 1))
    reviews.append({"product_id": a[1]["_id"], "rating": 5})

    doi_thu, so_ao_thun = [], 0
    for ma in ("E", "B", "C", "D", "F", "G", "H"):
        for j in range(6):
            if j < 2:
                doi_thu.append(sp(ma, "ao-thun", ["ao-thun"], 150000 + 15000 * so_ao_thun))
                so_ao_thun += 1
            else:
                doi_thu.append(sp(ma, "hoodie", ["ao-thun"], 300000 + 5000 * j))
    for k, p in enumerate(doi_thu[:20]):
        ban((p, 40 - k))
        if k % 2 == 0:
            p["tag_ids"].append(tag["ao-cap-doi"]["_id"])
            p["tags"].append("Áo cặp đôi")
    reviews += [{"product_id": doi_thu[0]["_id"], "rating": s} for s in [5] * 6 + [4] * 6]

    khong_ban = doi_thu[25]
    ban((khong_ban, 5), trang_thai="CANCELLED")
    ban((khong_ban, 7), is_simulated=True)
    ban((khong_ban, 9), tao=NOW - timedelta(days=120))

    an = sp("C", "ao-thun", ["ao-thun"], 200000, is_hidden=True)
    ban((an, 50))
    sp("D", "hoodie", ["ao-thun"], 300000, category_ids=[], categories=[])
    het_gia = sp("F", "hoodie", ["ao-thun"], 300000)
    variants[-1]["is_active"] = False
    for ma in ("I", "I", "J"):
        sp(ma, "coc-su", ["qua-tang"], 120000)
    moi_ao = sp("B", "ao-thun", ["ao-thun"], 250000, tao=NOW - timedelta(days=1))
    sp("B", "tranh-canvas", ["trang-tri"], 300000, tao=NOW - timedelta(days=1))
    sp("B", "ao-thun", ["ao-thun"], 250000, tao=NOW - timedelta(days=1), seed_ref="x")   # dữ liệu mồi trên sàn: bỏ

    followers = [
        {"shop_id": shop["B"]["_id"], "buyer_ids": [shop["A"]["owner_id"]]},
        {"shop_id": shop["C"]["_id"], "buyer_ids": [shop["A"]["owner_id"], ObjectId()]},
        {"shop_id": shop["A"]["_id"], "buyer_ids": [shop["A"]["owner_id"]]},              # tự theo dõi: bỏ qua
    ]
    wishlists = [{"product_ids": [doi_thu[0]["_id"], doi_thu[0]["_id"]]}, {"product_ids": [doi_thu[0]["_id"]]}]

    return {
        "products": products, "variants": variants, "orders": orders, "reviews": reviews,
        "wishlists": wishlists, "shops": list(shop.values()), "categories": list(dm.values()),
        "tags": list(tag.values()), "followers": followers,
        "shop": shop, "a": a, "doi_thu": doi_thu, "an": an, "het_gia": het_gia, "moi_ao": moi_ao,
    }


NGUON = ("products", "variants", "orders", "reviews", "wishlists", "shops", "categories", "tags")


def _tinh(san=None):
    san = san or _san_mau()
    dong, bo_qua = tinh_dong_doi_thu(**{k: [p for p in san[k] if "seed_ref" not in p] for k in NGUON}, now=NOW)
    return san, dong, bo_qua


def _theo_ma(dong):
    return {r["product_id"]: r for r in dong}


def _ma(x):
    return str(x["_id"])


# DB giả trong bộ nhớ: chỉ đủ những lệnh F32–F36 dùng.
def _khop(doc, loc):
    for k, dk in (loc or {}).items():
        gt = doc.get(k)
        if isinstance(dk, dict):
            for op, x in dk.items():
                if op == "$in":
                    ok = any(e in x for e in gt) if isinstance(gt, list) else gt in x
                elif op == "$ne":
                    ok = gt != x
                elif op == "$exists":
                    ok = (k in doc) == x
                elif op == "$gte":
                    ok = gt is not None and gt >= x
                else:
                    raise NotImplementedError(op)
                if not ok:
                    return False
        elif isinstance(gt, list):
            if dk not in gt:
                return False
        elif gt != dk:
            return False
    return True


class _Bang:
    def __init__(self, docs):
        self.docs = [copy.deepcopy(d) for d in docs]

    def find(self, loc=None, _chieu=None):
        return [copy.deepcopy(d) for d in self.docs if _khop(d, loc)]

    def find_one(self, loc=None, _chieu=None):
        ds = self.find(loc)
        return ds[0] if ds else None

    def distinct(self, truong, loc=None):
        out = []
        for d in self.find(loc):
            for x in d.get(truong) if isinstance(d.get(truong), list) else [d.get(truong)]:
                if x not in out:
                    out.append(x)
        return out

    def estimated_document_count(self):
        return len(self.docs)

    def count_documents(self, loc):
        return len(self.find(loc))


class _DB(dict):
    def __missing__(self, k):
        self[k] = _Bang([])
        return self[k]


def _gan(seed, live):
    s = _DB({k: _Bang(v) for k, v in seed.items()})
    l = _DB({k: _Bang(v) for k, v in live.items()})
    for (m, t) in _GOC:
        setattr(m, t, {"db": lambda: s, "db_live": lambda: l, "_bay_gio": lambda: NOW}[t])


def teardown_module():
    for (m, t), goc in _GOC.items():
        setattr(m, t, goc)


def _san_live(bo=None):
    """Nạp sàn mẫu vào DB giả. `bo(dong, san)` -> các product_id bỏ khỏi sàn trước khi nạp."""
    san, dong, _ = _tinh()
    an = set(bo(dong, san)) if bo else set()
    _gan({}, {"products": [p for p in san["products"] if _ma(p) not in an], "product_variants": san["variants"],
              "orders": san["orders"], "reviews": san["reviews"], "wishlists": san["wishlists"],
              "shops": san["shops"], "categories": san["categories"], "tags": san["tags"],
              "shop_followers": san["followers"]})
    return san, _ma(san["shop"]["A"])


# --- Dòng đối thủ tính từ DB sàn ---

def test_chi_dem_don_da_giao_khong_mo_phong_trong_90_ngay():
    san, dong, bo_qua = _tinh()
    theo = _theo_ma(dong)
    assert theo[_ma(san["doi_thu"][25])]["est_sales_90d"] == 0, "đơn huỷ / mô phỏng / quá 90 ngày bị tính"
    assert theo[_ma(san["doi_thu"][25])]["orders_90d"] == 0
    assert bo_qua["don_khong_tinh"] == 3
    assert theo[_ma(san["doi_thu"][0])]["est_sales_90d"] == 40


def test_don_nhieu_san_pham_moi_san_pham_mot_don():
    san, dong, _ = _tinh()
    theo = _theo_ma(dong)
    a0, a3 = theo[_ma(san["a"][0])], theo[_ma(san["a"][3])]
    assert (a0["orders_90d"], a0["est_sales_90d"], a0["revenue_90d_vnd"]) == (1, 2, 960000)
    assert (a3["orders_90d"], a3["est_sales_90d"]) == (1, 1)


def test_loai_san_pham_an_khong_gia_thieu_danh_muc():
    san, dong, bo_qua = _tinh()
    co = set(_theo_ma(dong))
    assert _ma(san["an"]) not in co and _ma(san["het_gia"]) not in co
    assert bo_qua == {"don_khong_tinh": 3, "khong_dang_ban": 1, "thieu_gia": 1, "thieu_danh_muc": 1}, bo_qua


def test_gia_la_bien_the_re_nhat_dang_ban_va_la_so_nguyen():
    san = _san_mau()
    p = san["a"][0]
    san["variants"] += [{"product_id": p["_id"], "retail_price": Decimal128("455000.4"), "is_active": True},
                        {"product_id": p["_id"], "retail_price": Decimal128("1000"), "is_active": False}]
    _, dong, _ = _tinh(san)
    gia = _theo_ma(dong)[_ma(p)]["price_vnd"]
    assert gia == 455000 and isinstance(gia, int), gia


def test_danh_gia_null_khi_chua_co_va_co_ngot_dung_cong_thuc():
    san, dong, _ = _tinh()
    theo = _theo_ma(dong)
    assert theo[_ma(san["a"][0])]["rating_shrunk"] is None, "0 đánh giá phải là null, không phải 5.0"
    moc = 59 / 13
    assert theo[_ma(san["a"][1])]["rating_shrunk"] == round((5 + moc * K_CO_NGOT) / (1 + K_CO_NGOT), 2)
    assert theo[_ma(san["doi_thu"][0])]["rating_shrunk"] == round((54 + moc * K_CO_NGOT) / (12 + K_CO_NGOT), 2)
    assert theo[_ma(san["doi_thu"][0])]["n_reviews"] == 12


def test_thoi_gian_phan_hoi_0_la_chua_do():
    san, dong, _ = _tinh()
    assert {r["shop_response_seconds"] for r in dong if r["shop_id"] == _ma(san["shop"]["E"])} == {None}
    assert {r["shop_response_seconds"] for r in dong if r["shop_id"] == _ma(san["shop"]["A"])} == {600}


def test_yeu_thich_dem_moi_wishlist_mot_lan():
    san, dong, _ = _tinh()
    assert _theo_ma(dong)[_ma(san["doi_thu"][0])]["favorite_count"] == 2


def test_xep_hang_trong_danh_muc_cap_1_loai_la_danh_muc_la():
    _, dong, _ = _tinh()
    ao = sorted((r for r in dong if r["category_id"] == "ao"), key=lambda r: r["rank_in_cat"])
    assert len(ao) == 48, len(ao)
    assert [r["rank_in_cat"] for r in ao] == list(range(1, 49)) and {r["n_in_cat"] for r in ao} == {48}
    ban = [r["est_sales_90d"] for r in ao]
    assert ban == sorted(ban, reverse=True)
    assert {r["product_type_id"] for r in ao} == {"ao-thun", "hoodie"} and {r["category_name"] for r in ao} == {"Áo"}


def test_tag_lay_slug_tu_tag_ids_hoac_lam_tu_ten():
    assert lam_slug("Áo cặp đôi") == "ao-cap-doi" and lam_slug("  Quà Tặng 8/3 ") == "qua-tang-8-3"
    san = _san_mau()
    p = san["a"][0]
    p["tag_ids"], p["tags"] = [], ["Áo cặp đôi"]
    _, dong, _ = _tinh(san)
    assert _theo_ma(dong)[_ma(p)]["tags"] == ["ao-cap-doi"]


def test_canh_bao_chi_san_pham_moi_trung_ngach_cua_shop_dang_theo_doi():
    san, dong, _ = _tinh()
    canh = tinh_canh_bao(dong, san["shops"], san["followers"], NOW)
    assert [(c["watcher_shop_id"], c["product_id"]) for c in canh] == [(_ma(san["shop"]["A"]), _ma(san["moi_ao"]))]
    c = canh[0]
    assert c["matched_tags"] == ["ao-thun"] and c["matched_category"] == "ao" and c["in_my_niche"] is True
    assert c["listed_at"] == "2026-10-14T12:00:00Z", "ngày ra hàng phải là ngày đăng thật"


# --- Endpoint ---

def test_la_shop_live_tach_hai_mien():
    assert la_shop_live(str(ObjectId())) and not la_shop_live("shp_00017")


def test_doc_san_bo_du_lieu_moi_va_san_pham_an():
    san, _ = _san_live()
    dong = cl.dong_live()
    assert len(dong) == len(_tinh()[1]), "dòng đọc từ DB sàn phải khớp phần tính thuần"
    assert not [r for r in dong if r["product_id"] == _ma(san["an"])]


def test_f32_shop_that_chi_so_voi_shop_that_va_co_ma_shop():
    san, A = _san_live()
    r = f32.competitors(shop_id=A, categoryId=None)
    d, m = r["data"], r["meta"]
    assert m["source"]["mode"] == "live" and m["source"]["attributed_to_live_shop"] is True
    assert m["quality"]["identity_linked"] is True and m["computed_at"] == "2026-10-15T12:00:00Z"
    assert d["category_id"] == "ao" and d["category_names"] == {"ao": "Áo", "coc-ly": "Cốc ly"}
    assert len(d["competitors"]) == 20 and all(c["shop_id"] != A for c in d["competitors"])
    ban = [c["est_sales_90d"] for c in d["competitors"]]
    assert ban == sorted(ban, reverse=True) and ban[0] == 40
    assert {c["listing_id"] for c in d["my_listings"]} == {_ma(p) for p in san["a"][:5]}
    assert _ma(san["an"]) not in {c["listing_id"] for c in d["competitors"]}


def test_f32_danh_muc_chua_du_doi_thu_thi_chua_du_du_lieu():
    _, A = _san_live()
    r = f32.competitors(shop_id=A, categoryId="coc-ly")
    assert r["data"] is None and r["meta"]["status"] == "insufficient_data", r
    assert "3 sản phẩm" in r["meta"]["reason"] and "Cốc ly" in r["meta"]["reason"]


def test_f32_shop_moi_tra_y_nhu_truoc():
    dong = [{"listing_id": f"lst_{i}", "shop_id": "shp_00017" if i == 0 else f"shp_{i:05d}",
             "shop_name": f"S{i}", "title": f"T{i}", "category_id": "apparel", "price_vnd": 100000 + i,
             "est_sales_90d": 10 - i, "rating_shrunk": None, "n_reviews": 0, "favorite_count": 0,
             "rank_in_cat": i + 1, "n_in_cat": 7, "computed_at": "2026-10-15T12:00:00Z",
             "model_version": "marts-1.0"} for i in range(7)]
    _gan({"mart_competitor": dong}, {})
    d = f32.competitors(shop_id="shp_00017", categoryId=None)
    assert d["meta"]["source"]["mode"] == "seed_demo" and d["meta"]["source"]["attributed_to_live_shop"] is False
    assert "category_names" not in d["data"] and all("shop_id" not in c for c in d["data"]["competitors"])
    assert "dữ liệu mồi" in d["data"]["note"]


def test_mac_dinh_mo_danh_muc_chinh_khong_theo_chu_cai():
    dong = [{"listing_id": f"lst_{i}", "shop_id": "shp_00017" if i < 3 else f"shp_{i:05d}",
             "category_id": "a-phu" if i == 0 else "z-chinh", "price_vnd": 100000, "est_sales_90d": i,
             "rating_shrunk": None, "n_reviews": 0, "favorite_count": 0, "tags": ["t"],
             "computed_at": "2026-10-15T12:00:00Z", "model_version": "marts-1.0"} for i in range(16)]
    _gan({"mart_competitor": dong}, {})
    assert f32.competitors(shop_id="shp_00017", categoryId=None)["data"]["category_id"] == "z-chinh"
    assert f34.tag_gap(shop_id="shp_00017", categoryId=None)["data"]["category_id"] == "z-chinh"


def test_f33_truc_thieu_du_lieu_la_null_khong_phai_0():
    san, A = _san_live()
    d = f33.shop_comparison(shop_id=A)["data"]
    assert d["segment"] == "ao" and d["segment_name"] == "Áo" and d["axes_missing"] == []
    assert d["me_raw"]["response_speed"] == -10.0, "600 giây = 10 phút"
    i = d["axes"].index("response_speed")
    e = [c for c in d["competitors"] if c["shop_id"] == _ma(san["shop"]["E"])]
    assert e and e[0]["values"][i] is None, "E chưa đo phản hồi: trục phải null, không được 0"
    assert e[0]["raw"]["response_speed"] is None and e[0]["raw"]["listing_count"] == 6, "đối thủ phải kèm số thật"
    assert all(c["values"][i] is not None for c in d["competitors"] if c["shop_id"] != _ma(san["shop"]["E"]))


def test_f34_tag_thieu_lay_ten_tag_cua_san():
    _, A = _san_live()
    d = f34.tag_gap(shop_id=A, categoryId=None)["data"]
    thieu = {t["tag_id"]: t for t in d["missing_tags"]}
    assert "ao-cap-doi" in thieu and thieu["ao-cap-doi"]["name"] == "Áo cặp đôi"
    assert thieu["ao-cap-doi"]["lift"] >= 2.0 and d["signal"]["has_signal"] is True
    assert "ao-thun" not in thieu, "tag A đã có không được vào danh sách thiếu"
    assert d["category_names"]["ao"] == "Áo"
    assert d["tag_names"]["qua-tang"] == "Quà tặng", "tag của chính shop cũng phải có tên có dấu"
    dau = {t["tag_id"]: t for t in d["leader_tags"]}
    assert dau["ao-thun"]["mine"] is True and dau["ao-cap-doi"]["mine"] is False
    assert dau["ao-thun"]["used_by"] == 20 and dau["ao-cap-doi"]["used_by"] == 10


def test_f34_danh_muc_toi_da_20_doi_thu_noi_ro_vi_sao_khong_co_tag():
    def bo(dong, san):      # chỉ giữ 20 sản phẩm đối thủ bán chạy nhất ở Áo
        A = _ma(san["shop"]["A"])
        return [r["product_id"] for r in dong if r["shop_id"] != A and r["category_id"] == "ao" and r["rank_in_cat"] > 20]
    _, A = _san_live(bo)
    d = f34.tag_gap(shop_id=A, categoryId=None)["data"]
    assert d["missing_tags"] == [] and d["signal"]["has_signal"] is False
    assert "chính là cả danh mục" in d["signal"]["note"], d["signal"]["note"]


def test_f36_shop_that_doc_follow_cua_san_va_canh_bao_tinh_tai_cho():
    san, A = _san_live()
    r = f36.danh_sach(shop_id=A)
    d, m = r["data"], r["meta"]
    B, C = _ma(san["shop"]["B"]), _ma(san["shop"]["C"])
    assert m["source"]["mode"] == "live" and m["source"]["collection"] == "shop_followers"
    assert {t["shop_id"] for t in d["tracked"]} == {B, C}, "danh sách theo dõi là follow của sàn, không có chính A"
    assert (d["slots_used"], d["slots_limit"]) == (2, 10)
    assert next(t for t in d["tracked"] if t["shop_id"] == B)["listings_total"] == 8
    assert [a["product_id"] for a in d["alerts"]] == [_ma(san["moi_ao"])]
    assert d["tag_names"]["ao-thun"] == "Áo thun" and d["alerts_computed_at"] == "2026-10-15T12:00:00Z"


def test_f36_shop_that_khong_them_bot_qua_module_ai():
    _, A = _san_live()
    for goi in (lambda: f36.them(shop_id=A, body={"shop_id": "x"}),
                lambda: f36.bo(shop_id=A, body={"shop_id": "x"}, shopId=None)):
        try:
            goi()
            raise AssertionError("shop thật phải bị chặn ghi ở module AI")
        except HTTPException as e:
            assert e.status_code == 400


def test_f35_catalog_trong_thi_so_gia_that_cung_danh_muc():
    from app.api.v1 import f35_pricing as f35

    class _MartTrong:
        def estimated_document_count(self):
            return 0

    sp = [{"product_id": "p1", "title": "Áo thun Hoa sen", "price_vnd": 200000, "product_type_id": "tshirt",
           "type_source": "vi", "handmade_hint": False, "categories": ["Áo thun"]}]
    goc = {k: getattr(f35, k) for k in ("db", "san_pham_live", "gia_cung_danh_muc_live")}
    try:
        f35.db = lambda: {"mart_competitor": _MartTrong()}
        f35.san_pham_live = lambda _sid: sp
        f35.gia_cung_danh_muc_live = lambda _dm, tru_shop=None: sorted(range(100000, 300001, 20000))
        r = f35.pricing(shop_id=str(ObjectId()), productType=None, price=None, productId="p1")
    finally:
        for k, v in goc.items():
            setattr(f35, k, v)
    assert r["data"]["basis_kind"] == "live_category" and r["data"]["percentile"] == 55
    assert r["data"]["limitation"].startswith("Catalog tham chiếu chưa có dữ liệu")
