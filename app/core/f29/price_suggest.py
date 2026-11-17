import json
import math
from functools import cache
from pathlib import Path
from typing import Any

import joblib

from app.core.f29.material import material_price_factor

MODEL_PATH = Path(__file__).parent / "price_model.joblib"
MIN_PRICE = 1000.0


@cache
def _load(model_path: Path):
    try:
        meta = json.loads(model_path.with_suffix(".json").read_text("utf-8"))
        return joblib.load(model_path), float(meta["q25"]), float(meta["q75"])
    except Exception:
        return None


def round_price(x: float) -> float:
    return max(round(x, -3), MIN_PRICE)


def suggest(title: str, group: str | None, materials: Any = None) -> dict | None:
    loaded = _load(MODEL_PATH)
    if loaded is None:
        return None
    model, q25, q75 = loaded
    mat_factor = material_price_factor(materials) if materials else 1.0
    mat_tokens = ""
    if materials:
        if isinstance(materials, (list, set, frozenset)):
            mat_tokens = " ".join(str(m) for m in materials if m)
        elif isinstance(materials, str):
            mat_tokens = materials
    prompt_text = f"{group or ''} {mat_tokens} {title}".strip() if mat_tokens else f"{group or ''} {title}".strip()
    try:
        raw_pred = float(model.predict([prompt_text])[0])
        base_mid = math.exp(raw_pred)
        mid = base_mid * mat_factor
        low, high = mid * math.exp(q25), mid * math.exp(q75)
    except Exception:
        return None
    res = {
        "low": round_price(low),
        "mid": round_price(mid),
        "high": round_price(high),
    }
    if materials:
        res["material_factor"] = mat_factor
    return res
