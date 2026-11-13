"""
Cào giá thị trường 2 lần/ngày + tín hiệu Google Trends cho F42.
Không gọi mạng, không cần MongoDB: dùng collection giả trong bộ nhớ.
"""

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from app.services.f42 import market_crawler as mc
from app.services.f42 import orchestrator
from app.services.f42.comparable_pricing import ComparableIndex, _prep, load_market_rows
from app.services.f42.pricing_engine import round_price
from app.services.f42.schemas import PricingResult
from app.services.f42.trend_signal import apply_demand, match_keyword, momentum_from_series

NOW = datetime(2026, 11, 9, tzinfo=timezone.utc)


# ------------------------------------------------------------------ Mongo giả
def _match(doc, flt):
    for k, cond in flt.items():
        v = doc.get(k)
        if isinstance(cond, dict):
            if "$gte" in cond and not (v is not None and v >= cond["$gte"]):
                return False
        elif v != cond:
            return False
    return True


class _Cursor(list):
    def sort(self, key, direction=1):
        return _Cursor(sorted(self, key=lambda d: d.get(key, 0), reverse=direction == -1))

    def limit(self, n):
        return _Cursor(self[:n])


class FakeCol:
    def __init__(self, docs=None):
        self.docs = list(docs or [])
        self.ops = []

    def find(self, flt=None, proj=None):
        return _Cursor(d for d in self.docs if _match(d, flt or {}))

    def find_one(self, flt=None, proj=None):
        r = self.find(flt)
        return r[0] if r else None

    def update_one(self, flt, update, upsert=False):
        self.ops.append((flt, update, upsert))

    def bulk_write(self, ops, ordered=True):
        self.ops.extend(ops)
        return type("R", (), {"upserted_count": len(ops), "modified_count": 0})()

    def insert_one(self, doc):
        self.docs.append(doc)

    def create_index(self, *a, **k):
        return None


class FakeDB(dict):
    def __missing__(self, name):
        self[name] = FakeCol()
        return self[name]


# ------------------------------------------------------------------ cào & kiểm tra hợp lệ
def _raw(**kw):
    base = {"id": 101, "name": "Nến thơm sáp đậu nành", "price": 150000, "original_price": 180000,
            "quantity_sold": {"value": 12}, "review_count": 3, "rating_average": 4.8,
            "inventory_status": "available", "url_path": "nen-thom-p101.html"}
    base.update(kw)
    return base


def test_parse_valid_item():
    it = mc.parse_tiki_item(_raw(), "nến thơm", NOW)
    assert it["_id"] == "tiki_101" and it["price"] == 150000 and it["sold"] == 12
    assert it["list_price"] == 180000 and it["is_valid"] is True


@pytest.mark.parametrize("bad", [
    {"price": 0}, {"price": 500}, {"price": 999_000_000}, {"name": ""}, {"id": None},
    {"inventory_status": "discontinued"},
])
def test_parse_rejects_unusable(bad):
    assert mc.parse_tiki_item(_raw(**bad), "x", NOW) is None


def test_unsold_item_kept_but_not_valid_evidence():
    it = mc.parse_tiki_item(_raw(quantity_sold=None, review_count=0), "x", NOW)
    assert it is not None and it["is_valid"] is False


def test_build_keywords_dedupes_accents_and_cuts_long_titles():
    kws = mc.build_keywords(["áo thun", "Áo Thun"], ["Ao thun", "Nến thơm sáp đậu nành handmade hương lavender 200g"])
    assert kws == ["áo thun", "nến thơm sáp đậu nành"]


def test_record_seller_query_stores_only_title_head():
    db = FakeDB()
    mc.record_seller_query(db, "Nến thơm sáp đậu nành handmade hương lavender")
    flt, upd, upsert = db["f42_query_log"].ops[0]
    assert flt == {"_id": "nen thom sap dau nanh"} and upsert
    assert upd["$set"]["query"] == "nến thơm sáp đậu nành" and upd["$inc"] == {"count": 1}


def test_run_crawl_continues_after_keyword_error(monkeypatch):
    db = FakeDB()
    monkeypatch.setattr(mc, "seed_keywords", lambda: ["nến thơm", "cốc sứ"])
    sleeps = []

    def fake_fetch(kw, session):
        if kw == "cốc sứ":
            raise TimeoutError()
        return [mc.parse_tiki_item(_raw(), kw, NOW)]

    s = mc.run_crawl(db, fetch=fake_fetch, sleep=sleeps.append)
    assert (s["keywords"], s["items"], s["valid_items"], s["status"]) == (2, 1, 1, "partial")
    assert sleeps == [mc.REQUEST_DELAY_S]                       # nghỉ giữa các request
    op = db["market_price_listing"].ops[0]._doc
    assert op["$push"]["price_history"]["$slice"] == -mc.HISTORY_KEEP
    assert db["collector_run"].docs[0]["job"] == "f42_market_crawl"


def test_max_requests_caps_keywords(monkeypatch):
    monkeypatch.setattr(mc, "seed_keywords", lambda: [f"từ {i}" for i in range(10)])
    calls = []
    mc.run_crawl(FakeDB(), max_requests=3, fetch=lambda kw, s: calls.append(kw) or [], sleep=lambda _: None)
    assert len(calls) == 3


# ------------------------------------------------------------------ nạp giá mới vào bộ so sánh
def test_load_market_rows_only_valid_fresh_and_newest_wins():
    now = datetime.now(timezone.utc)
    db = FakeDB()
    db["external_market_products"] = FakeCol([
        {"_id": 1, "external_id": "tiki_1", "title": "Nến thơm cũ", "price_vnd": 90000, "sold_count": 5},
        {"_id": 2, "external_id": "tiki_2", "title": "Nến chưa ai mua", "price_vnd": 90000, "sold_count": 0, "review_count": 0},
    ])
    db["market_price_listing"] = FakeCol([
        {"_id": "tiki_1", "title": "Nến thơm cũ", "price": 120000, "sold": 7, "is_valid": True, "last_seen_at": now},
        {"_id": "tiki_3", "title": "Nến thơm hết hạn", "price": 80000, "sold": 2, "is_valid": True,
         "last_seen_at": now - timedelta(days=30)},
        {"_id": "tiki_4", "title": "Nến thơm không hợp lệ", "price": 80000, "sold": 0, "is_valid": False, "last_seen_at": now},
    ])
    rows = load_market_rows(db)
    assert [(r["title"], r["price"]) for r in rows] == [("Nến thơm cũ", 120000)]


def _index():
    rows = []
    for i in range(45):  # đủ để nguồn Tiki cũ tự lấp đầy top_k
        rows.append(("home", f"Nến thơm ly thuỷ tinh hương {i} mẫu {i}", 50_000 + i * 100, 1))
    rows += [("home", "Cốc sứ trắng", 40_000, 1), ("home", "Cốc sứ đen", 42_000, 1)]
    return ComparableIndex(pd.DataFrame(rows, columns=["group", "title", "price", "sold"]))


def _snap(idx, titles_prices, extra=None):
    rows = [{"title": t, "prep": _prep(t),
             "price": p, "sold": 3, "category_ids": [], **(extra or {})} for t, p in titles_prices]
    return rows, idx.vectorizer.transform([r["prep"] for r in rows])


def test_live_and_fresh_rows_included_even_when_old_tiki_fills_top_k():
    idx = _index()
    idx._live = _snap(idx, [("Nến thơm ly thuỷ tinh hương 1 mẫu 1 handmade", 199_000)])
    idx._market = _snap(idx, [("Nến thơm ly thuỷ tinh hương 2 mẫu 2", 150_000)])
    sources = {c.source for c in idx.search("Nến thơm ly thuỷ tinh hương 1 mẫu 1")}
    assert {"vietcraft", "tiki_fresh"} <= sources


def test_fresh_price_replaces_same_old_listing():
    idx = _index()
    idx._market = _snap(idx, [("Nến thơm ly thuỷ tinh hương 2 mẫu 2", 150_000)])
    hits = [c for c in idx.search("Nến thơm ly thuỷ tinh hương 2 mẫu 2") if c.title.endswith("2 mẫu 2")]
    assert [(c.source, c.price) for c in hits] == [("tiki_fresh", 150_000)]


# ------------------------------------------------------------------ Google Trends
def test_match_keyword_longest_subset():
    kws = ["cốc", "cốc in hình", "áo thun", "in áo thun"]
    assert match_keyword("Cốc in hình mèo cute", kws) == "cốc in hình"
    assert match_keyword("Cốc sứ in hình mèo", kws) == "cốc"            # "cốc in hình" không liền nhau
    assert match_keyword("Áo thun cotton in hình", kws) == "áo thun"    # không nhầm "in áo thun"
    assert match_keyword("Tranh thêu tay", kws) is None


def _series(prev, recent):
    pts = []
    for d in range(84, 28, -1):
        pts.append({"observed_on": NOW.replace(tzinfo=None) - timedelta(days=d), "scaled": prev})
    for d in range(28, 0, -1):
        pts.append({"observed_on": NOW.replace(tzinfo=None) - timedelta(days=d), "scaled": recent})
    return pts


def test_momentum_and_noise_guard():
    today = NOW.replace(tzinfo=None)
    assert momentum_from_series(_series(20, 30), today)["momentum"] == 1.5
    assert momentum_from_series(_series(2, 6), today) is None          # quá ít người tìm → nhiễu
    assert momentum_from_series(_series(20, 30)[:30], today) is None   # dữ liệu thưa


@pytest.mark.parametrize("m,expected,direction", [(1.5, 125_000, "up"), (0.6, 75_000, "down"), (1.05, 100_000, "flat")])
def test_apply_demand_stays_inside_range(m, expected, direction):
    out = apply_demand(50_000, 100_000, 150_000, {"keyword": "nến thơm", "momentum": m}, round_price)
    assert (out["price"], out["direction"]) == (expected, direction)
    assert 50_000 <= out["price"] <= 150_000


def test_demand_never_below_cost_floor_and_not_for_cost_plus(monkeypatch):
    monkeypatch.setattr(orchestrator, "demand_signal", lambda db, t: {"keyword": "nến", "momentum": 0.5})
    res = PricingResult(method="comparables", p25=50_000, p50=100_000, p75=150_000, suggested_price=100_000)
    orchestrator._apply_demand_signal(res, object(), "nến", blank_cost=60_000)
    assert res.suggested_price == round_price(60_000 * 1.3)         # (50k+100k)/2=75k < giá vốn × 1,3
    assert res.demand_signal["direction"] == "down" and "Google Trends" in res.explanation
    cp = PricingResult(method="cost_plus", p25=50_000, p50=100_000, p75=150_000, suggested_price=100_000)
    orchestrator._apply_demand_signal(cp, object(), "nến", blank_cost=0)
    assert cp.suggested_price == 100_000 and cp.demand_signal is None


# ------------------------------------------------------------------ lịch chạy
def test_scheduler_registers_crawl_at_6_and_18(monkeypatch):
    import apscheduler.schedulers.background as bg
    from app.core import f29_scheduler

    added = {}

    class FakeScheduler:
        def __init__(self, *a, **k):
            pass

        def add_job(self, func, trigger=None, **kw):
            added[kw.get("id")] = trigger

        def start(self):
            pass

    monkeypatch.setattr(bg, "BackgroundScheduler", FakeScheduler)
    monkeypatch.setattr(f29_scheduler, "_scheduler", None)
    monkeypatch.setattr(f29_scheduler, "needs_full_rescan", lambda db: False)
    monkeypatch.setattr(f29_scheduler, "db_live", lambda: None)
    f29_scheduler.start_scheduler()
    trig = str(added["f42_market_crawl"])
    assert "hour='6,18'" in trig and "minute='0'" in trig


# ------------------------------------------------------------------ cào theo yêu cầu khi chưa có dữ liệu
def test_fetch_on_demand_saves_valid_items():
    db = FakeDB()
    called = []
    ok = mc.fetch_on_demand(db, "Ốp lưng điện thoại silicone dẻo trong suốt",
                            fetch=lambda kw: called.append(kw) or [mc.parse_tiki_item(_raw(), kw, NOW)])
    assert ok is True and called == ["ốp lưng điện thoại silicone"]
    assert len(db["market_price_listing"].ops) == 1
    flt, upd, _ = db["f42_query_log"].ops[0]
    assert flt == {"_id": "op lung dien thoai silicone"} and "last_crawled" in upd["$set"]


def test_fetch_on_demand_respects_cooldown_and_errors():
    db = FakeDB()
    db["f42_query_log"] = FakeCol([{"_id": "op lung dien thoai", "last_crawled": datetime.now(timezone.utc)}])
    called = []
    assert mc.fetch_on_demand(db, "Ốp lưng điện thoại", fetch=lambda kw: called.append(kw) or []) is False
    assert called == []                                                   # trong 12h: không cào lại

    def boom(kw):
        raise TimeoutError()
    assert mc.fetch_on_demand(FakeDB(), "Ốp lưng điện thoại", fetch=boom) is False   # Tiki chậm: không vỡ gợi ý


def test_industry_tags_only_kept_when_about_the_product(monkeypatch):
    from app.services.f42.ai_engine import MarketAIAdvisor
    from app.services.f42.external_market import ExternalMarketProvider
    from app.services.f42.schemas import SuggestionRequest
    from app.services.f42 import config as f42_config

    monkeypatch.setattr(MarketAIAdvisor, "is_gemini_available", classmethod(lambda cls: False))
    monkeypatch.setattr(f42_config, "GOOGLE_SUGGEST_ENABLED", False)
    monkeypatch.setattr(ExternalMarketProvider, "get_lifted_keywords", classmethod(lambda cls, c, t, top_n=8: [
        {"keyword": "Tập Khăn", "lift": 3.0, "freq": 14}, {"keyword": "Bdn01 54X54Cm", "lift": 2.0, "freq": 14},
        {"keyword": "ốp lưng chống sốc", "lift": 1.5, "freq": 9},
    ]))
    res = orchestrator.F42Orchestrator.execute(SuggestionRequest(keywords="Ốp lưng điện thoại"), db_live_override=False)
    assert "ốp lưng chống sốc" in res.suggested_tags
    assert "Tập Khăn" not in res.suggested_tags and "Bdn01 54X54Cm" not in res.suggested_tags


def test_mined_tags_skip_fragments_and_risky_claims():
    from app.services.f42.comparable_pricing import Comparable
    titles = ["Ốp lưng điện thoại dẻo trong suốt hàng chính hãng dành cho iPhone",
              "Ốp lưng điện thoại dẻo trong suốt chống sốc dành cho iPhone",
              "Ốp lưng điện thoại dẻo trong suốt hàng chính hãng dành cho Samsung"]
    comps = [Comparable(t, 50_000, 0.8, "tiki") for t in titles]
    tags = [t for t, _, _ in ComparableIndex.mine_keywords(comps, "Ốp lưng điện thoại", top_n=20)]
    assert any("trong suốt" in t for t in tags)
    for bad in ("lưng điện", "dành cho", "cho iphone", "chính hãng"):
        assert not any(bad in t for t in tags), (bad, tags)


# ------------------------------------------------------------------ đúng mẫu máy (iPhone 18 Pro Max ≠ Realme 6 triệu)
def _phone_index():
    # Giống dữ liệu thật: tên hãng (iphone) HIẾM trong toàn tập (< 0,5%), bộ tách từ vẫn học được "18", "pro", "max"
    colors = ["đen", "trắng", "xanh", "đỏ", "nâu", "kem", "vàng", "hồng"]
    kinds = ["Áo thun cotton", "Túi xách da", "Giày sneaker", "Quần jean", "Váy maxi", "Mũ lưỡi trai"]
    rows = [("fashion", f"{kinds[i % 6]} {colors[i % 8]} size {i % 5}", 90_000 + (i % 50) * 1000, 5) for i in range(600)]
    rows += [("fashion", "Áo thun pro max 18 tuổi", 120_000, 5), ("fashion", "Váy max 18 tầng pro", 150_000, 5)]
    rows += [("bags", "Túi đựng iphone da bò", 200_000, 5), ("bags", "Bao da iphone cao cấp", 250_000, 5)]
    rows += [("bags", "Ốp lưng da cao cấp", 90_000, 5), ("bags", "Ốp lưng silicone dẻo", 60_000, 5)]
    # gia dụng: đủ để bộ tách từ biết "chảo chống dính", "bát gốm", "bát nhựa melamine"; "tefal" vẫn hiếm
    rows += [("home", f"Chảo chống dính đáy từ {i}cm", 200_000, 5) for i in (20, 24, 28)]
    rows += [("home", "Bát gốm men trắng", 50_000, 5), ("home", "Bát gốm sứ hoa", 60_000, 5),
             ("home", "Bát nhựa melamine trẻ em", 30_000, 5), ("home", "Bát nhựa melamine cao cấp", 35_000, 5),
             ("home", "Chảo Tefal cũ", 300_000, 5), ("home", "Nồi Tefal", 500_000, 5)]
    return ComparableIndex(pd.DataFrame(rows, columns=["group", "title", "price", "sold"]))


def test_model_signature():
    idx = _phone_index()
    assert idx.model_signature("điện thoại iphone 18 promax") == ["iphone", "18", "pro", "max"]
    assert idx.model_signature("Samsung Galaxy A17 8GB/128GB") == ["samsung", "galaxy", "a17"]
    assert idx.model_signature("Bình giữ nhiệt inox 304 500ml") == []     # không có hãng → so theo loại
    assert idx.model_signature("ao thun 2 mau") == []                      # gõ không dấu, "2" không phải đời máy
    assert idx.model_signature("Áo thun cotton in hình") == []


def test_exact_model_only_and_single_bestseller_is_enough():
    idx = _phone_index()
    idx._market = _snap(idx, [
        ("Điện Thoại Realme C85 8GB/128GB - Hàng Chính Hãng", 5_999_000),
        ("Điện thoại Xiaomi Redmi 17 (4GB/128GB)", 5_990_000),
        ("Điện Thoại Samsung Galaxy A17 8GB/128GB", 5_999_000),
        ("Apple iPhone 18 Pro", 37_990_000),
        ("Apple iPhone 18 Pro Max", 40_250_000),
    ], extra={"sold": 505})
    e = idx.estimate("điện thoại iphone 18 promax")
    assert [c.title for c in e.comparables] == ["Apple iPhone 18 Pro Max"]   # không lấy Realme/Redmi, không lấy bản Pro
    assert e.p50 == 40_250_000 and e.confidence == "medium"
    assert e.detected_product == "iPhone 18 Pro Max"


def test_exact_model_needs_real_sales():
    idx = _phone_index()
    idx._market = _snap(idx, [("Apple iPhone 18 Pro Max", 40_250_000)], extra={"sold": 3})
    assert not idx.estimate("iphone 18 pro max").usable                       # 1 tin, mới bán 3 cái: chưa đủ căn cứ


def test_accessory_for_model_keeps_type_in_name():
    idx = _phone_index()
    idx._market = _snap(idx, [
        ("Ốp lưng iPhone 18 Pro Max trong suốt chống sốc 18 Pro Max", 120_000),
        ("Ốp lưng iPhone 18 Pro Max silicone", 150_000),
        ("Ốp lưng iPhone 18 Pro Max da", 200_000),
        ("Apple iPhone 18 Pro Max", 40_250_000),
    ], extra={"sold": 30})
    e = idx.estimate("Ốp lưng iPhone 18 Pro Max")
    assert e.p50 < 1_000_000 and all("Ốp" in c.title for c in e.comparables)   # không lấy giá máy để định giá ốp
    assert e.detected_product == "Ốp lưng iPhone 18 Pro Max"


# ------------------------------------------------------------------ lọc theo bậc (kiểm thử 72 sản phẩm thật)
def test_model_variant_must_match_exactly():
    idx = _phone_index()
    idx._market = _snap(idx, [("Apple iPhone 17 Pro", 30_990_000), ("Apple iPhone 17 Pro Max", 32_550_000),
                              ("Ốp chống sốc cho iPhone 17 Pro Max", 29_000)], extra={"sold": 500})
    assert not idx.estimate("iPhone 17").usable                       # không lấy giá bản Pro/Pro Max cho bản thường
    e = idx.estimate("iPhone 17 Pro Max 256GB")
    assert [c.title for c in e.comparables] == ["Apple iPhone 17 Pro Max"]   # "Ốp..." là phụ kiện, không lẫn vào


def test_brand_tier_then_fallback_with_note():
    idx = _phone_index()
    pans = [("Chảo chống dính Elmich EL1", 240_000), ("Chảo chống dính Elmich EL2", 250_000), ("Chảo chống dính Sunhouse SH1", 200_000)]
    idx._market = _snap(idx, pans + [("Chảo chống dính Tefal Easy", 800_000), ("Chảo chống dính Tefal Day", 850_000),
                                     ("Chảo chống dính Tefal Expertise", 900_000)])
    e = idx.estimate("Chảo chống dính Tefal 24cm")
    assert all("Tefal" in c.title for c in e.comparables) and e.match_note is None
    idx._market = _snap(idx, pans)                                    # chưa có dữ liệu Tefal
    e2 = idx.estimate("Chảo chống dính Tefal 24cm")
    assert e2.usable and e2.confidence == "low" and "Tefal" in e2.match_note


def test_material_tier():
    idx = _phone_index()
    idx._market = _snap(idx, [("Bát gốm Bát Tràng men rạn", 300_000), ("Bát gốm sứ vẽ tay", 350_000), ("Bát gốm men lam", 320_000),
                              ("Bát nhựa melamine trắng", 35_000), ("Bát nhựa melamine hoa", 40_000), ("Bát nhựa melamine xanh", 45_000)])
    assert idx.estimate("Bát nhựa melamine").p50 < 100_000
    assert idx.estimate("Bát gốm Bát Tràng").p50 > 200_000


def test_repeated_variants_capped_but_different_prices_kept():
    from app.services.f42.comparable_pricing import Comparable
    same = [Comparable(f"Chuột game không dây Lightspeed Logitech G304 bản {i}", p, 0.8, "tiki")
            for i, p in enumerate([799_000, 842_000, 799_000, 826_000])]
    assert len(ComparableIndex._diversify(same)) == 2                 # 4 biến thể cùng giá ~ → giữ 2
    spread = [Comparable(f"Đồng hồ nam dây da mặt tròn mẫu {i}", p, 0.8, "tiki") for i, p in enumerate([300_000, 600_000, 900_000])]
    assert len(ComparableIndex._diversify(spread)) == 3              # khác giá nhiều là bằng chứng riêng
