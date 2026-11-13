import logging
import math
import re
from typing import Any, Dict, List, Optional

from bson import ObjectId

from app.services.f42 import config
from app.services.f42.schemas import ComparableItem, PriceRange, PricingResult
from app.services.f42.vi_text import contains_phrase_lenient, normalize_nfc

logger = logging.getLogger(__name__)


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
    "gỗ nghiến", "gỗ teak", "gỗ lim", "gỗ xoan", "gỗ cẩm", "gỗ walnut",
    # sáp nến
    "sáp đậu nành", "sáp ong", "sáp dừa", "sáp parafin", "parafin",
    # nhựa/khác hay gặp
    "melamine", "nhôm đúc", "gang đúc", "đá marble", "đá granite",
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
    # Làm tròn nửa lên (round() của Python làm tròn về số chẵn: 2.500 → 2.000 nhưng 3.500 → 4.000)
    return int(math.floor(val / step + 0.5) * step)


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
    market_p75 = p75
    if p50 < blank_cost * cfg.COST_FLOOR_RATIO:
        warnings.append("Giá thị trường của sản phẩm tương tự đang thấp hơn hoặc sát giá vốn của bạn.")
    min_safe = round_price(blank_cost * cfg.COST_MIN_SUGGEST_RATIO, cfg.PRICE_ROUND_STEP)
    if p50 < min_safe:
        p50 = min_safe
        p25 = max(p25, min_safe)
        p75 = max(p75, p50)
    if blank_cost > market_p75:
        warnings.append("Giá vốn của bạn cao hơn 75% sản phẩm tương tự, sẽ khó cạnh tranh về giá.")
    return p25, p50, p75


def _floor_note(market_p50: int, suggested: int) -> str:
    if suggested > market_p50:
        return (f" Giá đề xuất đã được nâng lên {format_vnd(suggested)} (giá vốn × "
                f"{str(config.COST_MIN_SUGGEST_RATIO).replace('.', ',')}) để không bán lỗ.")
    return ""


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
    m25, m50, m75 = est.p25, est.p50, est.p75  # phân vị thị trường thật, trước khi áp giá vốn
    p25, p50, p75 = _apply_cost_floor(m25, m50, m75, blank_cost, warnings, cfg)

    if getattr(est, "match_note", None):
        warnings.append(est.match_note)
    if est.confidence == "low":
        warnings.append(
            "Các sản phẩm tìm được chưa thật giống hoặc giá chênh nhau nhiều, giá chỉ để tham khảo. "
            "Ghi tên rõ hơn (loại sản phẩm, thương hiệu, chất liệu, kích thước) để có giá sát hơn."
        )

    n_live = sum(1 for c in est.comparables if c.source == "vietcraft")
    n_sold = sum(1 for c in est.comparables if c.source == "vietcraft_sold" or (c.source == "vietcraft" and c.sold > 0))
    n_fresh = sum(1 for c in est.comparables if c.source == "tiki_fresh")
    source_note = f"{est.n_used} sản phẩm tương tự"
    notes = []
    if n_live:
        notes.append(f"{n_live} sản phẩm đang bán trên sàn")
    if n_sold:
        notes.append(f"{n_sold} sản phẩm đã bán thành công trên sàn")
    if n_fresh:
        notes.append(f"{n_fresh} sản phẩm Tiki giá cập nhật trong 14 ngày, đã có người mua")
    sold_total = sum(c.sold for c in est.comparables)
    if sold_total:
        notes.append(f"tổng đã bán {sold_total:,}".replace(",", "."))
    if notes:
        source_note += f" (trong đó {'; '.join(notes)})"

    parts = [f"Dựa trên {source_note}"]
    if est.detected_product:
        parts[0] += f" cùng loại \"{est.detected_product}\""
    if est.detected_brand and est.brand_median:
        parts.append(f"các tin cùng thương hiệu {est.detected_brand} có giá trung vị {format_vnd(est.brand_median)}")
    explanation = (
        "; ".join(parts)
        + f". Giá thị trường P25: {format_vnd(m25)}, trung vị P50: {format_vnd(m50)}, P75: {format_vnd(m75)}."
        + _floor_note(m50, p50)
    )

    comparables = [
        ComparableItem(
            title=c.title[:140],
            price=int(round(c.price)),
            similarity=round(c.similarity, 3),
            source={"vietcraft": "Sàn VietCraft", "vietcraft_sold": "Sàn VietCraft (giá đã bán)",
                    "tiki_fresh": "Tiki (giá mới cập nhật)"}.get(c.source, "Thị trường TMĐT")
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
        m25, m50, m75 = p25, p50, p75
        p25, p50, p75 = _apply_cost_floor(p25, p50, p75, blank_cost, warnings, cfg)

        explanation = (
            f"Dựa trên {sample_filtered} sản phẩm cùng danh mục trên sàn (sau khi lọc ngoại lai), "
            f"khoảng giá phổ biến {format_vnd(m25)} – {format_vnd(m75)}, trung vị {format_vnd(m50)}. "
            f"Mức đề xuất: {format_vnd(p50)}." + _floor_note(m50, p50)
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
        # Khoảng giá luôn chứa giá đề xuất (biên mục tiêu < 15% từng cho low > giá đề xuất)
        low_price = min(round_price(blank_cost * 1.15, cfg.PRICE_ROUND_STEP), suggested_price)
        high_price = max(round_price(blank_cost * (1 + margin * 1.5), cfg.PRICE_ROUND_STEP), suggested_price)

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


def _variant_min_prices(db_live: Any, product_ids: List[Any], chunk: int = 5000) -> Dict[Any, float]:
    """Giá bán thấp nhất (retail_price) của các biến thể đang hoạt động, theo product_id."""
    out: Dict[Any, float] = {}
    for i in range(0, len(product_ids), chunk):
        batch = product_ids[i:i + chunk]
        rows = db_live["product_variants"].aggregate([
            {"$match": {"product_id": {"$in": batch}, "is_active": {"$ne": False}}},
            {"$group": {"_id": "$product_id", "min_price": {"$min": "$retail_price"}}},
        ])
        for r in rows:
            val = to_float_price(r.get("min_price"))
            if val:
                out[r["_id"]] = val
    return out


def fetch_live_listings(
    db_live: Any,
    extra_filter: Optional[Dict[str, Any]] = None,
    limit: int = config.LIVE_MAX_PRODUCTS,
    cfg=config,
) -> List[Dict[str, Any]]:
    """
    Sản phẩm đang bán công khai trên sàn kèm giá thật.

    Giá lấy từ product_variants.retail_price (Decimal128) — collection products KHÔNG có
    min_price/max_price. Mỗi sản phẩm chỉ đóng góp MỘT giá (biến thể rẻ nhất) để không
    đếm trùng. Nếu một bản ghi cũ có min_price thì dùng làm phương án dự phòng.
    """
    if db_live is None:
        return []
    query: Dict[str, Any] = dict(cfg.LIVE_PRODUCT_FILTER)
    if extra_filter:
        query = {"$and": [query, extra_filter]}
    try:
        prods = list(db_live["products"].find(
            query,
            {"title": 1, "category_ids": 1, "categories": 1, "tags": 1, "materials": 1,
             "min_price": 1, "max_price": 1},
        ).limit(limit))
        price_map = _variant_min_prices(db_live, [p["_id"] for p in prods]) if prods else {}
    except Exception as exc:  # DB lỗi không được làm hỏng cả response
        logger.warning("f42.fetch_live_listings_failed", extra={"error": str(exc)})
        return []

    rows: List[Dict[str, Any]] = []
    for p in prods:
        price = price_map.get(p["_id"]) or to_float_price(p.get("min_price")) or to_float_price(p.get("max_price"))
        if not price:
            continue
        rows.append({
            "_id": p["_id"],
            "title": normalize_nfc(p.get("title") or ""),
            "price": price,
            "category_ids": [str(c) for c in (p.get("category_ids") or [])],
            "tags": [t for t in (p.get("tags") or []) if isinstance(t, str)],
            "materials": [m for m in (p.get("materials") or []) if isinstance(m, str)],
        })
    return rows


SOLD_LOOKBACK_DAYS = 180


def fetch_sold_items(db_live: Any, days: int = SOLD_LOOKBACK_DAYS) -> Dict[Any, Dict[str, Any]]:
    """
    Giá bán THẬT trên sàn: món hàng trong đơn đã giao thành công trong `days` ngày gần nhất.
    Bỏ đơn giả lập (is_simulated), đơn chưa giao/huỷ và đơn đã hoàn tiền — chỉ giữ giá người mua
    thực sự trả và giữ lại. Trả theo product_id: {title, price (giá niêm yết lúc bán, trung vị), qty}.
    """
    from datetime import datetime, timedelta, timezone
    from statistics import median

    if db_live is None:
        return {}
    since = datetime.now(timezone.utc) - timedelta(days=days)
    try:
        rows = db_live["orders"].aggregate([
            {"$match": {
                "is_simulated": {"$ne": True},
                "order_status": "DELIVERED",
                "refund_status": {"$ne": "REFUNDED"},
                "created_at": {"$gte": since},
            }},
            {"$unwind": "$items"},
            {"$project": {"pid": "$items.product_id", "title": "$items.title",
                          "price": "$items.retail_price", "qty": "$items.quantity"}},
        ])
        out: Dict[Any, Dict[str, Any]] = {}
        for r in rows:
            price = to_float_price(r.get("price"))
            if not price or not r.get("pid"):
                continue
            e = out.setdefault(r["pid"], {"title": normalize_nfc(r.get("title") or ""), "prices": [], "qty": 0})
            e["prices"].append(price)
            e["qty"] += max(1, int(r.get("qty") or 1))
        return {pid: {"title": e["title"], "price": float(median(e["prices"])), "qty": e["qty"]}
                for pid, e in out.items()}
    except Exception as exc:  # DB lỗi không được làm hỏng gợi ý giá
        logger.warning("f42.fetch_sold_items_failed", extra={"error": str(exc)})
        return {}


def fetch_prices_from_db(
    category_id: Optional[str],
    db_live: Any,
    material: Optional[str] = None
) -> List[float]:
    """
    Giá (mỗi sản phẩm một giá) của các sản phẩm đang bán cùng danh mục.
    Nếu có >= MIN_SAMPLE_LOW sản phẩm cùng chất liệu thì ưu tiên nhóm đó.
    """
    if not category_id or db_live is None:
        return []
    ors: List[Dict[str, Any]] = [{"categories": category_id}]
    if ObjectId.is_valid(category_id):
        ors.append({"category_ids": ObjectId(category_id)})
    rows = fetch_live_listings(db_live, {"$or": ors}, limit=500)
    prices = [r["price"] for r in rows]
    if material:
        mat_prices = [
            r["price"] for r in rows
            if any(contains_phrase_lenient(m, material) for m in r["materials"])
            or contains_phrase_lenient(r["title"], material)
        ]
        if len(mat_prices) >= config.MIN_SAMPLE_LOW:
            return mat_prices
    return prices
