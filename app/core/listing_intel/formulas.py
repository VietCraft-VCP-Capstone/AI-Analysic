import math

from .lexicon import attributes
from .text_axis import MATERIAL_GROUPS, VARIANT_GROUPS
from .vision import BRIGHTNESS_RANGE, MAX_TEXT_RATIO, MIN_BORDER_UNIFORM, MIN_BRIGHT_CONTRAST

NAN = float("nan")
TITLE_BAND = (20.0, 120.0)
MAX_REPEAT = 0.3
MISSING_PENALTY = 0.15
REQUIRED = (("material", MATERIAL_GROUPS), ("color", VARIANT_GROUPS), ("size", VARIANT_GROUPS))
ATTRS = ("material", "color", "size", "occasion", "use")
IMAGE_WEIGHTS = {"sharpness_rel": 0.3, "exposure_ok": 0.05, "contrast_ok": 0.05, "border": 0.3, "no_text": 0.15,
                 "resolution": 0.05, "sim_title": 0.05, "sim_category": 0.05}
CONTRAST_FLOOR = 0.1
TEXT_WEIGHTS = {"attributes": 0.35, "title_length": 0.2, "keyword_lift": 0.25, "clean": 0.2}
MARKET_WEIGHTS = {"price_centre": 0.6, "uniqueness": 0.4}
RANGES = {"img_sharpness": (3.0, 5.5), "sharpness_rel": (-5.2, -2.4), "sim_title": (0.05, 0.2), "sim_category": (0.03, 0.14),
          "img_text_ratio": (MAX_TEXT_RATIO, 2 * MAX_TEXT_RATIO), "short_side": (128.0, 256.0), "kw_lift_scale": 2.0}


def _num(feats, key):
    v = feats.get(key)
    return NAN if v is None or math.isnan(float(v)) else float(v)


def _ramp(x, lo, hi):
    return NAN if math.isnan(x) else min(1.0, max(0.0, (x - lo) / (hi - lo)))


def _flag(x, ok):
    return NAN if math.isnan(x) else float(ok(x))


def mix(parts: dict, weights: dict) -> float:
    ok = {k: v for k, v in parts.items() if k in weights and not math.isnan(v)}
    total = sum(weights[k] for k in ok)
    return NAN if not ok else sum(weights[k] * v for k, v in ok.items()) / total


def exposure_ok(b, border, contrast) -> float:
    lo, hi = BRIGHTNESS_RANGE
    washed = b > hi and (border < MIN_BORDER_UNIFORM or contrast < MIN_BRIGHT_CONTRAST)
    return NAN if math.isnan(b) else float(b >= lo and not washed)


def image_parts(feats: dict) -> dict:
    w, h = _num(feats, "img_w"), _num(feats, "img_h")
    side = NAN if math.isnan(w) or math.isnan(h) else min(w, h)
    sharp, contrast = _num(feats, "img_sharpness"), _num(feats, "img_contrast")
    rel = sharp - 2 * math.log(255 * contrast) if contrast > 0 else NAN
    return {
        "sharpness": _ramp(sharp, *RANGES["img_sharpness"]),
        "sharpness_rel": _ramp(rel, *RANGES["sharpness_rel"]),
        "exposure_ok": exposure_ok(_num(feats, "img_brightness"), _num(feats, "img_border_uniform"), contrast),
        "contrast_ok": _flag(_num(feats, "img_contrast"), lambda c: c >= CONTRAST_FLOOR),
        "border": _num(feats, "img_border_uniform"),
        "no_text": 1 - _ramp(_num(feats, "img_text_ratio"), *RANGES["img_text_ratio"]),
        "resolution": _ramp(side, *RANGES["short_side"]),
        "sim_title": _ramp(_num(feats, "sim_title"), *RANGES["sim_title"]),
        "sim_category": _ramp(_num(feats, "sim_category"), *RANGES["sim_category"]),
    }


def image(feats: dict, weights=IMAGE_WEIGHTS) -> float:
    return mix(image_parts(feats), weights)


def _title_length(n):
    lo, hi = TITLE_BAND
    return NAN if math.isnan(n) else min(1.0, n / lo) if n < lo else max(0.0, 1 - (n - hi) / hi) if n > hi else 1.0


def title_keys(title, materials, group) -> dict:
    found = attributes(" ".join([title or "", *(materials or [])]))
    out = {f"title_attr_{a}": float(len(found[a])) for a in ATTRS}
    missing = [a for a, groups in REQUIRED if group in groups and not found[a] and not (a == "material" and materials)]
    return out | {"title_missing": float(len(missing))}


def text(feats: dict) -> float:
    attrs = [_num(feats, f"title_attr_{a}") for a in ATTRS]
    lift, miss = _num(feats, "kw_lift_sum"), _num(feats, "title_missing")
    clean = 1 - 0.5 * (_num(feats, "title_repeat_ratio") > MAX_REPEAT) - 0.5 * (_num(feats, "title_banned") > 0)
    score = mix({
        "attributes": sum(min(a, 1.0) for a in attrs) / len(attrs) if not any(map(math.isnan, attrs)) else NAN,
        "title_length": _title_length(_num(feats, "title_len")),
        "keyword_lift": NAN if math.isnan(lift) else 1 / (1 + math.exp(-lift / RANGES["kw_lift_scale"])),
        "clean": float(clean),
    }, TEXT_WEIGHTS)
    return score if math.isnan(score) or math.isnan(miss) else max(0.0, score - MISSING_PENALTY * miss)


def market(feats: dict) -> float:
    pct, dup = _num(feats, "knn_price_pct"), _num(feats, "knn_dup_count")
    return mix({"price_centre": NAN if math.isnan(pct) else 1 - abs(pct - 50) / 50,
                 "uniqueness": NAN if math.isnan(dup) else 1 / (1 + dup)}, MARKET_WEIGHTS)


FORMULAS = {"image": image, "text": text, "market": market}
SPEC = {"image": IMAGE_WEIGHTS, "text": TEXT_WEIGHTS, "market": MARKET_WEIGHTS, "ranges": RANGES,
        "title_band": TITLE_BAND, "max_repeat": MAX_REPEAT, "brightness_range": BRIGHTNESS_RANGE,
        "contrast_floor": CONTRAST_FLOOR,
        "missing_penalty": MISSING_PENALTY, "required": {a: sorted(g) for a, g in REQUIRED}}
