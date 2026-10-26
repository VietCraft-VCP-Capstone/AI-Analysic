import json
import math
from functools import cache
from pathlib import Path

import joblib

MODEL_PATH = Path(__file__).parent / "price_model.joblib"
MIN_PRICE = 1000.0


@cache
def _load(model_path: Path):
    try:
        meta = json.loads(model_path.with_suffix(".json").read_text("utf-8"))
        return joblib.load(model_path), float(meta["q25"]), float(meta["q75"])
    except Exception:
        return None


def _price(x: float) -> float:
    return max(round(x, -3), MIN_PRICE)


def suggest(title: str, group: str | None) -> dict | None:
    loaded = _load(MODEL_PATH)
    if loaded is None:
        return None
    model, q25, q75 = loaded
    try:
        mid = math.exp(float(model.predict([f"{group or ''} {title}".strip()])[0]))
        low, high = mid * math.exp(q25), mid * math.exp(q75)
    except Exception:
        return None
    return {"low": _price(low), "mid": _price(mid), "high": _price(high)}
