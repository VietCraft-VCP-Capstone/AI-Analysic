import json
from functools import cache

import numpy as np

from app.core.f29.checks import make_check
from app.core.f29.paths import MODELS

VERSION = "image_match/v1"
ACTION = "Ảnh này không khớp tên sản phẩm. Thay bằng ảnh chụp đúng sản phẩm."


@cache
def _bundle() -> dict | None:
    path = MODELS / VERSION / "metrics.json"
    return json.loads(path.read_text("utf-8")) if path.exists() else None


def _unit(v) -> np.ndarray:
    v = np.asarray(v, dtype=float)
    return v / max(float(np.linalg.norm(v)), 1e-12)


def image_checks(vecs: list, title_vec) -> list[dict]:
    b = _bundle()
    if b is None or title_vec is None:
        return []
    t = _unit(title_vec)
    out = []
    for i, v in enumerate(vecs):
        cos = None if v is None else float(_unit(v) @ t)
        if cos is not None and cos < b["tau"]:
            out.append(make_check(f"image_match:{i}", "image", "warn", {"cos": round(cos, 4), "tau": b["tau"]},
                                  ACTION, model_version=VERSION, mode=b["mode"]))
    return out
