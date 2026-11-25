import json
from functools import lru_cache

import joblib
import numpy as np

from app.core.f29.checks import make_check
from app.core.f29.paths import DATA, MODELS


B1_DIR = MODELS / "b1_type" / "v1"
TREE: dict = json.loads((DATA / "category_tree.json").read_text("utf-8"))
TYPES: list[str] = list(TREE["types"])
PARENT: dict[str, str] = {t: v["parent"] for t, v in TREE["types"].items()}
GROUPS: set[str] = set(PARENT.values())
TRAINED: frozenset[str] = frozenset(t for t in TREE["tikifashion"].values() if t)
VC: dict[str, str | None] = {k.lower(): v for k, v in TREE["vc_category"].items()}


def vc_type(category_name: str | None) -> str | None:
    return VC.get((category_name or "").strip().lower())


def _softmax(z: np.ndarray) -> np.ndarray:
    e = np.exp(z - z.max(axis=1, keepdims=True))
    return e / e.sum(axis=1, keepdims=True)


def probe_part(art: dict, img: np.ndarray | None, txt: np.ndarray | None) -> np.ndarray:
    n = (img if img is not None else txt).shape[0]
    logp = np.zeros((n, len(art["classes"])))
    if img is not None:
        logp += art["img"].predict_log_proba(img)
    if txt is not None:
        logp += art["w"] * art["txt"].predict_log_proba(txt)
    out = np.zeros((n, len(TYPES)))
    out[:, [TYPES.index(c) for c in art["classes"]]] = _softmax(logp)
    return out


def zs_part(art: dict, img: np.ndarray | None, txt: np.ndarray | None) -> np.ndarray:
    sims = [x @ art["prompts"].T for x in (img, txt) if x is not None]
    return _softmax(art["temp"] * np.mean(sims, axis=0))


def probs(art: dict, img: np.ndarray | None, txt: np.ndarray | None) -> np.ndarray:
    out = probe_part(art, img, txt)
    if art["prompts"] is None:
        return out
    return (1 - art["zs_mix"]) * out + art["zs_mix"] * zs_part(art, img, txt)


@lru_cache(maxsize=1)
def _model() -> dict | None:
    try:
        art = joblib.load(B1_DIR / "model.joblib")
        art["prompts"] = np.load(B1_DIR / "prompts.npy") if art["zs_mix"] > 0 else None
    except FileNotFoundError:
        return None
    return art


def _rows(v: np.ndarray | None) -> np.ndarray | None:
    return None if v is None else np.asarray(v, dtype=np.float32).reshape(1, -1)


def type_probs(img_vec, txt_vec) -> dict[str, float]:
    art = _model()
    if art is None:
        return {}
    if img_vec is None and txt_vec is None:
        return {t: 1 / len(TYPES) for t in TYPES}
    row = probs(art, _rows(img_vec), _rows(txt_vec))[0]
    return dict(zip(TYPES, row.tolist()))


def predict(img_vec, txt_vec) -> dict:
    p = type_probs(img_vec, txt_vec)
    if not p:
        return {"type": None, "parent": None, "p": 0.0, "top3": [], "rejected": True}
    top3 = sorted(p.items(), key=lambda kv: -kv[1])[:3]
    best, pmax = top3[0]
    rejected = pmax < _model()["tau"]
    return {"type": None if rejected else best, "parent": None if rejected else PARENT[best],
            "p": pmax, "top3": top3, "rejected": rejected}


IDX = {t: i for i, t in enumerate(TYPES)}
VC_NAME: dict[str, str] = {}
for _name, _t in TREE["vc_category"].items():
    VC_NAME.setdefault(_t, _name)
CAT_ID = "description_category:top3"
NA_ACTION = "Chưa đánh giá được ảnh hoặc chữ để so khớp với danh mục."
PASS_ACTION = "Ảnh, chữ và danh mục khớp nhau."


def _f32(v) -> np.ndarray:
    return np.asarray(v, dtype=np.float32)


def _b1_ready() -> bool:
    return (B1_DIR / "model.joblib").exists() and _model() is not None


def category_name(product: dict) -> str | None:
    name = product.get("category")
    if isinstance(name, str) and name.strip():
        return name
    names = product.get("categories")
    if isinstance(names, list):
        return next((n for n in names if isinstance(n, str) and n.strip()), None)
    return None


def _declared(category) -> str | None:
    t = vc_type(category)
    return t if t in IDX else None


def _allowed(t: str, img, txt) -> bool:
    in_scope = t in TRAINED
    rejected = predict(img, None)["rejected"] or predict(None, txt)["rejected"]
    return in_scope and not rejected


def _suggest(t: str) -> str:
    return f"Gợi ý: {VC_NAME[t]}." if t in VC_NAME else "Kiểm tra lại danh mục."


def category_checks(product: dict, img, txt) -> list[dict]:
    t = _declared(category_name(product))
    if t is None or not _b1_ready():
        return []
    if img is None or txt is None:
        return [make_check(CAT_ID, "description", "na", {}, NA_ACTION)]
    img, txt = _f32(img).reshape(1, -1), _f32(txt).reshape(1, -1)
    top3 = predict(img, txt)["top3"]
    names = [k for k, _ in top3]
    if not names:
        return [make_check(CAT_ID, "description", "na", {}, NA_ACTION)]
    evidence = {"declared": t, "top3": [[k, round(p, 4)] for k, p in top3]}
    if t in names:
        return [make_check(CAT_ID, "description", "pass", evidence, PASS_ACTION)]
    sev = "warn" if _allowed(t, img, txt) else "info"
    return [make_check(CAT_ID, "description", sev, evidence, f"Danh mục chưa khớp ảnh và mô tả. {_suggest(names[0])}")]
