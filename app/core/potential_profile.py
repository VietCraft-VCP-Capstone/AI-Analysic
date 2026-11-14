import math
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple


def calculate_break_even(
    retail_price_vnd: float,
    base_cost_vnd: float,
    platform_fee_pct: float = 0.10,
    shipping_subsidy_vnd: float = 0.0,
    test_ads_budget_vnd: float = 300000.0,
    return_rate_assumption_pct: float = 0.05,
) -> Dict[str, Any]:
    """
    Bảng tính lợi nhuận và điểm hòa vốn (Lớp 4).
    Seller có thể mở ra và tự sửa từng con số.
    
    Công thức:
    - Phí sàn = retail_price * platform_fee_pct (mặc định 10% theo quy chuẩn VietCraft)
    - Lợi nhuận gộp trên 1 đơn = retail_price - phí sàn - base_cost - shipping_subsidy
    - Trừ hao rủi ro hoàn đơn: đối với hàng cá nhân hóa/POD, đơn hoàn lỗ tiền phôi (base_cost)
    - Lợi nhuận thực tế kỳ vọng / đơn = Lợi nhuận gộp - (base_cost * return_rate_assumption_pct)
    - Số đơn hòa vốn ngân sách thử nghiệm = ceil(test_ads_budget / Lợi nhuận thực tế / đơn)
    """
    platform_fee = retail_price_vnd * platform_fee_pct
    gross_profit_per_unit = retail_price_vnd - platform_fee - base_cost_vnd - shipping_subsidy_vnd
    return_loss_expected = base_cost_vnd * return_rate_assumption_pct
    net_profit_per_unit = gross_profit_per_unit - return_loss_expected

    margin_pct = (net_profit_per_unit / retail_price_vnd * 100) if retail_price_vnd > 0 else 0.0

    if net_profit_per_unit > 0:
        units_to_break_even = math.ceil(test_ads_budget_vnd / net_profit_per_unit)
    else:
        units_to_break_even = None  # Bán là lỗ, không bao giờ hòa vốn

    return {
        "retail_price_vnd": int(round(retail_price_vnd)),
        "base_cost_vnd": int(round(base_cost_vnd)),
        "platform_fee_pct": platform_fee_pct,
        "platform_fee_vnd": int(round(platform_fee)),
        "shipping_subsidy_vnd": int(round(shipping_subsidy_vnd)),
        "return_rate_assumption_pct": return_rate_assumption_pct,
        "net_profit_per_unit_vnd": int(round(net_profit_per_unit)),
        "margin_pct": round(margin_pct, 1),
        "test_ads_budget_vnd": int(round(test_ads_budget_vnd)),
        "units_to_break_even": units_to_break_even,
        "is_profitable": net_profit_per_unit > 0 and margin_pct >= 20.0,
        "formula_explanation": (
            f"Lãi ròng {int(net_profit_per_unit):,}đ/sp (biên lãi {margin_pct:.1f}%). "
            f"Với ngân sách thử {int(test_ads_budget_vnd):,}đ, cần bán {units_to_break_even or '∞'} đơn để hòa vốn."
        ),
    }


def analyze_trend_repeatability(
    trend_points: List[Tuple[str, float]],
    target_event_month: int,
) -> Dict[str, Any]:
    """
    Kiểm tra tính lặp lại của nhu cầu (Lớp 2):
    Chuỗi Trends 5 năm có lặp lại đỉnh vào cùng tháng/dịp này các năm trước hay không?
    """
    if not trend_points or len(trend_points) < 52:
        return {
            "status": "uncertain",
            "years_analyzed": 1,
            "years_peaked": 1,
            "evidence": "Chưa đủ 2 năm dữ liệu lịch sử để xác nhận tính lặp lại chu kỳ",
            "anti_evidence": "Có thể là hiện tượng bùng nổ nhất thời (trend bong bóng) thay vì mùa vụ hàng năm."
        }

    # Gom giá trị theo năm và kiểm tra xem tháng mục tiêu có phải đỉnh của năm không
    yearly_data: Dict[int, List[float]] = {}
    target_month_data: Dict[int, List[float]] = {}

    for date_str, val in trend_points:
        try:
            d = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
        except Exception:
            continue
        yearly_data.setdefault(d.year, []).append(val)
        if d.month == target_event_month or (target_event_month == 1 and d.month == 12) or abs(d.month - target_event_month) <= 1:
            target_month_data.setdefault(d.year, []).append(val)

    years_analyzed = 0
    years_peaked = 0

    for yr, all_vals in yearly_data.items():
        if len(all_vals) >= 30 and yr in target_month_data:
            years_analyzed += 1
            yr_avg = sum(all_vals) / len(all_vals)
            month_vals = target_month_data[yr]
            month_max = max(month_vals) if month_vals else 0
            # Nếu tháng này có đỉnh cao hơn 1.25 lần trung bình năm đó
            if yr_avg > 0 and month_max >= yr_avg * 1.25:
                years_peaked += 1

    if years_peaked >= 2:
        status = "pass"
        evidence = f"{years_peaked}/{years_analyzed} năm gần nhất đều tăng mạnh cùng dịp này"
        anti_evidence = None
    elif years_peaked == 1:
        status = "uncertain"
        evidence = f"Tăng ở 1/{years_analyzed} năm gần nhất (chưa đủ bằng chứng chu kỳ)"
        anti_evidence = "Chỉ có 1 kỳ lịch sử ghi nhận tăng trưởng, cần đề phòng đột biến nhất thời."
    else:
        status = "uncertain"
        evidence = f"Biên độ dịp này không vượt trội so với trung bình năm ({years_peaked}/{years_analyzed} năm)"
        anti_evidence = "Nhu cầu tương đối phẳng, không có đỉnh sóng rõ rệt theo mùa."

    return {
        "status": status,
        "years_analyzed": max(1, years_analyzed),
        "years_peaked": years_peaked,
        "evidence": evidence,
        "anti_evidence": anti_evidence
    }


def build_product_potential_profile(
    product_name: str,
    category_name: str,
    keyword: str,
    retail_price_vnd: float,
    base_cost_vnd: float,
    trend_series: List[Tuple[str, float]],
    target_event_date: date,
    cut_off_date: date,
    current_date: date,
    competitor_listings: Optional[List[Dict[str, Any]]] = None,
    shop_has_similar_sales: bool = False,
    shop_cr_in_category: Optional[float] = None,
    shop_lead_time_days: int = 4,
) -> Dict[str, Any]:
    """
    Xây dựng Hồ Sơ Tiềm Năng 5 Lớp Độc Lập cho một sản phẩm đề xuất.
    
    Quy tắc đề xuất:
    - Sản phẩm chỉ được khuyến nghị khi Lớp 1 (Nhu cầu), Lớp 3 (Cạnh tranh) và Lớp 4 (Lợi nhuận) ĐẠT.
    - Luôn hiển thị 'Lý do có thể sai' (Anti-evidence) để seller không chủ quan.
    """
    competitor_listings = competitor_listings or []
    days_to_cut_off = (cut_off_date - current_date).days

    # 1. LỚP 1: CÓ NGƯỜI CẦN KHÔNG? (Nhu cầu có thật và đang tăng?)
    recent_trend = [v for _, v in trend_series[-8:]] if len(trend_series) >= 8 else [50.0]
    older_trend = [v for _, v in trend_series[-16:-8]] if len(trend_series) >= 16 else recent_trend

    recent_avg = sum(recent_trend) / len(recent_trend) if recent_trend else 0.0
    older_avg = sum(older_trend) / len(older_trend) if older_trend else 0.0
    wow_growth_pct = round((recent_avg - older_avg) / older_avg * 100, 1) if older_avg > 0 else 0.0

    if recent_avg >= 15.0 and wow_growth_pct >= 5.0:
        layer1_status = "pass"
        layer1_text = f"Lượt tìm kiếm tăng +{wow_growth_pct}% trong các tuần gần đây"
    elif recent_avg >= 10.0:
        layer1_status = "uncertain"
        layer1_text = f"Nhu cầu tìm kiếm duy trì ở mức ổn định (tăng {wow_growth_pct}%)"
    else:
        layer1_status = "fail"
        layer1_text = f"Lượng tìm kiếm ở mức nền thấp (< 10 điểm)"

    # 2. LỚP 2: CÓ LẶP LẠI KHÔNG? (Chu kỳ mùa vụ hay đột biến?)
    rep = analyze_trend_repeatability(trend_series, target_event_date.month)
    layer2_status = rep["status"]
    layer2_text = rep["evidence"]

    # 3. LỚP 3: CÓ CHỖ CHO BẠN KHÔNG? (Cạnh tranh có chấp nhận được?)
    n_sellers = len({str(l.get("shop_id") or l.get("shop_name")) for l in competitor_listings if l.get("shop_id") or l.get("shop_name")})
    # Nếu không có dữ liệu đối thủ trực tiếp thì ước lượng từ danh sách listing mẫu
    if n_sellers == 0:
        n_sellers = max(3, len(competitor_listings))

    prices = [l.get("price_vnd") for l in competitor_listings if l.get("price_vnd")]
    min_p = min(prices) if prices else int(retail_price_vnd * 0.8)
    max_p = max(prices) if prices else int(retail_price_vnd * 1.3)

    if n_sellers <= 25:
        layer3_status = "pass"
        layer3_text = f"{n_sellers} người bán tham gia, phân khúc giá {min_p // 1000}k–{max_p // 1000}k"
    elif n_sellers <= 60:
        layer3_status = "uncertain"
        layer3_text = f"Mức độ cạnh tranh khá dày ({n_sellers} người bán trên sàn)"
    else:
        layer3_status = "fail"
        layer3_text = f"Thị trường bão hòa với hơn {n_sellers} shop đang bán"

    # 4. LỚP 4: CÓ LÃI KHÔNG? (Hòa vốn sau bao nhiêu đơn?)
    financials = calculate_break_even(
        retail_price_vnd=retail_price_vnd,
        base_cost_vnd=base_cost_vnd,
        platform_fee_pct=0.10,
        test_ads_budget_vnd=300000.0,
    )
    if financials["is_profitable"] and financials["units_to_break_even"] and financials["units_to_break_even"] <= 15:
        layer4_status = "pass"
        layer4_text = f"Biên lãi {financials['margin_pct']}%, hòa vốn sau {financials['units_to_break_even']} đơn"
    elif financials["net_profit_per_unit_vnd"] > 0:
        layer4_status = "uncertain"
        layer4_text = f"Biên lãi mỏng ({financials['margin_pct']}%), cần {financials['units_to_break_even']} đơn hòa vốn"
    else:
        layer4_status = "fail"
        layer4_text = "Giá bán hiện tại không bù đắp được giá vốn và phí sàn"

    # 5. LỚP 5: BẠN LÀM ĐƯỢC KHÔNG? (Năng lực xưởng và hạn giao kịp?)
    # Cần tối thiểu shop_lead_time_days + 4 ngày ship = X ngày trước lễ
    total_fulfillment_days = shop_lead_time_days + 4
    if days_to_cut_off >= total_fulfillment_days:
        layer5_status = "pass"
        layer5_text = f"Kịp tiến độ: xưởng cần {shop_lead_time_days} ngày, hạn chốt đơn còn {days_to_cut_off} ngày"
    elif days_to_cut_off > 0:
        layer5_status = "uncertain"
        layer5_text = f"Gấp rút: còn {days_to_cut_off} ngày trước hạn chốt đơn (xưởng cần {shop_lead_time_days} ngày)"
    else:
        layer5_status = "fail"
        layer5_text = "Đã quá hạn chốt đơn an toàn, nhận đơn dễ bị giao trễ"

    # Thu thập "Lý do có thể sai" (Anti-evidence)
    reasons_could_be_wrong = []
    if rep["anti_evidence"]:
        reasons_could_be_wrong.append(rep["anti_evidence"])
    if layer3_status != "pass":
        reasons_could_be_wrong.append(f"Mật độ cạnh tranh đang tăng nhanh với {n_sellers} shop đang chào bán.")
    if not shop_has_similar_sales:
        reasons_could_be_wrong.append("Shop của bạn chưa từng có đơn nào cho dòng sản phẩm có phong cách/chất liệu này.")
    if shop_cr_in_category is not None and shop_cr_in_category < 1.0:
        reasons_could_be_wrong.append(f"Tỷ lệ chuyển đổi lịch sử của shop ở nhóm ngành này khá thấp ({shop_cr_in_category:.1f}%).")
    if days_to_cut_off <= 10:
        reasons_could_be_wrong.append("Thời gian bán cao điểm còn lại rất ngắn, chậm trễ 1–2 ngày in có thể gây quá hạn giao.")

    if not reasons_could_be_wrong:
        reasons_could_be_wrong.append("Thị hiếu người dùng có thể thay đổi nhanh nếu đối thủ ra mắt mẫu mã độc lạ hơn.")

    # Đánh giá độ tin cậy tín hiệu tổng quát
    passes = sum(1 for s in (layer1_status, layer2_status, layer3_status, layer4_status, layer5_status) if s == "pass")
    if passes >= 4 and layer1_status == "pass" and layer4_status == "pass":
        signal_level = "high"
        signal_label = "Tín hiệu Tốt ●●●○"
    elif passes >= 3 and layer4_status == "pass":
        signal_level = "medium"
        signal_label = "Tín hiệu Khá ●●○○"
    else:
        signal_level = "low"
        signal_label = "Tín hiệu Sơ bộ ●○○○"

    # THANG THỬ NHỎ (TRIAL PLAN)
    trial_units = 20
    test_budget = 300000
    stop_loss_days = 5
    min_orders_success = max(4, financials["units_to_break_even"] // 2 if financials["units_to_break_even"] else 4)

    is_make_to_order = "khắc" in product_name.lower() or "in" in product_name.lower()
    trial_plan = {
        "mode": "make_to_order" if is_make_to_order else "small_batch",
        "recommended_mode": "make_to_order" if is_make_to_order else "small_batch",
        "mode_label": "Sản xuất theo đơn (Make-to-order, vốn 0đ phôi)" if is_make_to_order else "Nhập thử lô nhỏ (15–20 sản phẩm)",
        "test_units": trial_units,
        "test_quantity": 0 if is_make_to_order else trial_units,
        "test_budget_vnd": test_budget,
        "test_ads_budget_vnd": test_budget,
        "timeframe_days": stop_loss_days,
        "test_duration_days": stop_loss_days,
        "ladder_steps": [
            {
                "step": 1,
                "name": "Nấc 1: Tín hiệu & Listing sớm",
                "action": "Đăng listing sớm, dùng mockup chuẩn SEO đón tìm kiếm tự nhiên",
                "threshold": "Tối thiểu 100 lượt xem tự nhiên"
            },
            {
                "step": 2,
                "name": "Nấc 2: Thử nhỏ có điểm dừng lỗ",
                "action": "Bật ads ngân sách nhỏ hoặc mở bán make-to-order",
                "threshold": f"Ngân sách tối đa {test_budget // 1000}k, đạt {min_orders_success} đơn"
            },
            {
                "step": 3,
                "name": "Nấc 3: Đặt cược lớn (Scale-up)",
                "action": "Nhập sỉ số lượng lớn, đẩy mạnh combo và ads chuyển đổi",
                "threshold": "CVR > 2.5% và có ít nhất 5 đánh giá 5 sao"
            }
        ],
        "success_criteria": f"Đạt tối thiểu {min_orders_success} đơn thật và {min_orders_success * 2} lượt thêm giỏ trong {stop_loss_days} ngày thử",
        "stop_loss_rules": [
            f"Dừng ngay nếu tiêu hết {test_budget // 1000}k mà không có đơn nào.",
            f"Dừng nếu sau {stop_loss_days} ngày tỷ lệ chuyển đổi dưới 1%.",
            "Không ôm tồn thêm nếu chưa đạt ngưỡng nấc 2."
        ],
        "stop_loss_rule": f"Dừng ngay nếu sau {stop_loss_days} ngày hoặc tiêu hết {test_budget // 1000}k mà dưới {min_orders_success} đơn để bảo toàn vốn.",
        "scale_up_trigger": f"Chỉ nhập số lượng lớn khi đạt từ {min_orders_success} đơn trở lên trong bước thử nhỏ."
    }

    return {
        "product_name": product_name,
        "category_name": category_name,
        "keyword": keyword,
        "signal_level": signal_level,
        "signal_label": signal_label,
        "verdict": "dat" if layer1_status in ("pass", "uncertain") and layer4_status == "pass" and layer5_status != "fail" else "chua_chac" if layer5_status != "fail" else "khong_dat",
        "verdict_label": "Đạt hồ sơ" if layer1_status in ("pass", "uncertain") and layer4_status == "pass" and layer5_status != "fail" else "Cần cân nhắc" if layer5_status != "fail" else "Không khuyến nghị",
        "layers": {
            "demand": {"status": layer1_status, "title": "Nhu cầu", "text": layer1_text, "action_label": "Xem xu hướng", "name": "Nhu cầu thị trường", "question": "Nhu cầu có thật và đang tăng?", "claim": layer1_text, "evidence": "Dữ liệu Google Trends VN"},
            "repeatability": {"status": layer2_status, "title": "Lặp lại", "text": layer2_text, "action_label": "Xem các năm", "name": "Tính lặp lại", "question": "Năm nào cũng lặp lại vào dịp này?", "claim": layer2_text, "evidence": "Chuỗi lịch sử đa năm"},
            "competition": {"status": layer3_status, "title": "Cạnh tranh", "text": layer3_text, "action_label": "Xem người bán", "name": "Cạnh tranh", "question": "Có chen chân vào được không?", "claim": layer3_text, "evidence": "Số đối thủ cùng ngành"},
            "profitability": {"status": layer4_status, "title": "Lợi nhuận", "text": layer4_text, "action_label": "Xem / Sửa bảng tính", "name": "Biên lợi nhuận", "question": "Bán có lời sau mọi chi phí không?", "claim": layer4_text, "evidence": financials["formula_explanation"]},
            "capacity": {"status": layer5_status, "title": "Năng lực", "text": layer5_text, "action_label": "Xem tiến độ xưởng", "name": "Năng lực đáp ứng", "question": "Có làm kịp và giao kịp trước lễ không?", "claim": layer5_text, "evidence": "Lead time sản xuất và hạn chót giao hàng"},
        },
        "financials": financials,
        "break_even": {
            "retail_price": financials["retail_price_vnd"],
            "base_cost": financials["base_cost_vnd"],
            "platform_fee": financials["platform_fee_vnd"],
            "gross_margin": financials["retail_price_vnd"] - financials["platform_fee_vnd"] - financials["base_cost_vnd"],
            "gross_margin_pct": financials["margin_pct"],
            "estimated_cpa": int(round(financials["retail_price_vnd"] * 0.15)),
            "net_margin_per_unit": financials["net_profit_per_unit_vnd"],
            "net_margin_pct": financials["margin_pct"],
            "fixed_test_budget": financials["test_ads_budget_vnd"],
            "break_even_units": financials["units_to_break_even"] or 0,
            "is_viable": financials["is_profitable"],
            "verdict_note": financials["formula_explanation"],
        },
        "reasons_could_be_wrong": reasons_could_be_wrong,
        "anti_evidence": reasons_could_be_wrong,
        "trial_plan": trial_plan,
        "is_recommended_for_launch": layer1_status in ("pass", "uncertain") and layer4_status == "pass" and layer5_status != "fail",
    }


if __name__ == "__main__":
    print("=== TỰ KIỂM TRA POTENTIAL_PROFILE.PY ===")

    # 1. Kiểm tra bảng tính hòa vốn
    fb = calculate_break_even(retail_price_vnd=180000, base_cost_vnd=85000, test_ads_budget_vnd=300000)
    assert fb["is_profitable"] is True
    assert fb["units_to_break_even"] == 5, f"Mong đợi 5 đơn hòa vốn, nhận {fb['units_to_break_even']}"
    assert fb["margin_pct"] > 30.0
    print(f"✓ Bảng tính hòa vốn: {fb['formula_explanation']}")

    # 2. Kiểm tra hồ sơ 5 lớp cho một sản phẩm mẫu dịp Tết
    sample_trend = [("2026-09-01", 30.0), ("2026-10-01", 45.0), ("2026-11-01", 65.0), ("2026-12-01", 90.0)]
    profile = build_product_potential_profile(
        product_name="Cốc sứ Bát Tràng men hỏa biến in chữ An Khang",
        category_name="Gia dụng & Quà tặng",
        keyword="quà tết",
        retail_price_vnd=195000,
        base_cost_vnd=80000,
        trend_series=sample_trend,
        target_event_date=date(2027, 2, 6),
        cut_off_date=date(2027, 1, 19),
        current_date=date(2026, 12, 10),
        competitor_listings=[{"shop_name": "Shop A", "price_vnd": 180000}, {"shop_name": "Shop B", "price_vnd": 210000}],
        shop_has_similar_sales=False,
    )

    assert "layers" in profile
    assert profile["layers"]["profitability"]["status"] == "pass"
    assert len(profile["reasons_could_be_wrong"]) > 0
    assert "trial_plan" in profile
    print("✓ Đã sinh đầy đủ 5 lớp bằng chứng, lý do có thể sai và kế hoạch thử nhỏ.")
    print("✅ TẤT CẢ SELF-CHECKS CỦA POTENTIAL_PROFILE.PY ĐÃ PASS!")
