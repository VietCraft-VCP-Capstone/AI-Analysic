import math
import re
from typing import Any, Dict, List, Optional

from bson import ObjectId

from app.services.f42 import config
from app.services.f42.schemas import ComparableItem, PriceRange, PricingResult
from app.services.f42.vi_text import contains_phrase_lenient, normalize_nfc


# ---------------------------------------------------------------------------
# Nhận diện chất liệu (chỉ để TỰ ĐIỀN ô chất liệu, KHÔNG dùng để nhân giá).
# Ảnh hưởng của chất liệu lên giá được học từ các tin tương đồng (comparable_pricing).
#
# Quy tắc chống nhận nhầm trên sàn đa ngành hàng:
#   - So khớp CÓ DẤU theo ranh giới từ ("sứ" ≠ "su" trong "cao su", "len" ≠ "lên").
#   - Không dùng từ đơn mơ hồ: "đồng" (đồng hồ), "bạc"/"vàng" (màu bạc, màu vàng).
#   - Bỏ qua khi đứng sau "màu", "vân", "giả", "họa tiết" ("màu gỗ", "vân gỗ", "giả da").
# ---------------------------------------------------------------------------
MATERIAL_KEYWORDS: List[str] = [
    # kim loại
    "inox 304", "inox 316", "inox 201", "thép không gỉ", "inox", "thép", "nhôm", "hợp kim",
    "titan", "đồng thau", "đồng đỏ", "đồng nguyên chất", "bạc 925", "bạc ta", "bạc s925",
    "vàng 10k", "vàng 14k", "vàng 18k", "vàng 24k", "mạ vàng", "mạ bạc", "gang",
    # da
    "da bò thật", "da bò sáp", "da bò", "da cừu", "da cá sấu", "da thật", "da pu", "da tổng hợp",
    "simili", "da lộn",
    # vải
    "cotton 100%", "cotton", "polyester", "spandex", "thun lạnh", "nỉ bông", "nỉ", "len lông cừu",
    "len", "linen", "vải lanh", "đũi", "kaki", "jean", "denim", "voan", "chiffon", "lụa tơ tằm",
    "tơ tằm", "lụa", "canvas", "vải bố", "vải dù", "nhung", "ren", "lông vũ", "cashmere",
    # gỗ / tự nhiên
    "gỗ sồi", "gỗ óc chó", "gỗ thông", "gỗ cao su", "gỗ keo", "gỗ hương", "gỗ mun", "gỗ trắc",
    "gỗ tràm", "gỗ mdf", "gỗ tự nhiên", "gỗ", "tre", "mây", "cói", "lục bình", "trầm hương",
    # gốm, đá, thủy tinh
    "gốm sứ", "gốm", "sứ", "thủy tinh", "pha lê", "đá cẩm thạch", "đá thạch anh", "đá tự nhiên",
    "đá mã não", "ngọc bích",
    # nhựa, cao su
    "nhựa abs", "nhựa pp", "nhựa pvc", "nhựa", "silicone", "cao su", "mica", "acrylic", "carbon",
]
_NEGATIVE_PREV_WORDS = {"màu", "vân", "giả", "tiết", "kiểu", "phong"}
_NEGATIVE_NEXT = {"tre": {"em", "trung"}, "len": {"đồ", "xuống"}}
_MATERIAL_SORTED = sorted(MATERIAL_KEYWORDS, key=len, reverse=True)


def detect_material(text: Optional[str]) -> str:
    """Trả về tên chất liệu được nhắc rõ trong tiêu đề, hoặc chuỗi rỗng."""
    if not text or not str(text).strip():
        return ""
    t = f" {normalize_nfc(text).lower()} "
    t = re.sub(r"[^\w%\s]", " ", t, flags=re.UNICODE)
    t = re.sub(r"\s+", " ", t)
    for kw in _MATERIAL_SORTED:
        for m in re.finditer(rf"(?<![\w]){re.escape(kw)}(?![\w])", t, flags=re.UNICODE):
            before = t[:m.start()].split()
            after = t[m.end():].split()
            if before and before[-1] in _NEGATIVE_PREV_WORDS:
                continue
            if kw in _NEGATIVE_NEXT and after and after[0] in _NEGATIVE_NEXT[kw]:
                continue
            return kw[:1].upper() + kw[1:]
    return ""


def to_float_price(val: Any) -> Optional[float]:
    """Chuyển đổi an toàn giá trị giá từ MongoDB (hỗ trợ Decimal128, int, float, str)."""
    if val is None:
        return None
    try:
        if hasattr(val, "to_decimal"):
            f = float(val.to_decimal())
        else:
            f = float(val)
        return f if f > 0 else None
    except (ValueError, TypeError):
        return None


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


def format_vnd(amount: float) -> str:
    """Định dạng số tiền VND theo chuẩn Việt Nam (VD: 250.000đ)."""
    return f"{int(round(amount)):,}".replace(",", ".") + "đ"


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


def _apply_cost_floor(
    p25: int, p50: int, p75: int, blank_cost: float, warnings: List[str], cfg=config
) -> tuple:
    """Không bao giờ gợi ý giá khiến seller bán dưới giá vốn + biên tối thiểu."""
    if blank_cost <= 0:
        return p25, p50, p75
    if p50 < blank_cost * cfg.COST_FLOOR_RATIO:
        warnings.append("Giá thị trường của sản phẩm tương tự đang thấp hơn hoặc sát giá vốn của bạn.")
    min_safe = round_price(blank_cost * cfg.COST_MIN_SUGGEST_RATIO, cfg.PRICE_ROUND_STEP)
    if p50 < min_safe:
        p50 = min_safe
        p25 = max(p25, min_safe)
        p75 = max(p75, p50)
    if blank_cost > p75:
        warnings.append("Giá vốn của bạn cao hơn 75% sản phẩm tương tự, sẽ khó cạnh tranh về giá.")
    return p25, p50, p75


def pricing_from_comparables(est: Any, blank_cost: float = 0.0, cfg=config) -> PricingResult:
    """Chuyển ComparableEstimate thành PricingResult có giải thích và bằng chứng."""
    if not est or not est.usable or est.p50 <= 0 or est.n_used == 0:
        return PricingResult(
            mode="none",
            method="none",
            insufficient_market_data=True,
            sample_size=getattr(est, "n_used", 0) if est else 0,
            sample_size_after_outlier_filter=getattr(est, "n_used", 0) if est else 0,
            p25=0,
            p50=0,
            p75=0,
            p90=0,
            suggested_price=0,
            suggested_range=PriceRange(low=0, high=0),
            confidence="none",
            warnings=["Chưa đủ sản phẩm tương đồng để định giá thị trường."],
            explanation="Chưa đủ sản phẩm tương đồng đáng tin cậy trên thị trường.",
            source_label="Chưa đủ dữ liệu",
        )

    warnings: List[str] = []
    p25, p50, p75 = _apply_cost_floor(est.p25, est.p50, est.p75, blank_cost, warnings, cfg)

    if est.confidence == "low":
        warnings.append(
            "Các sản phẩm tìm được chưa thật giống hoặc giá phân tán rộng — hãy coi đây là mức tham khảo "
            "và bổ sung tiêu đề cụ thể hơn (loại sản phẩm, thương hiệu, chất liệu, kích thước)."
        )

    n_live = sum(1 for c in est.comparables if c.source == "vietcraft")
    source_note = f"{est.n_used} sản phẩm tương tự"
    if n_live:
        source_note += f" (trong đó {n_live} sản phẩm đang bán trên sàn)"

    parts = [f"Dựa trên {source_note}"]
    if est.detected_product:
        parts[0] += f" cùng loại \"{est.detected_product}\""
    if est.detected_brand and est.brand_median:
        parts.append(f"các tin cùng thương hiệu {est.detected_brand} có giá trung vị {format_vnd(est.brand_median)}")
    explanation = (
        "; ".join(parts)
        + f". Khoảng giá phổ biến {format_vnd(p25)} – {format_vnd(p75)}, mức đề xuất cân bằng {format_vnd(p50)}."
    )

    comparables = [
        ComparableItem(
            title=c.title[:140], price=int(round(c.price)), similarity=round(c.similarity, 3), source=c.source
        )
        for c in est.comparables[:8]
    ]

    source_label = f"Đối chiếu từ {est.n_used} sản phẩm tương đồng (Độ tương đồng TB {int(est.mean_similarity * 100)}%)"

    return PricingResult(
        mode="market" if est.confidence in ("high", "medium") else "market_low_confidence",
        method="comparables",
        insufficient_market_data=False,
        sample_size=est.n_used,
        sample_size_after_outlier_filter=est.n_used,
        p25=p25,
        p50=p50,
        p75=p75,
        p90=max(est.p90, p75),
        suggested_price=p50,
        suggested_range=PriceRange(low=p25, high=p75),
        confidence=est.confidence,
        warnings=warnings,
        explanation=explanation,
        comparables=comparables,
        detected_product=est.detected_product,
        detected_brand=est.detected_brand,
        source_label=source_label,
    )


def compute_pricing(
    prices: List[float],
    blank_cost: float = 0.0,
    target_margin: Optional[float] = None,
    material: Optional[str] = None,
    cfg=config
) -> PricingResult:
    """
    Phương án dự phòng khi không tìm được sản phẩm tương đồng:
    phân vị giá của cả danh mục trên sàn, hoặc Cost-Plus từ giá vốn.
    """
    clean_prices = []
    for p in prices:
        fp = to_float_price(p)
        if fp is not None and fp > 0:
            clean_prices.append(fp)

    sample_size = len(clean_prices)
    filtered_prices = filter_outliers(clean_prices, method=cfg.OUTLIER_METHOD, k=cfg.IQR_K)
    sample_filtered = len(filtered_prices)
    warnings: List[str] = []

    # Nhánh 1: Đủ dữ liệu giá của cả danh mục
    if sample_filtered >= cfg.MIN_SAMPLE_LOW:
        sorted_p = sorted(filtered_prices)
        p25 = round_price(_percentile(sorted_p, 0.25), cfg.PRICE_ROUND_STEP)
        p50 = round_price(_percentile(sorted_p, 0.50), cfg.PRICE_ROUND_STEP)
        p75 = round_price(_percentile(sorted_p, 0.75), cfg.PRICE_ROUND_STEP)
        p90 = round_price(_percentile(sorted_p, 0.90), cfg.PRICE_ROUND_STEP)
        p25 = min(p25, p50)
        p75 = max(p75, p50)

        warnings.append(
            "Không tìm thấy sản phẩm thật sự giống, giá đang tính theo toàn bộ danh mục nên chỉ mang tính tham khảo."
        )
        p25, p50, p75 = _apply_cost_floor(p25, p50, p75, blank_cost, warnings, cfg)

        explanation = (
            f"Dựa trên {sample_filtered} sản phẩm cùng danh mục trên sàn (sau khi lọc ngoại lai), "
            f"khoảng giá phổ biến {format_vnd(p25)} – {format_vnd(p75)}. "
            f"Mức đề xuất cân bằng: {format_vnd(p50)}."
        )

        return PricingResult(
            mode="market_low_confidence",
            method="category_market",
            insufficient_market_data=False,
            sample_size=sample_size,
            sample_size_after_outlier_filter=sample_filtered,
            p25=p25,
            p50=p50,
            p75=p75,
            p90=max(p90, p75),
            suggested_price=p50,
            suggested_range=PriceRange(low=p25, high=p75),
            confidence="low",
            warnings=warnings,
            explanation=explanation,
            source_label=f"Thống kê {sample_filtered} sản phẩm cùng danh mục",
        )

    # Nhánh 2: Thiếu dữ liệu thị trường nhưng có giá vốn (Cost-Plus)
    elif blank_cost > 0:
        margin = target_margin if target_margin is not None else cfg.DEFAULT_TARGET_MARGIN
        suggested_price = round_price(blank_cost * (1 + margin), cfg.PRICE_ROUND_STEP)
        low_price = round_price(blank_cost * 1.15, cfg.PRICE_ROUND_STEP)
        high_price = round_price(blank_cost * (1 + margin * 1.5), cfg.PRICE_ROUND_STEP)

        warnings.append("Chưa tìm thấy sản phẩm tương tự để so giá thị trường.")
        explanation = (
            f"Chưa đủ dữ liệu sản phẩm tương tự. "
            f"Giá được tính theo phương pháp định giá trên chi phí (Cost-Plus) "
            f"với biên lợi nhuận kỳ vọng {int(margin * 100)}% từ giá vốn {format_vnd(blank_cost)}."
        )

        return PricingResult(
            mode="cost_plus",
            method="cost_plus",
            insufficient_market_data=True,
            sample_size=0,
            sample_size_after_outlier_filter=0,
            p25=low_price,
            p50=suggested_price,
            p75=high_price,
            p90=high_price,
            suggested_price=suggested_price,
            suggested_range=PriceRange(low=low_price, high=high_price),
            confidence="low",
            warnings=warnings,
            explanation=explanation,
            source_label="Ước tính theo giá vốn (Cost-Plus)",
        )

    # Nhánh 3: Thiếu cả thị trường lẫn giá vốn
    else:
        warnings.append("Không tìm thấy sản phẩm tương tự và chưa có giá vốn.")
        explanation = (
            "Chưa đủ dữ liệu để đề xuất giá. Chưa tìm thấy sản phẩm tương tự để so giá. Hãy ghi tiêu đề cụ thể hơn "
            "(loại sản phẩm, thương hiệu, chất liệu, kích thước) hoặc nhập giá vốn để AI tính giá."
        )
        return PricingResult(
            mode="none",
            method="none",
            insufficient_market_data=True,
            sample_size=0,
            sample_size_after_outlier_filter=0,
            p25=0,
            p50=0,
            p75=0,
            p90=0,
            suggested_price=0,
            suggested_range=PriceRange(low=0, high=0),
            confidence="none",
            warnings=warnings,
            explanation=explanation,
            source_label="Chưa đủ dữ liệu",
        )


def fetch_prices_from_db(
    category_id: Optional[str],
    db_live: Any,
    material: Optional[str] = None
) -> List[float]:
    """
    Truy vấn giá sản phẩm cùng category_id từ collection products và product_variants.
    Hỗ trợ ưu tiên biến thể hoặc sản phẩm có cùng chất liệu khi có sẵn dữ liệu.
    """
    if not category_id or db_live is None:
        return []

    prices: List[float] = []
    mat_specific_prices: List[float] = []

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
            {"_id": 1, "title": 1, "min_price": 1, "max_price": 1}
        ).limit(150))

        prod_ids = [p["_id"] for p in prods]
        prod_title_map = {p["_id"]: p.get("title", "") for p in prods}

        # 2. Lấy giá từ biến thể hoạt động
        if prod_ids:
            variants = list(db_live["product_variants"].find(
                {"product_id": {"$in": prod_ids}, "is_active": {"$ne": False}},
                {"retail_price": 1, "material": 1, "product_id": 1}
            ).limit(300))

            for v in variants:
                val = to_float_price(v.get("retail_price"))
                if val:
                    prices.append(val)
                    if material:
                        v_mat = v.get("material") or ""
                        p_title = prod_title_map.get(v.get("product_id"), "")
                        if (v_mat and contains_phrase_lenient(v_mat, material)) or \
                           (p_title and contains_phrase_lenient(p_title, material)):
                            mat_specific_prices.append(val)

        # 3. Bổ sung min_price / max_price từ chính sản phẩm nếu ít biến thể
        if len(prices) < 5:
            for p in prods:
                min_p = to_float_price(p.get("min_price"))
                max_p = to_float_price(p.get("max_price"))
                if min_p:
                    prices.append(min_p)
                if max_p and max_p != min_p:
                    prices.append(max_p)

        # Nếu tìm thấy đủ mẫu cùng chất liệu (>= 5 sản phẩm), ưu tiên mẫu đó
        if len(mat_specific_prices) >= 5:
            return mat_specific_prices

    except Exception:
        pass

    return prices
