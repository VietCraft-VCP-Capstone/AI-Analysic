import json
import re
from pathlib import Path
from typing import Any

from app.api.v1._mart import client_dung_chung
from app.core.f29.paths import CONFIG


MODEL_VERSION = "health-5.0"

STORE_DB = "vietcraft"

MIN_TITLE_LENGTH = 20
MAX_TITLE_LENGTH = 120

MIN_CATEGORY_SAMPLE = 8

BLOCKING_FIELDS = ("title", "materials", "moderation_status", "images", "variants.retail_price")

K_BAYESIAN_SHRINKAGE = 50

EFFORT = {"image": 1, "tags": 1, "material": 1, "description": 2, "price": 2, "review": 3,
          "images": 1, "materials": 1, "title": 1, "moderation_status": 3,
          "variants.retail_price": 1, "variants.stock": 1, "categories": 1}


KEYS = ("image", "description", "tags", "review", "price")

LABELS = {
    "image": "Hình ảnh",
    "description": "Mô tả",
    "tags": "Tag",
    "review": "Đánh giá",
    "price": "Giá bán",
}


def desc_words(text: str | None) -> int:
    if not text or not isinstance(text, str):
        return 0
    return len({t for t in re.findall(r"\w+", text.lower()) if len(t) >= 2 and not t.isdigit()})



def review_score(n_good: int, n: int, p0: float, m: float) -> float:
    if n <= 0:
        return 0.0
    return (n_good + m * p0) / (n + m) * 100.0


WEIGHTS_PATH = CONFIG / "health_weights.json"
_cache: dict[Path, dict] = {}


def _valid(data: Any) -> bool:
    try:
        return abs(sum(data["weights"][k] for k in KEYS) - 100) < 1e-6 and "m" in data["review"]
    except (KeyError, TypeError):
        return False


def _read(path: Path) -> dict:
    try:
        data = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError) as e:
        raise RuntimeError("health weights missing") from e
    if not _valid(data):
        raise RuntimeError("health weights missing")
    return data


def load(path: Path | None = None) -> dict:
    path = path or WEIGHTS_PATH
    if path not in _cache:
        _cache[path] = _read(path)
    return _cache[path]


def clear_cache() -> None:
    _cache.clear()


def store_db():
    return client_dung_chung()[STORE_DB]
