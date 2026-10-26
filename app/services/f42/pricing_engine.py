import math
from typing import Any, Dict, List, Optional
from bson import ObjectId

from app.services.f42 import config
from app.services.f42.schemas import PriceRange, PricingResult


def _percentile(sorted_data: List[float], q: float) -> float:
    """Nội suy tuyến tính phân vị chuẩn."""
    if not sorted_data:
        return 0.0
    if len(sorted_data) == 1:
        return float(sorted_data[0])
    k = (len(sorted_data) - 1) * q
    lo = int(math.floor(k))
    hi = int(math.ceil(k))
    if lo == hi:
        return float(sorted_data[lo])
    weight = k - lo
    return float(sorted_data[lo] + (sorted_data[hi] - sorted_data[lo]) * weight)


def round_price(val: float, step: int = config.PRICE_ROUND_STEP) -> int:
    """Làm tròn tiền theo bước quy định (mặc định 1.000 VND)."""
    if val <= 0:
        return 0
    return int(round(val / step) * step)


def filter_outliers(
    numbers: List[float],
    method: str = config.OUTLIER_METHOD,
    k: float = config.IQR_K,
    percentile_trim: tuple = config.PERCENTILE_TRIM
) -> List[float]:
    """Loại bỏ ngoại lai bằng IQR hoặc Percentile."""
    if len(numbers) < 4:
        return list(numbers)

    sorted_nums = sorted(numbers)
    if method == "iqr":
        q1 = _percentile(sorted_nums, 0.25)
        q3 = _percentile(sorted_nums, 0.75)
        iqr = q3 - q1
        lower_bound = q1 - k * iqr
        upper_bound = q3 + k * iqr
        filtered = [x for x in sorted_nums if lower_bound <= x <= upper_bound]
        return filtered if filtered else sorted_nums
    elif method == "percentile":
        low_p = percentile_trim[0] / 100.0
        high_p = percentile_trim[1] / 100.0
        min_val = _percentile(sorted_nums, low_p)
        max_val = _percentile(sorted_nums, high_p)
        filtered = [x for x in sorted_nums if min_val <= x <= max_val]
        return filtered if filtered else sorted_nums
    return sorted_nums


def compute_pricing(
    prices: List[float],
    blank_cost: float = 0.0,
    target_margin: Optional[float] = None,
    cfg=config
) -> PricingResult:
    """
    Hàm thuần toán học tính toán khoảng giá đề xuất minh bạch, có kiểm tra giá vốn.
    Không phụ thuộc vào I/O cơ sở dữ liệu.
    """
    clean_prices = [float(p) for p in prices if p is not None and isinstance(p, (int, float)) and p > 0]
    sample_size = len(clean_prices)
    filtered_prices = filter_outliers(clean_prices, method=cfg.OUTLIER_METHOD, k=cfg.IQR_K)
    sample_filtered = len(filtered_prices)
    warnings: List[str] = []

    # Nhánh 1: Đủ dữ liệu thị trường
    if sample_filtered >= cfg.MIN_SAMPLE_LOW:
        sorted_p = sorted(filtered_prices)
        raw_p25 = _percentile(sorted_p, 0.25)
        raw_p50 = _percentile(sorted_p, 0.50)
        raw_p75 = _percentile(sorted_p, 0.75)

        p25 = round_price(raw_p25, cfg.PRICE_ROUND_STEP)
        p50 = round_price(raw_p50, cfg.PRICE_ROUND_STEP)
        p75 = round_price(raw_p75, cfg.PRICE_ROUND_STEP)

        mode = "market" if sample_filtered >= cfg.MIN_SAMPLE_HIGH else "market_low_confidence"
        confidence = "high" if sample_filtered >= cfg.MIN_SAMPLE_HIGH else "low"

        if sample_filtered < cfg.MIN_SAMPLE_HIGH:
            warnings.append(f"Số lượng mẫu đối thủ còn ít ({sample_filtered} sản phẩm), độ tin cậy ở mức tham khảo.")

        suggested_price = p50
        suggested_low = p25
        suggested_high = p75

        # Ràng buộc giá vốn
        if blank_cost > 0:
            if p50 < blank_cost * cfg.COST_FLOOR_RATIO:
                warnings.append("Giá trung bình thị trường đang thấp hơn hoặc sát giá vốn của bạn.")
            
            min_safe_price = round_price(blank_cost * cfg.COST_MIN_SUGGEST_RATIO, cfg.PRICE_ROUND_STEP)
            if suggested_price < min_safe_price:
                suggested_price = min_safe_price
                suggested_low = max(suggested_low, min_safe_price)
                suggested_high = max(suggested_high, suggested_price)
            
            if blank_cost > p75:
                warnings.append("Giá vốn của bạn cao hơn 75% giá thị trường, sản phẩm có thể gặp khó khăn khi cạnh tranh giá.")

        explanation = (
            f"Dựa trên phân tích {sample_filtered} sản phẩm cùng ngành (sau khi lọc ngoại lai), "
            f"khoảng giá giao dịch phổ biến từ {suggested_low:,.0f}đ đến {suggested_high:,.0f}đ. "
            f"Mức giá đề xuất cân bằng: {suggested_price:,.0f}đ."
        ).replace(",", ".")

        return PricingResult(
            mode=mode,
            insufficient_market_data=False,
            sample_size=sample_size,
            sample_size_after_outlier_filter=sample_filtered,
            p25=suggested_low,
            p50=suggested_price,
            p75=suggested_high,
            suggested_price=suggested_price,
            suggested_range=PriceRange(low=suggested_low, high=suggested_high),
            confidence=confidence,
            warnings=warnings,
            explanation=explanation,
        )

    # Nhánh 2: Thiếu dữ liệu thị trường nhưng có giá vốn (Cost-Plus)
    elif blank_cost > 0:
        margin = target_margin if target_margin is not None else cfg.DEFAULT_TARGET_MARGIN
        suggested_price = round_price(blank_cost * (1 + margin), cfg.PRICE_ROUND_STEP)
        low_price = round_price(blank_cost * 1.15, cfg.PRICE_ROUND_STEP)
        high_price = round_price(blank_cost * (1 + margin * 1.5), cfg.PRICE_ROUND_STEP)

        warnings.append("Sàn chưa đủ dữ liệu đối thủ cùng ngành để tính phân vị thị trường.")
        explanation = (
            f"Chưa đủ dữ liệu đối thủ cùng ngành trên sàn ({sample_size} sản phẩm). "
            f"Giá được tính theo phương pháp định giá trên chi phí (Cost-Plus) "
            f"với biên lợi nhuận kỳ vọng {int(margin * 100)}% từ giá vốn {int(blank_cost):,.0f}đ."
        ).replace(",", ".")

        return PricingResult(
            mode="cost_plus",
            insufficient_market_data=True,
            sample_size=sample_size,
            sample_size_after_outlier_filter=sample_filtered,
            p25=low_price,
            p50=suggested_price,
            p75=high_price,
            suggested_price=suggested_price,
            suggested_range=PriceRange(low=low_price, high=high_price),
            confidence="low",
            warnings=warnings,
            explanation=explanation,
        )

    # Nhánh 3: Thiếu cả thị trường lẫn giá vốn
    else:
        warnings.append("Không đủ dữ liệu đối thủ và chưa có giá vốn.")
        explanation = "Chưa đủ dữ liệu đối thủ cùng ngành trên sàn và bạn chưa nhập giá vốn để gợi ý mức giá."
        return PricingResult(
            mode="none",
            insufficient_market_data=True,
            sample_size=sample_size,
            sample_size_after_outlier_filter=sample_filtered,
            p25=0,
            p50=0,
            p75=0,
            suggested_price=0,
            suggested_range=PriceRange(low=0, high=0),
            confidence="none",
            warnings=warnings,
            explanation=explanation,
        )


def fetch_prices_from_db(category_id: Optional[str], db_live: Any) -> List[float]:
    """
    Truy vấn giá sản phẩm cùng category_id từ collection products và product_variants.
    """
    if not category_id or db_live is None:
        return []

    prices: List[float] = []
    try:
        # 1. Tìm trong products theo ObjectId hoặc string
        match_query: Dict[str, Any] = {"is_hidden": {"$ne": True}}
        if ObjectId.is_valid(category_id):
            oid = ObjectId(category_id)
            match_query["$or"] = [
                {"category_ids": oid},
                {"category_id": oid},
                {"categories": category_id}
            ]
        else:
            match_query["$or"] = [
                {"categories": category_id},
                {"category_id": category_id}
            ]

        prods = list(db_live["products"].find(
            match_query,
            {"_id": 1, "min_price": 1, "max_price": 1}
        ).limit(150))

        prod_ids = [p["_id"] for p in prods]

        # 2. Lấy giá từ biến thể hoạt động
        if prod_ids:
            variants = list(db_live["product_variants"].find(
                {"product_id": {"$in": prod_ids}, "is_active": {"$ne": False}},
                {"retail_price": 1}
            ).limit(300))
            for v in variants:
                rp = v.get("retail_price")
                if rp and float(rp) > 0:
                    prices.append(float(rp))

        # 3. Nếu biến thể ít, bổ sung min_price / max_price từ chính sản phẩm
        if len(prices) < 5:
            for p in prods:
                min_p = p.get("min_price")
                max_p = p.get("max_price")
                if min_p and float(min_p) > 0:
                    prices.append(float(min_p))
                if max_p and float(max_p) > 0 and max_p != min_p:
                    prices.append(float(max_p))

    except Exception:
        pass

    return prices
