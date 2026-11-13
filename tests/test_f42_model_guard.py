"""F42: tên nêu mẫu máy cụ thể thì không định giá theo giá chung của mọi hãng."""

from app.services.f42.comparable_pricing import _prep
from app.services.f42.orchestrator import _resolve_pricing


def test_joined_model_number_is_split():
    assert _prep("OPPO Reno15 F") == "oppo reno 15 f"
    assert _prep("Galaxy S25 500ml") == "galaxy s25 500ml"      # mã ngắn và đơn vị giữ nguyên


def test_model_without_exact_data_does_not_use_mixed_platform_prices():
    iphones = {"prices": [21_304_500, 29_074_500, 36_750_000, 44_100_000, 12_537_000]}
    mixed = _resolve_pricing(None, iphones, None, None, 0, None, None)
    assert mixed.suggested_price > 0                                  # không nêu mẫu: vẫn tham khảo như cũ
    guarded = _resolve_pricing(None, iphones, None, None, 0, None, None, has_model=True)
    assert guarded.method == "none" and guarded.suggested_price == 0  # OPPO Reno15 F không lấy giá iPhone
