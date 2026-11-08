import os
from typing import Any, Dict, List, Tuple

MIN_SAMPLE_HIGH: int = int(os.getenv("F42_MIN_SAMPLE_HIGH", 10))
MIN_SAMPLE_LOW: int = int(os.getenv("F42_MIN_SAMPLE_LOW", 5))
OUTLIER_METHOD: str = os.getenv("F42_OUTLIER_METHOD", "iqr")
IQR_K: float = float(os.getenv("F42_IQR_K", 1.5))
PERCENTILE_TRIM: Tuple[int, int] = (5, 95)
COST_FLOOR_RATIO: float = float(os.getenv("F42_COST_FLOOR_RATIO", 1.15))
COST_MIN_SUGGEST_RATIO: float = float(os.getenv("F42_COST_MIN_SUGGEST_RATIO", 1.30))
DEFAULT_TARGET_MARGIN: float = float(os.getenv("F42_DEFAULT_TARGET_MARGIN", 0.30))
PRICE_ROUND_STEP: int = int(os.getenv("F42_PRICE_ROUND_STEP", 1000))

CATEGORY_MIN_SCORE: float = float(os.getenv("F42_CATEGORY_MIN_SCORE", 0.25))
CATEGORY_TOP_K: int = int(os.getenv("F42_CATEGORY_TOP_K", 3))
CATEGORY_AUTOCONFIRM_SCORE: float = float(os.getenv("F42_CATEGORY_AUTOCONFIRM_SCORE", 0.60))

TAG_TOP_N: int = int(os.getenv("F42_TAG_TOP_N", 10))
TAG_MIN_FREQ: int = int(os.getenv("F42_TAG_MIN_FREQ", 2))
TAG_GENERIC_STOPLIST: List[str] = [
    "đẹp", "hot", "rẻ", "tốt", "hàng mới", "giá rẻ", "freeship", "xinh", "cao cấp", "uy tín", "chất lượng"
]

LLM_MODEL: str = os.getenv("F42_LLM_MODEL", "gemini-2.5-flash")
# Model dự phòng khi model chính lỗi (phân tách bằng dấu phẩy). Giữ ngắn để không cộng dồn timeout.
LLM_FALLBACK_MODELS: List[str] = [
    m.strip() for m in os.getenv("F42_LLM_FALLBACK_MODELS", "gemini-flash-latest").split(",") if m.strip()
]
LLM_TEMPERATURE: float = float(os.getenv("F42_LLM_TEMPERATURE", 0.4))
LLM_TOP_P: float = float(os.getenv("F42_LLM_TOP_P", 0.9))
LLM_MAX_OUTPUT_TOKENS: int = int(os.getenv("F42_LLM_MAX_OUTPUT_TOKENS", 1500))
LLM_TIMEOUT_S: int = int(os.getenv("F42_LLM_TIMEOUT_S", 12))
LLM_MAX_RETRIES: int = int(os.getenv("F42_LLM_MAX_RETRIES", 2))
CACHE_TTL_S: int = int(os.getenv("F42_CACHE_TTL_S", 3600))
USE_REFERENCE_TITLES: bool = os.getenv("F42_USE_REFERENCE_TITLES", "false").lower() in ("true", "1", "yes")

RISKY_CLAIMS: List[str] = [
    "da thật", "chính hãng", "an toàn sức khỏe", "không độc hại", "organic", "hữu cơ",
    "fda", "iso", "nhập khẩu", "bảo hành", "hoàn tiền", "tốt nhất", "số 1", "rẻ nhất",
    "duy nhất", "cam kết 100%", "điều trị", "trị mụn", "trị nám", "chữa bệnh", "chữa trị",
    "giảm cân", "chống lão hóa", "authentic", "hàng hiệu", "100% hình ảnh thực tế", "đổi trả",
    "miễn phí vận chuyển", "kiểm định chất lượng"
]

# Sản phẩm đang bán công khai trên sàn — trùng với điều kiện PUBLIC của BE (ProductsService.suggest).
# Đặt F42_LIVE_FILTER_STRICT=false nếu DB seed chưa có listing_status / moderation_status.
LIVE_FILTER_STRICT: bool = os.getenv("F42_LIVE_FILTER_STRICT", "true").lower() in ("true", "1", "yes")
LIVE_PRODUCT_FILTER: Dict[str, Any] = (
    {"status": "PUBLISHED", "is_hidden": {"$ne": True}, "listing_status": "ACTIVE", "moderation_status": "APPROVED"}
    if LIVE_FILTER_STRICT
    else {"is_hidden": {"$ne": True}, "status": {"$nin": ["DRAFT", "UNPUBLISHED"]}}
)
LIVE_MAX_PRODUCTS: int = int(os.getenv("F42_LIVE_MAX_PRODUCTS", 20000))

# Từ khóa tìm kiếm trên sàn: số từ tối đa phải cùng xuất hiện trong tiêu đề khi tìm sản phẩm tương tự.
INTERNAL_MATCH_TOKENS: int = int(os.getenv("F42_INTERNAL_MATCH_TOKENS", 3))
GOOGLE_SUGGEST_ENABLED: bool = os.getenv("F42_GOOGLE_SUGGEST_ENABLED", "true").lower() in ("true", "1", "yes")
GOOGLE_SUGGEST_TIMEOUT_S: float = float(os.getenv("F42_GOOGLE_SUGGEST_TIMEOUT_S", 2.0))

KNOWN_MATERIALS: List[str] = [
    "cotton", "polyester", "len", "gỗ", "inox", "nhựa", "silicone", "thủy tinh", "gốm",
    "sứ", "kim loại", "vải", "lụa", "thép", "nhôm", "sáp", "da pu", "da thật", "da bò",
    "bạc", "đồng", "vàng", "đá tự nhiên", "canvas", "kaki", "tơ tằm", "mây", "tre", "cói"
]
