import json
from pathlib import Path
from typing import Any

from app.core.f29.factors import KEYS

WEIGHTS_PATH = Path(__file__).parent / "health_weights.json"
TARGET_KEYS = ("image", "description", "tags")
PRICE_KEYS = ("low_full", "full_at", "zero_at", "floor_at", "min_peers")
_cache: dict[Path, dict] = {}


def _valid(data: Any) -> bool:
    try:
        return (sum(data["weights"][k] for k in KEYS) == 100
                and all(k in data["targets"] for k in TARGET_KEYS)
                and "m" in data["review"]
                and all(k in data["price"] for k in PRICE_KEYS))
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
