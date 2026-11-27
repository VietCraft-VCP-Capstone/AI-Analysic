import json
from functools import cache

from app.core.f29.checks.category import TRAINED, VC_NAME
from app.core.f29.paths import MODELS as MODELS_DIR
from app.core.f29.score.text_rules import MATERIALS
from app.core.f29.shared.normalize import fold

SOURCES = {
    "b1_type/v1": ("Nhận diện loại hàng từ ảnh và tên", "tin Tiki Fashion"),
    "b2_material/v1": ("Đoán chất liệu từ mô tả", "tin Tiki"),
    "b3_attr/v1": ("Kiểm ảnh có khớp mô tả", "ảnh Tiki"),
    "i_dupes/v1": ("Phát hiện ảnh trùng", "bản sao ảnh VietCraft"),
    "image_match/v1": ("Kiểm ảnh có khớp tên sản phẩm", "tin Tiki có ảnh và tên"),
}
NO_IMAGE = "Chưa phân tích được ảnh"
NOT_LEARNED = "AI chưa học loại hàng này"


def _num(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _pct(x: float, digits: int = 0) -> str:
    return f"{x * 100:.{digits}f}".replace(".", ",")


def _facts(name: str, m: dict) -> tuple[int, str]:
    if name == "b1_type/v1":
        r = m["reject"]["test"]
        return sum(m["rows"].values()), (f"Đúng {_pct(r['acc_answered'])}% trên tập kiểm tra, "
                                         f"tự từ chối {_pct(r['rate'])}% khi không chắc")
    if name == "b2_material/v1":
        t = m["test"]["A"]
        return sum(m["rows"].values()), (f"Điểm F1 {_pct(t['model']['macro_f1'])}% so với "
                                         f"{_pct(t['baseline_current']['macro_f1'])}% của cách bắt từ khoá")
    if name == "b3_attr/v1":
        return m["rows"]["total"], "Chỉ gợi ý, chưa qua ngưỡng tự đặt nên không trừ điểm"
    if name == "image_match/v1":
        t = m["test"]["other_group"]
        note = "" if m["mode"] == "live" else "; chưa qua ngưỡng tự đặt nên chỉ gợi ý"
        return m["rows"]["total"], (f"Bắt được {_pct(t['catch'])}% ảnh sai loại hàng, "
                                    f"báo nhầm {_pct(t['false_alarm'], 1)}%{note}")
    return m["n_B_copies"], f"Báo nhầm {_pct(m['fpr_warn_B'], 2)}%"


@cache
def models() -> dict:
    out = {}
    for name, (title, source) in SOURCES.items():
        path = MODELS_DIR / name / "metrics.json"
        if path.exists():
            n, metric = _facts(name, json.loads(path.read_text("utf-8")))
            out[name] = {"title": title, "trained_on": f"{_num(n)} {source}", "metric": metric}
    return out


def type_name(code: str) -> str:
    return VC_NAME.get(code, code.replace("_", " "))


def material_name(cls: str) -> str:
    plain = cls.replace("_", " ")
    return next((t for t in MATERIALS.get(cls, []) if fold(t) == plain), plain)


def _check(checks: list, cid: str):
    return next((c for c in checks if c.get("id") == cid), None)


def _b1(checks: list, no_image: bool):
    c = _check(checks, "description_category:top3")
    if c is None:
        return NOT_LEARNED, "na", None
    ev = c.get("evidence") or {}
    if c["severity"] == "na" or no_image:
        return NO_IMAGE, "na", None
    if ev.get("declared") not in TRAINED:
        return NOT_LEARNED, "info", None
    code, p = ev["top3"][0]
    if c["severity"] == "pass" and code == ev["declared"]:
        return f"Ảnh và tên khớp danh mục {type_name(code)} (AI chắc {_pct(p)}%)", "pass", p
    if c["severity"] == "pass":
        return (f"AI thấy giống {type_name(code)} nhất ({_pct(p)}%); {type_name(ev['declared'])} "
                f"nằm trong 3 khả năng AI đưa ra"), "info", p
    return f"AI thấy giống {type_name(code)} hơn danh mục đang chọn", c["severity"], p


def _b2(checks: list, no_image: bool):
    c = _check(checks, "description_material:missing")
    if c is None:
        return None
    if c["severity"] == "pass":
        return "Đã ghi chất liệu", "pass", None
    suggest = (c.get("evidence") or {}).get("suggest") or []
    if not suggest:
        return "Chưa ghi chất liệu", "info", None
    found = ", ".join(f"{material_name(k)} {_pct(p)}%" for k, p in suggest[:2])
    return f"AI đoán chất liệu: {found}", "info", suggest[0][1]


def _b3(checks: list, no_image: bool):
    found = [c for c in checks if str(c.get("id", "")).startswith("description_attribute:")]
    if not found:
        return (NO_IMAGE, "na", None) if no_image else None
    warn = next((c for c in found if c["severity"] == "warn"), None)
    if warn:
        return warn["action"], "warn", (warn.get("evidence") or {}).get("p_seen")
    return "Thuộc tính trong mô tả khớp ảnh", "pass", None


def _dupes(checks: list, no_image: bool):
    if no_image:
        return NO_IMAGE, "na", None
    idx = sorted(int(c["id"].split(":")[1]) + 1 for c in checks
                 if str(c.get("id", "")).startswith("duplicate_same_shop:") and c["severity"] == "warn")
    if idx:
        return f"Ảnh {', '.join(map(str, idx))} trùng sản phẩm khác của shop", "warn", None
    return "Không có ảnh trùng", "pass", None


def _match(checks: list, no_image: bool):
    if no_image:
        return NO_IMAGE, "na", None
    idx = sorted(int(c["id"].split(":")[1]) + 1 for c in checks
                 if str(c.get("id", "")).startswith("image_match:") and c["severity"] == "warn")
    if idx:
        return f"Ảnh {', '.join(map(str, idx))} không khớp tên sản phẩm", "warn", None
    return "Mọi ảnh đều khớp tên sản phẩm", "pass", None


READERS = (("b1_type/v1", _b1), ("b2_material/v1", _b2), ("b3_attr/v1", _b3), ("i_dupes/v1", _dupes),
           ("image_match/v1", _match))


def build(checks: list, factors: list) -> list[dict]:
    image = next((f for f in factors if f.get("key") == "image"), {})
    no_image = not (image.get("evidence") or {}).get("siglip")
    out = []
    for name, read in READERS:
        found = read(checks, no_image) if name in models() else None
        if found:
            finding, status, confidence = found
            out.append({"model": name, **models()[name], "finding": finding, "status": status,
                        "confidence": confidence})
    return out
