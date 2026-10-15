import os
import json
from pathlib import Path

try:
    from dotenv import load_dotenv
    app_env_path = Path(__file__).resolve().parent / ".env"
    root_env_path = Path(__file__).resolve().parent.parent / ".env"
    if app_env_path.exists():
        load_dotenv(dotenv_path=app_env_path, override=False)
    if root_env_path.exists():
        load_dotenv(dotenv_path=root_env_path, override=False)
except ImportError:
    pass


class Settings:
    PROJECT_NAME: str = "VietCraft AI Analytics Worker"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    PORT: int = int(os.getenv("PORT", 8000))

    # MongoDB settings (đọc linh hoạt cả MONGODB_URI lẫn MONGO_URI)
    MONGO_URI: str = (
        os.getenv("MONGODB_URI")
        or os.getenv("MONGO_URI")
        or ""
    )
    MONGO_DB_DATA: str = (
        os.getenv("MONGODB_DB")
        or os.getenv("MONGO_DB_DATA")
        or "data-collection"
    )
    MONGO_DB_SEED: str = os.getenv("MONGO_DB_SEED", "vietcraft-seed")
    MONGO_DB_LIVE: str = os.getenv("MONGO_DB_LIVE", "vietcraft")

    # External APIs
    PRINTIFY_TOKEN: str = os.getenv("PRINTIFY_TOKEN", "")
    ETSY_API_KEY: str = os.getenv("ETSY_API_KEY", "")



settings = Settings()

# Biến tương thích nhanh cho module collectors
MONGODB_URI = settings.MONGO_URI
MONGODB_DB = settings.MONGO_DB_DATA

# 2. THAM SỐ NGHIỆP VỤ CÀO DỮ LIỆU GOOGLE TRENDS & PRINTIFY
GEO = "VN"          # Vietnam. Dùng "" cho toàn cầu
LANGUAGE = "vi"

# Google cho phép tối đa 5 từ khóa/request (1 anchor + 4 từ khóa thực tế)
BATCH_SIZE = 4

# Throttling chống chặn HTTP 429 từ Google Trends
REQUEST_DELAY = 5.0
SLEEP_MIN = 15.0
SLEEP_MAX = 25.0
MAX_RETRIES = 4
TRENDSPY_RETRIES = 1
RETRY_BASE = 60.0

DISCOVERY_MAX_SEEDS_PER_RUN = 10

# Bộ lọc từ khóa thương mại / phi thương mại
PRODUCT_WORDS = [
    "áo", "cốc", "ly", "túi", "tote", "tranh", "poster", "sticker", "móc khóa",
    "quà", "nón", "mũ", "gối", "sổ", "lịch", "hoodie", "shirt", "tee", "mug",
    "bag", "print", "gift", "canvas",
]

NON_COMMERCIAL_WORDS = [
    "wallpaper", "hình nền", "download", "tải", "xem", "tập", "phần",
    "lyrics", "lời bài hát", "review", "nghĩa là", "là gì", "cách", "hướng dẫn",
    "full", "vietsub", "trailer", "spoiler", "raw", "manga", "truyện",
]

# Timezone offset: VN là UTC+7 -> -420
TZ_OFFSET = -420

TIMEFRAME_DAILY = "today 3-m"    # ~90 ngày gần nhất (cho ARIMA / Anomaly)
TIMEFRAME_WEEKLY = "today 5-y"   # ~260 tuần / 5 năm (cho STL Seasonality)

# Từ khóa mốc cố định: Có lượng tìm kiếm ổn định quanh năm (ít biến động mùa vụ)
ANCHOR = "quà sinh nhật"

# 3. NẠP TỪ KHÓA HẠT GIỐNG TỪ FILE JSON RIÊNG BIỆT (DATA-DRIVEN)
def load_seed_keywords():
    json_path = Path(__file__).resolve().parent / "data" / "seed_keywords.json"
    if json_path.exists():
        with open(json_path, mode="r", encoding="utf-8") as f:
            data = json.load(f)
            return [(item["keyword"], item["product_type"], item["topic"]) for item in data]
    return []


SEED_KEYWORDS = load_seed_keywords()

