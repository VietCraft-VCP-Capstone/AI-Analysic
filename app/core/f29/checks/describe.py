import json
from functools import lru_cache
from itertools import combinations

import joblib
import numpy as np

from app.core.f29.score import text_rules
from app.core.f29.checks import category as cat, make_check
from app.core.f29.paths import MODELS
from app.core.f29.checks.attributes import method_probs
from app.core.f29.checks.attributes import claims, conflicts, vocab
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
    return make_check(MISSING_ID, "description", "info", {"suggest": [[k, round(p, 4)] for k, p in top3]},
                      MISSING_ACTION, confidence=top3[0][1] if top3 else 0.0,
                      model_version="b2_material/v1" if top3 else "rule")


def material_checks(product: dict) -> list[dict]:
    if not _applies(category_name(product)):
        return []
    conflict = _conflict(product)
    checks = [make_check(CONFLICT_ID, "description", "warn" if conflict else "pass",
                         conflict or {}, CONFLICT_ACTION if conflict else OK_ACTION)]
    return [*checks, _missing_check(product)]


ATTR_DIR = MODELS / "b3_attr" / "v1"
MODEL_VERSION = "b3_attr/v1"
DESC_CHARS = 300
ACTION = "Mô tả ghi '{claimed}' nhưng ảnh giống '{seen}' (AI chắc {p}%). Sửa mô tả hoặc thay ảnh."
PASS_ACTION = "Thuộc tính trong mô tả khớp ảnh."


@lru_cache(maxsize=1)
def _bundle() -> dict | None:
    thr = ATTR_DIR / "thresholds.json"
    files = ("model.joblib", "prompts.npy")
    if not (thr.exists() and all((ATTR_DIR / f).exists() for f in files)):
        return None
    return {"groups": joblib.load(ATTR_DIR / "model.joblib"),
            "V": np.load(ATTR_DIR / "prompts.npy", allow_pickle=True).item(),
            **json.loads(thr.read_text("utf-8"))}


def version() -> str:
    b = _bundle()
    return f"{MODEL_VERSION}@{b['mode'] if b else 'missing'}"


def _vtype(product: dict) -> str | None:
    return cat.vc_type(category_name(product))


def _check(group: str, claimed: str, entry: dict, img, bundle: dict):
    classes = entry["classes"]
    rivals = [c for c in conflicts(group, claimed) if c in classes]
    if not rivals:
        return None
    P = method_probs(bundle["method"], entry, bundle["V"].get(group), img)[0]
    seen = max(rivals, key=lambda c: P[classes.index(c)])
    p_seen, p_claimed = float(P[classes.index(seen)]), float(P[classes.index(claimed)])
    sev = "warn" if p_seen - p_claimed > bundle["t_warn"] else "pass"
    names = vocab()[group]["names"]
    action = ACTION.format(claimed=names[claimed], seen=names[seen], p=round(p_seen * 100))
    evidence = {"claimed": claimed, "seen": seen, "p_seen": round(p_seen, 4), "p_claimed": round(p_claimed, 4)}
    return make_check(f"description_attribute:{group}", "description", sev, evidence,
                      action if sev == "warn" else PASS_ACTION, confidence=p_seen,
                      model_version=MODEL_VERSION, mode=bundle["mode"])


def attribute_checks(product: dict, img_vec) -> list[dict]:
    bundle = _bundle()
    if bundle is None or img_vec is None:
        return []
    text = f"{product.get('title') or ''} {(product.get('description') or '')[:DESC_CHARS]}"
    img = np.asarray(img_vec, dtype=np.float32).reshape(1, -1)
    out = []
    for group, claimed in claims(text, _vtype(product)).items():
        entry = bundle["groups"].get(group)
        if entry is None or claimed not in entry["classes"]:
            continue
        check = _check(group, claimed, entry, img, bundle)
        if check is not None:
            out.append(check)
    return out


def check_listing(product: dict, img_vec, txt_vec, img_vecs=None) -> list[dict]:
    attr_vec = img_vecs[0] if img_vecs and img_vecs[0] is not None else img_vec
    return [*material_checks(product),
            *category_checks(product, img_vec, txt_vec), *attribute_checks(product, attr_vec)]
