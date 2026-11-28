"""Kiểm thử lõi seasonal_intel bằng dữ liệu tổng hợp (không cần MongoDB)."""
import datetime as dt
import random

from app.core import seasonal_intel as si


def _orders(shop, n, start, days, item_n=1, coupon=False, amt=200000):
    random.seed(hash((shop, start)) % 1000)
    out = []
    for i in range(n):
        d = start + dt.timedelta(days=random.randint(0, days - 1), hours=random.randint(0, 20))
        out.append({"shop_id": shop, "created_at": d, "order_status": "DELIVERED",
                    "items": [{"title": "Ly sứ tết"}] * item_n,
                    "coupon_code": "X" if coupon else None, "financial_breakdown": {"subtotal": amt}})
    return out


def test_compare_shop_vs_industry_percentile_and_insufficient():
    ev = dt.date(2025, 1, 29)
    past = {2025: ev}
    today = dt.date(2025, 11, 1)
    win_start = ev - dt.timedelta(days=30)
    industry = []
    for k in range(8):                       # 8 shop ngành, mỗi shop 20 đơn trong dịp + 20 đơn nền
        industry += _orders(f"s{k}", 20 + k * 2, win_start, 30, item_n=1 + (k % 2), coupon=(k % 3 == 0))
        industry += _orders(f"s{k}", 20, win_start - dt.timedelta(days=56), 56)
    shop = [o for o in industry if o["shop_id"] == "s7"]
    cmp_ = si.compare_shop_vs_industry(shop, industry, past, 30, today, model_uplift_pct=40.0)
    og = cmp_["orders_growth"]
    assert og["basis"] == "measured_shop"
    assert og["shop_percentile"] is not None and 0 <= og["shop_percentile"] <= 100
    assert og["industry"]["n_shops"] >= si.MIN_SHOPS_FOR_RANK

    # Shop không có đơn → không bịa số shop, dùng ngành
    empty = si.compare_shop_vs_industry([], industry, past, 30, today, model_uplift_pct=40.0)
    assert empty["orders_growth"]["shop"]["value"] is None
    assert empty["orders_growth"]["basis"] == "industry_only"

    # Không ai có đơn → chỉ orders_growth có model, còn lại insufficient
    none_ = si.compare_shop_vs_industry([], [], past, 30, today, model_uplift_pct=40.0)
    assert none_["orders_growth"]["basis"] == "model_forecast"
    assert none_["voucher_pct"]["basis"] == "insufficient"


def test_seller_competition_hhi():
    mono = [{"seller_id": "a", "price_vnd": 100000, "sold_count": 900},
            {"seller_id": "b", "price_vnd": 120000, "sold_count": 50},
            {"seller_id": "c", "price_vnd": 110000, "sold_count": 50}]
    c = si.seller_competition(mono, 105000)
    assert c["status"] == "measured" and c["top3_share_pct"] == 100.0 and c["hhi"] > 5000
    assert si.seller_competition(mono[:2], 1)["status"] == "insufficient"


def test_impact_counterfactual_and_projected():
    ev = dt.date(2025, 2, 10)
    base = _orders("s", 56, ev - dt.timedelta(days=30 + 56), 56)       # 1 đơn/ngày nền
    win = _orders("s", 60, ev - dt.timedelta(days=30), 30)
    up = {"uplift_p10": 1.2, "uplift_p50": 1.5, "uplift_p90": 1.9}
    done = si.impact_report(base + win, ev, 30, ev + dt.timedelta(days=1), ["ly sứ"], up, None)
    assert done["phase"] == "ended" and done["status"] == "measured"
    assert done["counterfactual_orders"]["p50"] > 0 and done["adopted_orders"] == done["actual_orders"]
    proj = si.impact_report(base, ev, 30, ev - dt.timedelta(days=45), ["ly sứ"], up, None)
    assert proj["status"] == "projected" and proj["expected_orders_p10"] < proj["expected_orders_p90"]
    nothing = si.impact_report([], ev, 30, ev - dt.timedelta(days=45), [], up, None)
    assert nothing["status"] == "insufficient"


def test_real_stl_strength_and_playbook():
    import math
    pts = [((dt.date(2021, 1, 3) + dt.timedelta(weeks=i)).isoformat(),
            50 + 30 * math.sin(2 * math.pi * i / 52) + (i % 3)) for i in range(260)]
    r = si.real_stl(pts)
    assert r["method"].startswith("statsmodels") and r["seasonal_strength"] > 0.8
    pb = si.build_playbook({"title": "Ly sứ", "keyword": "ly sứ"}, dt.date(2025, 1, 15), dt.date(2025, 1, 29),
                           dt.date(2025, 1, 1), {"uplift_p10": 1, "uplift_p50": 1.4, "uplift_p90": 2}, 1.0, 4)
    assert pb["feasible"] and len(pb["steps"]) == 5
    assert pb["steps"] == sorted(pb["steps"], key=lambda s: s["date"])


def _by_key(pb):
    return {s["key"]: s for s in pb["steps"]}


def test_playbook_steps_have_fixed_key_and_slot():
    pb = si.build_playbook({"title": "x", "keyword": "x"}, dt.date(2026, 12, 3), dt.date(2026, 12, 10),
                           dt.date(2026, 11, 28), None, None, 4)
    steps = _by_key(pb)
    assert {k: s["slot"] for k, s in steps.items()} == {"listing": 0, "test": 1, "decide": 2, "produce": 3, "cutoff": 4}
    assert steps["test"]["target_orders"] == 20


def test_playbook_short_window_keeps_listing_before_test_before_decide():
    # Còn 5 ngày tới hạn chốt: trước đây listing (01/12) rơi sau bước thử (29/11)
    pb = si.build_playbook({"title": "x", "keyword": "x"}, dt.date(2026, 12, 3), dt.date(2026, 12, 10),
                           dt.date(2026, 11, 28), None, None, 4)
    s = _by_key(pb)
    assert s["listing"]["date"] <= s["test"]["date"] < s["decide"]["date"] <= s["cutoff"]["date"]


def test_playbook_long_window_dates_unchanged():
    today = dt.date(2026, 11, 1)
    pb = si.build_playbook({"title": "x", "keyword": "x"}, today + dt.timedelta(days=30), today + dt.timedelta(days=37),
                           today, None, None, 4)
    s = _by_key(pb)
    assert [s[k]["days_from_today"] for k in ("listing", "test", "decide", "produce", "cutoff")] == [3, 7, 10, 22, 30]


def test_playbook_cutoff_today_all_steps_capped():
    today = dt.date(2026, 12, 3)
    pb = si.build_playbook({"title": "x", "keyword": "x"}, today, today + dt.timedelta(days=7), today, None, None, 4)
    s = _by_key(pb)
    assert all(s[k]["date"] <= today.isoformat() for k in ("listing", "test", "decide", "cutoff"))

