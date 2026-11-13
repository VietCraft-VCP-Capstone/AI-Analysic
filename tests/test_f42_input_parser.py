"""
F42: lọc & phân tích tiêu đề seller nhập trước khi định giá / viết tiêu đề.
"""

import pytest

from app.services.f42 import orchestrator
from app.services.f42.input_parser import parse_seller_input
from app.services.f42.schemas import PriceRange, PricingResult


def test_removes_emoji_promo_and_sales_talk_keeping_original_words():
    r = parse_seller_input("🔥HOT🔥 [FREESHIP] ốp lưng iphone 18 promax 256 gb màu đen hàng mới về giá rẻ")
    assert r.clean_title == "ốp lưng iphone 18 Pro Max 256GB màu đen"
    assert r.removed == ["[FREESHIP]", "hàng mới về", "giá rẻ", "HOT"]           # đúng chữ seller gõ
    assert r.attributes == {"Dung lượng": "256GB", "Màu": "đen"}


@pytest.mark.parametrize("title,qty,query", [
    ("Combo 2 ốp lưng iPhone 18 Pro Max", 2, "ốp lưng iPhone 18 Pro Max"),
    ("Set 3 cốc sứ Bát Tràng vẽ tay", 3, "cốc sứ Bát Tràng vẽ tay"),
    ("Nến thơm 5 cái hương quế", 5, "Nến thơm hương quế"),
    ("Áo 2 dây lụa", 1, "Áo 2 dây lụa"),                       # "2 dây" không phải số lượng
])
def test_quantity_split_from_pricing_query(title, qty, query):
    r = parse_seller_input(title)
    assert (r.quantity, r.pricing_query) == (qty, query)


def test_used_condition_detected_with_accents():
    r = parse_seller_input("Điện thoại iPhone 17 Pro Max 256GB cũ 99% like new")
    assert r.condition == "used" and r.pricing_query == "Điện thoại iPhone 17 Pro Max 256GB"
    assert any("đã qua sử dụng" in i for i in r.issues)
    assert parse_seller_input("Củ cải muối Hải Dương").condition == "new"        # "củ" ≠ "cũ"


def test_issues_for_vague_title_and_risky_claims():
    assert any("quá ngắn" in i for i in parse_seller_input("abc").issues)
    assert any("chinh hang" in i for i in parse_seller_input("Nến thơm sáp đậu nành hàng chính hãng").issues)
    assert parse_seller_input("Áo thun cotton in hình size XL").attributes == {"Kích cỡ": "XL", "Chất liệu": "Cotton"}


def test_combo_price_is_unit_price_times_quantity():
    res = PricingResult(method="comparables", p25=80_000, p50=100_000, p75=120_000, p90=150_000,
                        suggested_price=100_000, suggested_range=PriceRange(low=80_000, high=120_000))
    orchestrator._apply_quantity_and_condition(res, parse_seller_input("Combo 2 cốc sứ vẽ tay"))
    assert (res.suggested_price, res.suggested_range.low, res.suggested_range.high) == (200_000, 160_000, 240_000)
    assert "combo 2" in res.explanation and "100.000đ × 2" in res.explanation


def test_cost_plus_not_multiplied_and_used_warning_added():
    res = PricingResult(method="cost_plus", suggested_price=130_000, suggested_range=PriceRange(low=115_000, high=145_000))
    orchestrator._apply_quantity_and_condition(res, parse_seller_input("Combo 2 cốc sứ cũ"))
    assert res.suggested_price == 130_000                                      # giá vốn đã là của cả combo
    assert any("đã qua sử dụng" in w for w in res.warnings)


def test_response_carries_input_analysis(monkeypatch):
    from app.services.f42.ai_engine import MarketAIAdvisor
    from app.services.f42 import config as f42_config
    from app.services.f42.schemas import SuggestionRequest

    monkeypatch.setattr(MarketAIAdvisor, "is_gemini_available", classmethod(lambda cls: False))
    monkeypatch.setattr(f42_config, "GOOGLE_SUGGEST_ENABLED", False)
    r = orchestrator.F42Orchestrator.execute(SuggestionRequest(keywords="🔥 Combo 2 cốc sứ vẽ tay giá rẻ"),
                                             db_live_override=False)
    ia = r.input_analysis
    assert ia["clean_title"] == "Combo 2 cốc sứ vẽ tay" and ia["quantity"] == 2
    assert "giá rẻ" in ia["removed"]


def test_shock_sale_phrases_removed():
    r = parse_seller_input("Bình giữ nhiệt inox 304 500 ml sale sốc hàng có sẵn")
    assert r.clean_title == "Bình giữ nhiệt inox 304 500ml" and r.attributes["Thể tích"] == "500ml"
