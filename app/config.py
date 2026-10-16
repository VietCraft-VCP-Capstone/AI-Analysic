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

MONGODB_URI = settings.MONGO_URI
MONGODB_DB = settings.MONGO_DB_DATA

GEO = "VN"
LANGUAGE = "vi"

BATCH_SIZE = 4

REQUEST_DELAY = 5.0
SLEEP_MIN = 15.0
SLEEP_MAX = 25.0
MAX_RETRIES = 4
TRENDSPY_RETRIES = 1
RETRY_BASE = 60.0

DISCOVERY_MAX_SEEDS_PER_RUN = 10

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

TZ_OFFSET = -420

TIMEFRAME_DAILY = "today 3-m"
TIMEFRAME_WEEKLY = "today 5-y"

ANCHOR = "quà sinh nhật"

def load_seed_keywords():
    json_path = Path(__file__).resolve().parent / "data" / "seed_keywords.do-not-remove.json"
    if json_path.exists():
        with open(json_path, mode="r", encoding="utf-8") as f:
            data = json.load(f)
            return [(item["keyword"], item["product_type"], item["topic"]) for item in data]
    return []


SEED_KEYWORDS = load_seed_keywords()

