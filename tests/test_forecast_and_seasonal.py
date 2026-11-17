import datetime
import pytest

from app.core.calendar_vn import (
    SHOPPING_EVENTS,
    TET_DATES,
    calculate_occasion_window,
    get_tet_date,
    upcoming_events,
)
from app.core.potential_profile import (
    analyze_trend_repeatability,
    build_product_potential_profile,
    calculate_break_even,
)


def test_calendar_tet_and_occasions_up_to_2030():
    assert 2030 in TET_DATES
    peak_2027 = get_tet_date(2027)
    assert peak_2027.strftime("%Y-%m-%d") == "2027-02-06"

    # Tất cả các sự kiện lớn đều có cấu hình hợp lệ
    for ev in SHOPPING_EVENTS:
        assert ev["lead_time_days"] > 0
        assert "key" in ev
        assert "name" in ev


def test_calculate_occasion_window():
    # Giả lập ngày 2026-11-01 cho Tết 2027 (06/02/2027)
    ref_date = datetime.date(2026, 11, 1)
    tet_ev = next(ev for ev in SHOPPING_EVENTS if ev["key"] == "tet")
    window = calculate_occasion_window(tet_ev, ref_date)

    assert window["event_key"] == "tet"
    assert window["lead_time_days"] == 18
    assert window["event_date"] == "2027-02-06"
    assert window["cut_off_date"] == "2027-01-19"  # 06/02 trừ 18 ngày lead time
    assert window["days_to_event"] > 0
    assert window["days_to_cut_off"] > 0
    assert window["status"] in ("active", "upcoming", "passed")


def test_break_even_calculator():
    # Test sp bán 200,000đ, vốn 80,000đ, ngân sách test 500,000đ
    res = calculate_break_even(
        retail_price_vnd=200000.0,
        base_cost_vnd=80000.0,
        platform_fee_pct=0.10,
        return_rate_assumption_pct=0.03,
        test_ads_budget_vnd=500000.0,
    )

    assert res["retail_price_vnd"] == 200000
    assert res["base_cost_vnd"] == 80000
    assert res["platform_fee_vnd"] == 20000  # 10% của 200k
    assert res["net_profit_per_unit_vnd"] > 0
    assert res["margin_pct"] > 0
    assert res["units_to_break_even"] is not None
    assert res["is_profitable"] is True


def test_trend_repeatability_analysis():
    # Giả lập chuỗi 104 tuần (2 năm)
    series = [(f"2025-02-{(i%20)+1:02d}", 80.0 if i < 10 else 20.0) for i in range(52)] + \
             [(f"2026-02-{(i%20)+1:02d}", 85.0 if i < 10 else 22.0) for i in range(52)]

    rep = analyze_trend_repeatability(series, target_event_month=2)
    assert rep["status"] in ("pass", "uncertain", "fail")
    assert rep["years_analyzed"] >= 1


def test_product_potential_profile_5_layers():
    # Tạo profile hoàn chỉnh cho sản phẩm mẫu
    series = [(f"2026-10-{(i%25)+1:02d}", 40.0 + i * 0.5) for i in range(45)]
    target_event_d = datetime.date(2027, 2, 6)
    cut_off_d = datetime.date(2027, 1, 30)
    current_d = datetime.date(2026, 11, 1)

    profile = build_product_potential_profile(
        product_name="Hộp Quà Mứt Tết & Trà Gỗ Khắc Laser",
        category_name="Quà tặng & Gia dụng",
        keyword="quà tết",
        retail_price_vnd=285000.0,
        base_cost_vnd=115000.0,
        trend_series=series,
        target_event_date=target_event_d,
        cut_off_date=cut_off_d,
        current_date=current_d,
        competitor_listings=[],
        shop_has_similar_sales=True,
        shop_lead_time_days=5,
    )

    assert "layers" in profile
    assert profile["layers"]["demand"]["status"] in ("pass", "uncertain", "fail", "dat", "chua_chac", "khong_dat")
    assert profile["layers"]["repeatability"]["status"] in ("pass", "uncertain", "fail", "dat", "chua_chac", "khong_dat")
    assert profile["layers"]["competition"]["status"] in ("pass", "uncertain", "fail", "dat", "chua_chac", "khong_dat")
    assert profile["layers"]["profitability"]["status"] in ("pass", "uncertain", "fail", "dat", "chua_chac", "khong_dat")
    assert profile["layers"]["capacity"]["status"] in ("pass", "uncertain", "fail", "dat", "chua_chac", "khong_dat")

    # Anti-evidence phải có cảnh báo để người bán không cược mù quáng
    assert len(profile["anti_evidence"]) >= 1

    # Trial plan phải có các nấc thang kiểm chứng và nguyên tắc cắt lỗ
    assert len(profile["trial_plan"]["ladder_steps"]) >= 2
    assert len(profile["trial_plan"]["stop_loss_rules"]) >= 1
