"""
Kiểm thử các lỗi gợi ý giá đã sửa sau đợt review:
- chỉ so giá với tin CÙNG LOẠI sản phẩm (trước đây "Đồng hồ nam" lấy giá giày boots nam),
- khoảng Cost-Plus luôn chứa giá đề xuất, chặn targetMargin vô lý,
- làm tròn nửa lên, snapshot dữ liệu sàn đọc/ghi một lần.
Chỉ mục nhỏ tự dựng — không cần dữ liệu Tiki, MongoDB hay mạng.
"""

import pandas as pd
import pytest
from pydantic import ValidationError

from app.services.f42.comparable_pricing import ComparableIndex, _head_tokens, _prep, _same_product_type, round_price_nice
from app.services.f42.pricing_engine import compute_pricing, round_price
from app.services.f42.schemas import SuggestionRequest


def _index():
    rows = []
    for i in range(6):
        rows.append(("fashion", f"Giày boots nam da lộn cao cổ mẫu {i}", 400_000 + i * 10_000))
        rows.append(("fashion", f"Áo đông xuân nam giữ nhiệt mẫu {i}", 70_000 + i * 1_000))
        rows.append(("accessories", f"Đồng hồ nam dây da mặt tròn mẫu {i}", 900_000 + i * 20_000))
        rows.append(("bags", f"Balo laptop nam chống nước mẫu {i}", 300_000 + i * 5_000))
        rows.append(("shoes", f"Giày ABC thể thao mẫu {i}", 120_000 + i * 2_000))
    df = pd.DataFrame(rows, columns=["group", "title", "price"])
    df["sold"] = 0
    return ComparableIndex(df)


def test_head_tokens_skip_noise_and_numbers():
    assert _head_tokens(_prep("[10 màu] Nến thơm sáp đậu nành")) == ["nen", "thom"]
    assert _head_tokens(_prep("Combo 2 Áo thun cotton")) == ["ao", "thun"]


@pytest.mark.parametrize("cand,ok", [
    ("Đồng hồ nữ dây kim loại", True),           # cùng danh từ chính ở đầu
    ("Bờm đồng hồ la mã", False),                 # "đồng hồ" nằm giữa tiêu đề
    ("Áo đông xuân nam", False),                  # "đông" ≠ "đồng hồ"
    ("Giày boots nam dây da", False),
])
def test_same_product_type(cand, ok):
    assert _same_product_type(_head_tokens(_prep("Đồng hồ nam dây da")), _prep(cand)) is ok


def test_word_in_middle_of_title_is_not_same_type():
    # "Balo laptop" không được dùng để định giá laptop
    assert not _same_product_type(_head_tokens(_prep("Laptop Dell XPS 13")), _prep("Balo laptop nam"))


def test_watch_priced_only_from_watches():
    est = _index().estimate("Đồng hồ nam dây da")
    assert est.usable
    assert all("Đồng hồ" in c.title for c in est.comparables)
    assert 850_000 <= est.p50 <= 1_050_000


def test_unrelated_query_gets_no_price():
    # Trước đây "abc xyz" ra giá theo "Giày ABC" với độ tin cậy trung bình
    assert not _index().estimate("abc xyz").usable
    assert not _index().estimate("Laptop Dell XPS 13").usable


@pytest.mark.parametrize("margin", [0.05, 0.1, 0.3, 1.0])
def test_cost_plus_range_contains_suggestion(margin):
    r = compute_pricing([], blank_cost=100_000, target_margin=margin)
    assert r.suggested_range.low <= r.suggested_price <= r.suggested_range.high


def test_unreasonable_target_margin_rejected():
    with pytest.raises(ValidationError):
        SuggestionRequest(targetMargin=30)  # tưởng là 30% → giá gấp 31 lần giá vốn
    assert SuggestionRequest(targetMargin=0.3).get_target_margin() == 0.3


def test_rounding_half_up():
    assert (round_price(2_500), round_price(3_500)) == (3_000, 4_000)
    assert round_price_nice(102_500) == 105_000


def test_live_snapshot_is_consistent():
    idx = _index()
    idx._live = ([{"title": "Đồng hồ nam gỗ", "prep": _prep("Đồng hồ nam gỗ"), "price": 950_000, "category_ids": []}],
                 idx.vectorizer.transform([_prep("Đồng hồ nam gỗ")]))
    assert any(c.source == "vietcraft" for c in idx.search("Đồng hồ nam"))
