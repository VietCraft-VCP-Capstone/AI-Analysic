import json
from functools import cache

import numpy as np

from app.core.f29.checks import make_check
from app.core.f29.paths import MODELS

VERSION = "image_match/v1"
ACTION = "Ảnh này không khớp tên sản phẩm. Thay bằng ảnh chụp đúng sản phẩm."
SCOPE_ACTION = "AI chưa học loại hàng này nên ảnh được tính như cũ."
OK_ACTION = "Ảnh khớp tên sản phẩm."


@cache
def _bundle() -> dict | None:
    path = MODELS / VERSION / "metrics.json"
    return json.loads(path.read_text("utf-8")) if path.exists() else None


def _unit(v) -> np.ndarray:
    v = np.asarray(v, dtype=float)
    return v / max(float(np.linalg.norm(v)), 1e-12)


def image_checks(vecs: list, title_vec, group: str | None) -> list[dict]:
    b = _bundle()
    if b is None or title_vec is None:
        return []
    if group not in b.get("groups", []):
        return [make_check("image_match:scope", "image", "na", {"group": group}, SCOPE_ACTION,
                           confidence=0.0, model_version=VERSION, mode=b["mode"])]
    t = _unit(title_vec)
    out = []
    for i, v in enumerate(vecs):
        if v is None:
            continue
        cos = float(_unit(v) @ t)
        sev, action = ("warn", ACTION) if cos < b["tau"] else ("pass", OK_ACTION)
        out.append(make_check(f"image_match:{i}", "image", sev, {"cos": round(cos, 4), "tau": b["tau"]},
                              action, model_version=VERSION, mode=b["mode"]))
    return out
