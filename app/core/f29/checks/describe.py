import json
from functools import lru_cache
from itertools import combinations

import joblib
import numpy as np

from app.core.f29.score import text_rules
from app.core.f29.checks import category as cat, make_check
from app.core.f29.paths import MODELS
from app.core.f29.checks.category import category_checks, category_name
from app.core.f29.score.text_rules import find_materials, material_line, sentences


B2_DIR = MODELS / "b2_material" / "v1"
NO_MATERIAL_GROUPS = {"dien_tu"}
SOURCES = ("title", "description", "materials")
CONFLICT_ID = "description_material:conflict"
MISSING_ID = "description_material:missing"
CONFLICT_ACTION = "Tên, mô tả và ô Chất liệu đang nêu chất liệu khác nhau. Chỉ giữ một chất liệu đúng."
MISSING_ACTION = "Ghi rõ chất liệu trong mô tả hoặc ô Chất liệu."
OK_ACTION = "Chất liệu khớp nhau."


@lru_cache(maxsize=1)
def _model():
    path = B2_DIR / "model.joblib"
    return joblib.load(path) if path.exists() else None


@lru_cache(maxsize=1)
def _gate() -> float:
    try:
        return json.loads((B2_DIR / "metrics.json").read_text("utf-8")).get("suggest_gate", {}).get("min_p", 1.01)
    except (OSError, ValueError, AttributeError):
        return 1.01


def material_top3(title: str, description: str) -> list[tuple[str, float]]:
    art = _model()
    text = f"{title or ''} {material_line(description or '')[1]}".strip()
    if art is None or not text:
        return []
    p = art.predict_proba([text])[0]
    return [(str(art.classes_[i]), float(p[i])) for i in np.argsort(-p)[:3]]


def _applies(category) -> bool:
    return cat.PARENT.get(cat.vc_type(category)) not in NO_MATERIAL_GROUPS


def _sources(product: dict) -> dict[str, str]:
    mats = product.get("materials")
    mats = [mats] if isinstance(mats, str) else mats if isinstance(mats, list) else []
    texts = {"title": product.get("title"), "description": product.get("description"),
             "materials": ", ".join(m for m in mats if isinstance(m, str))}
    return {k: v for k, v in texts.items() if isinstance(v, str) and v.strip()}


def _sentence(text: str, classes: set[str]) -> str:
    return next((s for s in sentences(text) if set(find_materials(s)) & classes), text)


def _conflict(product: dict) -> dict | None:
    src = _sources(product)
    found = {k: set(find_materials(src[k])) for k in SOURCES if k in src}
    for a, b in combinations([k for k in SOURCES if found.get(k)], 2):
        if not found[a] & found[b]:
            return {"sources": [a, b], "classes": [sorted(found[a]), sorted(found[b])],
                    "sentence": _sentence(src[b], found[b])}
    return None


def _missing_check(product: dict) -> dict:
    if text_rules.has_material(product):
        return make_check(MISSING_ID, "description", "pass", {}, OK_ACTION)
    top3 = material_top3(product.get("title"), product.get("description"))
    gate = _gate()
    confident = bool(top3) and top3[0][0] != "khac" and top3[0][1] >= gate
    suggest = [[k, round(p, 4)] for k, p in top3 if k != "khac" and p >= gate] if confident else []
    return make_check(MISSING_ID, "description", "info", {"suggest": suggest}, MISSING_ACTION,
                      confidence=top3[0][1] if suggest else 0.0,
                      model_version="b2_material/v1" if suggest else "rule")


def material_checks(product: dict) -> list[dict]:
    if not _applies(category_name(product)):
        return []
    conflict = _conflict(product)
    checks = [make_check(CONFLICT_ID, "description", "warn" if conflict else "pass",
                         conflict or {}, CONFLICT_ACTION if conflict else OK_ACTION)]
    return [*checks, _missing_check(product)]


def check_listing(product: dict, img_vec, txt_vec) -> list[dict]:
    return [*material_checks(product), *category_checks(product, img_vec, txt_vec)]
