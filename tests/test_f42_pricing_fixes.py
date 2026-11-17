"""
Kiểm thử các lỗi đã sửa của F42 (giá thật từ product_variants, bỏ bảng giá cứng,
Gemini không định giá, validator nội dung, lợi nhuận, nhãn nguồn từ khóa).

Dùng Mongo giả lập trong bộ nhớ — không cần MongoDB, không cần mạng.
"""

import re
from decimal import Decimal
from typing import Any, Dict, List

import pytest
from bson import Decimal128, ObjectId

from app.services.f42 import market_aggregator, orchestrator
from app.services.f42.ai_engine import MarketAIAdvisor
from app.services.f42.comparable_pricing import _ACCESSORY_MARKERS, _contains, _prep
from app.services.f42.content_validator import find_violations, validate_content
from app.services.f42.orchestrator import F42Orchestrator
from app.services.f42.pricing_engine import fetch_live_listings
from app.services.f42.schemas import SuggestionRequest


# --------------------------------------------------------------------------- Mongo giả
def _get(doc: Dict[str, Any], key: str) -> Any:
    return doc.get(key)


def _match_value(val: Any, cond: Any) -> bool:
    if isinstance(cond, dict) and any(k.startswith("$") for k in cond):
        for op, arg in cond.items():
            if op == "$ne" and (arg in val if isinstance(val, list) else val == arg):
                return False
            if op == "$nin" and val in arg:
                return False
            if op == "$in" and val not in arg:
                return False
            if op == "$regex":
                flags = re.I if "i" in cond.get("$options", "") else 0
                vals = val if isinstance(val, list) else [val]
                if not any(isinstance(v, str) and re.search(arg, v, flags) for v in vals):
                    return False
        return True
    if isinstance(val, list):
        return cond in val
    return val == cond


def _match(doc: Dict[str, Any], query: Dict[str, Any]) -> bool:
    for k, cond in query.items():
        if k == "$and":
            if not all(_match(doc, q) for q in cond):
                return False
        elif k == "$or":
            if not any(_match(doc, q) for q in cond):
                return False
        elif not _match_value(_get(doc, k), cond):
            return False
    return True


class _Cursor(list):
    def limit(self, n: int) -> "_Cursor":
        return _Cursor(self[:n])


class FakeCollection:
    def __init__(self, docs: List[Dict[str, Any]]):
        self.docs = docs

    def find(self, query: Dict[str, Any] = None, projection: Dict[str, Any] = None) -> _Cursor:
        return _Cursor([d for d in self.docs if _match(d, query or {})])

    def aggregate(self, pipeline: List[Dict[str, Any]]):
        rows = self.docs
        for stage in pipeline:
            if "$match" in stage:
                rows = [d for d in rows if _match(d, stage["$match"])]
            elif "$group" in stage:
                key = stage["$group"]["_id"].lstrip("$")
                field = stage["$group"]["min_price"]["$min"].lstrip("$")
                grouped: Dict[Any, Any] = {}
                for d in rows:
                    v = d[field].to_decimal() if hasattr(d[field], "to_decimal") else Decimal(d[field])
                    k = d[key]
                    grouped[k] = min(grouped.get(k, v), v)
                rows = [{"_id": k, "min_price": Decimal128(v)} for k, v in grouped.items()]
        return iter(rows)


class FakeDB(dict):
    def __getitem__(self, name: str) -> FakeCollection:
        return self.setdefault(name, FakeCollection([]))


def _product(title: str, prices: List[int], **over: Any):
    pid = ObjectId()
    doc = {
        "_id": pid, "title": title, "status": "PUBLISHED", "is_hidden": False,
        "listing_status": "ACTIVE", "moderation_status": "APPROVED",
        "tags": ["áo thun", "quà tặng"], "categories": [], "category_ids": [], "materials": [],
    }
    doc.update(over)
    variants = [
        {"_id": ObjectId(), "product_id": pid, "retail_price": Decimal128(str(p)), "is_active": True}
        for p in prices
    ]
    return doc, variants


def _db(items) -> FakeDB:
    db = FakeDB()
    prods, vars_ = [], []
    for title, prices, over in items:
        p, v = _product(title, prices, **over)
        prods.append(p)
        vars_.extend(v)
    db["products"] = FakeCollection(prods)
    db["product_variants"] = FakeCollection(vars_)
    db["categories"] = FakeCollection([])
    db["banned_keywords"] = FakeCollection([])
    db["tags"] = FakeCollection([])
    return db


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    """Không gọi mạng, không Gemini, không cache chéo giữa các test."""
    monkeypatch.setattr(MarketAIAdvisor, "is_gemini_available", classmethod(lambda cls: False))
    monkeypatch.setattr(market_aggregator.config, "GOOGLE_SUGGEST_ENABLED", False)
    monkeypatch.setattr(orchestrator.ComparableIndex, "get", classmethod(lambda cls: None))
    monkeypatch.setattr(orchestrator, "_cached_categories", [])
    monkeypatch.setattr(orchestrator, "_cached_banned", set())


SHIRTS = [
    (f"Áo thun cotton in hình mèo mẫu {i}", [150_000 + i * 15_000, 260_000], {}) for i in range(7)
]


# --------------------------------------------------------------------------- giá thật
def test_live_listings_use_variant_price_and_public_filter():
    db = _db(SHIRTS + [
        ("Áo thun cotton in hình mèo bản nháp", [9_000_000], {"status": "DRAFT"}),
        ("Áo thun cotton in hình mèo chưa duyệt", [9_000_000], {"moderation_status": "PENDING"}),
        ("Áo thun cotton in hình mèo đã ẩn", [9_000_000], {"is_hidden": True}),
    ])
    rows = fetch_live_listings(db)
    assert len(rows) == 7                        # bản nháp / chưa duyệt / ẩn bị loại
    assert all(r["price"] < 1_000_000 for r in rows)
    assert min(r["price"] for r in rows) == 150_000  # giá = biến thể rẻ nhất, 1 giá / sản phẩm


def test_internal_similar_pricing_from_real_variants():
    db = _db(SHIRTS + [("Nến thơm sáp đậu nành", [99_000], {})])
    res = F42Orchestrator.execute(SuggestionRequest(title="Áo thun cotton in hình mèo"), db_live_override=db)
    assert res.pricing.method == "internal_similar"
    assert res.pricing.sample_size_after_outlier_filter == 7
    assert 150_000 <= res.pricing.suggested_price <= 260_000
    assert res.pricing_insight["market_sample_count"] == 7
    assert all("Nến" not in c["title"] for c in res.pricing_insight["comparables"])


def test_no_hardcoded_brand_price_for_accessory():
    """Trước đây: ốp lưng iPhone giá vốn 30k → đề xuất 34.990.000đ."""
    res = F42Orchestrator.execute(
        SuggestionRequest(title="Ốp lưng iPhone 15 Pro Max in hình hoa", blankCost=30_000), db_live_override=_db([])
    )
    assert res.pricing.method == "cost_plus"
    assert 30_000 < res.pricing.suggested_price < 100_000
    assert not hasattr(market_aggregator, "BRAND_SEGMENT_BENCHMARKS")


def test_cost_floor_kept_when_market_below_cost():
    res = F42Orchestrator.execute(
        SuggestionRequest(title="Áo thun cotton in hình mèo", blankCost=300_000), db_live_override=_db(SHIRTS)
    )
    assert res.pricing.suggested_price >= 390_000
    assert res.pricing_insight["recommended_price"] >= 390_000
    assert any("giá vốn" in w for w in res.pricing.warnings)
    assert any("cao hơn 75%" in w for w in res.pricing.warnings)
    assert "173.000đ" in res.pricing.explanation  # nêu đúng giá thị trường thật (P25 = 172.500đ, làm tròn nửa lên)


def test_no_invented_profit_without_blank_cost():
    res = F42Orchestrator.execute(SuggestionRequest(title="Áo thun cotton in hình mèo"), db_live_override=_db(SHIRTS))
    assert res.pricing.suggested_price > 0
    assert res.pricing_insight["recommended_markup"] == 0
    assert res.pricing_insight["evidence_stats"]["profit"] == 0


def test_cost_plus_uses_target_margin():
    res = F42Orchestrator.execute(
        SuggestionRequest(title="Tượng gốm điêu khắc độc bản", blankCost=100_000, targetMargin=0.5),
        db_live_override=_db([]),
    )
    assert res.pricing.method == "cost_plus"
    assert res.pricing.suggested_price == 150_000


# --------------------------------------------------------------------------- Gemini
def test_gemini_never_sets_price_and_claims_are_removed(monkeypatch):
    monkeypatch.setattr(MarketAIAdvisor, "is_gemini_available", classmethod(lambda cls: True))
    fake = {
        "detected_product": "Áo thun",
        "detected_category": "Thời trang",
        "pricing": {"low": 90_000_000, "recommended": 99_000_000, "high": 120_000_000},
        "titles": [
            "Áo thun in hình mèo chính hãng cotton 100% cao cấp",
            "Áo thun in hình mèo dễ thương cho bạn trẻ năng động",
            "Áo thun in hình mèo phong cách tối giản dễ phối đồ",
            "ÁO THUN IN HÌNH MÈO SIÊU ĐẸP HÀNG MỚI VỀ",
        ],
        "description": {
            "intro": "Áo thun in hình mèo, an toàn sức khỏe cho mọi làn da.",
            "specs": [{"label": "Chất liệu", "value": "Cotton 100%"}, {"label": "Loại", "value": "Áo thun"}],
            "highlights": ["Hình in mèo dễ thương", "Bảo hành 12 tháng"],
            "usage_guide": "Giặt nước lạnh.",
            "warranty_policy": "Đổi trả trong 7 ngày.",
        },
        "tags": ["áo thun mèo", "áo thun chính hãng"],
    }
    monkeypatch.setattr(MarketAIAdvisor, "call_gemini_analysis", classmethod(lambda cls, **kw: fake))
    res = F42Orchestrator.execute(SuggestionRequest(title="Áo thun in hình mèo"), db_live_override=_db([]))

    assert res.pricing.suggested_price == 0               # không có dữ liệu, không giá vốn → không gợi ý
    assert res.content.source == "llm_gemini"
    joined = " ".join(res.suggested_titles + [res.seo_description] + res.suggested_tags).lower()
    for bad in ("chính hãng", "cotton", "an toàn sức khỏe", "bảo hành", "đổi trả", "100% hình ảnh"):
        assert bad not in joined, bad
    assert all(not t.isupper() for t in res.suggested_titles)
    assert res.content.description.care_guide is None      # chưa khai báo chất liệu
    assert res.content.warnings


# --------------------------------------------------------------------------- validator
def test_validator_vietnamese_word_boundaries():
    seller = "Áo len cổ lọ"
    assert not find_violations("Mặc lên rất ấm, hợp giới trẻ, may mặc tỉ mỉ", seller, set())
    assert find_violations("Áo len cổ lọ chất cotton", seller, set()) == ["unsupported_material:cotton"]
    assert not find_violations("Áo len cổ lọ màu gỗ", seller, set())
    assert find_violations("Bình gốm chính hãng", "binh gom", set()) == ["unsupported_claim:chính hãng"]
    assert not find_violations("Bình gốm thủ công", "binh gom thu cong", set())   # seller gõ không dấu


def test_validator_keeps_declared_material_and_care_guide():
    data, errors = validate_content(
        {"titles": ["Áo len cổ lọ dệt kim cho mùa đông ấm áp"],
         "description": {"intro": "", "specs": [{"label": "Chất liệu", "value": "len"}],
                         "highlights": [], "usage_guide": "Giặt tay nước lạnh."}},
        "Áo len cổ lọ len", set(), material_declared=True,
    )
    assert data["titles"] and data["description"]["usage_guide"]
    assert data["description"]["specs"] == [{"label": "Chất liệu", "value": "len"}]


# --------------------------------------------------------------------------- khác
def test_description_has_no_default_commitments():
    res = F42Orchestrator.execute(SuggestionRequest(title="Cốc gốm vẽ tay"), db_live_override=False)
    text = res.seo_description.lower()
    for bad in ("100% hình ảnh thực tế", "kiểm định chất lượng", "đổi trả", "chính sách bán hàng"):
        assert bad not in text
    assert not res.seo_description.splitlines()[0].isupper()


@pytest.mark.parametrize("title", ["Áo võ thuật cotton", "Tất cả quà tặng gốm", "Vở ghi chép bìa da"])
def test_accessory_markers_no_false_positive(title):
    prep = _prep(title)
    assert not [m for m in _ACCESSORY_MARKERS if _contains(prep, m)]


def test_google_suggest_not_labelled_as_trends(monkeypatch):
    monkeypatch.setattr(
        orchestrator.MarketDataAggregator, "fetch_google_trending_data",
        classmethod(lambda cls, **kw: {"suggest_keywords": ["áo thun mèo nam"], "trend_keywords": [],
                                       "trending_keywords": ["áo thun mèo nam"], "search_signals": [],
                                       "summary_text": ""}),
    )
    res = F42Orchestrator.execute(SuggestionRequest(title="Áo thun in hình mèo"), db_live_override=_db([]))
    kw = next(k for k in res.trending_keywords if k["keyword"] == "áo thun mèo nam")
    assert kw["growth"] == "Gợi ý Google" and kw["is_hot"] is False and kw["source"] == "google_suggest"


def test_comparables_pricing_cost_floor_explanation():
    from app.services.f42.comparable_pricing import Comparable, ComparableEstimate
    from app.services.f42.pricing_engine import pricing_from_comparables

    comps = [Comparable(title=f"Ly gốm men lam {i}", price=80_000 + i * 5_000, similarity=0.6, source="tiki")
             for i in range(6)]
    est = ComparableEstimate(comparables=comps, p25=85_000, p50=95_000, p75=105_000, p90=110_000,
                             n_used=6, mean_similarity=0.6, confidence="high")
    res = pricing_from_comparables(est, blank_cost=110_000)
    assert res.suggested_price == 143_000
    assert "95.000đ" in res.explanation
    assert "nâng lên 143.000đ" in res.explanation
    assert any("cao hơn 75%" in w for w in res.warnings)
