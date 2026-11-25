import math

import numpy as np
from PIL import Image
from sklearn.cluster import KMeans

from app.core.f29.checks import make_check


MARGIN = 0.04
PERIODS = (8, 10, 12, 16, 20, 24, 32)
MAX_POINTS = 20000
SOLID_DIST = 24
INK_ALPHA = 50


def alpha_stats(img: Image.Image) -> dict:
    rgba = np.asarray(img.convert("RGBA"))
    alpha = rgba[..., 3]
    border = _border(*alpha.shape)
    edge, opaque = rgba[border, :3].astype(float), alpha[border] == 255
    border_rgb, solid = _solid_edge(edge, opaque)
    return {
        "has_alpha": "A" in img.getbands() or "transparency" in img.info,
        "transparent_frac": float((alpha == 0).mean()),
        "semi_frac": float(((alpha > 0) & (alpha < 255)).mean()),
        "border_white_frac": float(((edge > 235).all(axis=-1) & opaque).mean()),
        "border_solid_frac": float(solid.mean()),
        "border_rgb": border_rgb,
        "fake_checker": is_fake_checker(np.asarray(img.convert("L"))),
    }


def is_fake_checker(gray: np.ndarray) -> bool:
    g = np.asarray(gray, dtype=float)[:64, :64]
    lo, hi = np.percentile(g, [10, 90])
    if not (lo > 150 and hi > 150 and 10 <= hi - lo <= 80):
        return False
    m = g >= (lo + hi) / 2
    return any(_shift_differs(m, p) for p in PERIODS)


def contrast_ratio(rgb_a: tuple, rgb_b: tuple) -> float:
    la, lb = sorted((_luminance(rgb_a), _luminance(rgb_b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def dominant_ink(img: Image.Image, k: int = 3) -> list[tuple[tuple[int, int, int], float]]:
    rgba = np.asarray(img.convert("RGBA"))
    px = rgba[rgba[..., 3] > INK_ALPHA][:, :3].astype(float)
    if not len(px):
        return []
    if len(px) > MAX_POINTS:
        px = px[np.random.default_rng(0).choice(len(px), MAX_POINTS, replace=False)]
    k = min(k, len(np.unique(px, axis=0)))
    km = KMeans(n_clusters=k, n_init=3, random_state=0).fit(px)
    counts = np.bincount(km.labels_, minlength=k)
    order = np.argsort(-counts)
    return [(tuple(int(round(v)) for v in km.cluster_centers_[i]), float(counts[i] / len(px)))
            for i in order]


def _border(h: int, w: int) -> np.ndarray:
    my, mx = max(1, int(h * MARGIN)), max(1, int(w * MARGIN))
    y, x = np.arange(h)[:, None], np.arange(w)[None, :]
    return (y < my) | (y >= h - my) | (x < mx) | (x >= w - mx)


def _solid_edge(edge: np.ndarray, opaque: np.ndarray):
    if not opaque.any():
        return None, np.zeros(len(edge), dtype=bool)
    med = np.median(edge[opaque], axis=0)
    solid = opaque & (np.linalg.norm(edge - med, axis=-1) <= SOLID_DIST)
    return [int(round(v)) for v in med], solid


def _shift_differs(m: np.ndarray, p: int) -> bool:
    if min(m.shape) <= p:
        return False
    base = m[:-p, :-p]
    ok = (base != m[:-p, p:]) & (base != m[p:, :-p])
    return bool(ok.mean() >= 0.9)


def _linear(v: int) -> float:
    c = v / 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def _luminance(rgb: tuple) -> float:
    r, g, b = (_linear(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


VISIBLE_MIN = 1.5
SOLID_MIN = 0.6
LOW_SHARE_MAX = 0.5
NA_ACTION = "Chưa đủ dữ liệu để kiểm file in."


def alpha_check(cid: str, img, sold: dict) -> dict:
    if img is None:
        return make_check(cid, "print", "na", {}, NA_ACTION)
    st = alpha_stats(img)
    if st["fake_checker"]:
        return make_check(cid, "print", "warn", st,
                          "Ô caro giả thay cho nền trong suốt. Lưu PNG nền trong suốt thật.")
    if st["border_solid_frac"] > SOLID_MIN and _visible(st["border_rgb"], sold):
        return make_check(cid, "print", "warn", st,
                          f"Thiết kế có nền đặc ({_hex(st['border_rgb'])}) nên sẽ in thành khung chữ nhật. "
                          "Xoá nền, lưu PNG nền trong suốt.")
    return make_check(cid, "print", "pass", st, "Nền ảnh hợp lệ.")


def ink_profile(img) -> tuple[list, list | None]:
    st = alpha_stats(img)
    bg = st["border_rgb"] if st["border_solid_frac"] > SOLID_MIN else None
    return dominant_ink(img), bg


def color_checks(sold: dict, profiles: list) -> list[dict]:
    return [_contrast_check(name, hex_, profiles) for name, hex_ in sold.items()]


def _contrast_check(name: str, hex_: str | None, profiles: list) -> dict:
    cid = f"print_contrast:{name}"
    if not hex_ or not profiles:
        return make_check(cid, "print", "na", {}, NA_ACTION)
    rgb = _rgb(hex_)
    kept, printed = [], 0
    for clusters, bg in profiles:
        if bg is not None and contrast_ratio(tuple(bg), rgb) >= VISIBLE_MIN:
            printed += 1
        else:
            kept.append(_drop_background(clusters, bg) if bg is not None else clusters)
    kept = [c for c in kept if c]
    if not kept:
        if printed:
            return make_check(cid, "print", "pass", {"reason": "ink_on_printed_background"},
                              "Mực nằm trên nền đã in. Xem cảnh báo nền.")
        return make_check(cid, "print", "na", {}, NA_ACTION)
    low, ratio = max((_low_share(c, rgb) for c in kept), key=lambda t: t[0])
    evidence = {"low_share": round(low, 3), "ratio": round(ratio, 2)}
    if low >= LOW_SHARE_MAX:
        return make_check(cid, "print", "warn", evidence,
                          f"{low:.0%} mực in gần như chìm vào áo {name} (tương phản dưới 1,5). "
                          "Nên đổi màu in hoặc màu áo.")
    return make_check(cid, "print", "pass", evidence, f"Mực in đủ tương phản với áo {name}.")


def _drop_background(clusters: list, bg: list) -> list:
    keep = [(rgb, share) for rgb, share in clusters if math.dist(rgb, bg) > SOLID_DIST]
    total = sum(share for _, share in keep)
    return [(rgb, share / total) for rgb, share in keep] if total else []


def _low_share(clusters: list, rgb: tuple) -> tuple[float, float]:
    ratios = [(share, contrast_ratio(ink, rgb)) for ink, share in clusters]
    low = sum(share for share, r in ratios if r < VISIBLE_MIN)
    return low, max(ratios)[1]


def _rgb(hex_: str) -> tuple:
    return tuple(bytes.fromhex(hex_.lstrip("#")))


def _hex(rgb) -> str:
    return "#" + "".join(f"{v:02X}" for v in rgb)


def _visible(rgb, sold: dict) -> bool:
    return any(bool(h) and contrast_ratio(tuple(rgb), _rgb(h)) >= VISIBLE_MIN for h in sold.values())


CM_PER_INCH = 2.54
MIN_DPI = 150
OUT_LIMIT = 0.02


def effective_dpi(area_w_px: float, scale: float, phys_w_cm: float,
                  area_h_px: float | None = None, phys_h_cm: float | None = None) -> float:
    dpi = CM_PER_INCH * area_w_px / (scale * phys_w_cm)
    if area_h_px is not None and phys_h_cm is not None:
        dpi = min(dpi, CM_PER_INCH * area_h_px / (scale * phys_h_cm))
    return dpi


def dpi_severity(dpi: float) -> str:
    if dpi >= MIN_DPI:
        return "pass"
    return "warn" if dpi >= 120 else "block"


def check_product(product: dict, designs: dict[str, dict], blank: dict | None, load_image) -> list[dict]:
    if not _ready(product, blank):
        return [make_check("print", "print", "na", {}, NA_ACTION)]
    areas = {a.get("key"): a for a in blank["print_areas"]}
    sold = _sold_hexes(product, blank)
    cache: dict = {}
    checks = []
    for p in product["design_placements"]:
        area = areas.get(p.get("print_area_key"))
        for j, layer in enumerate(p.get("layers") or []):
            if not layer.get("design_id"):
                continue
            key, did = f"{p.get('print_area_key')}:{j}", str(layer["design_id"])
            design = designs.get(did) or {}
            img = _load(design, did, load_image, cache)
            checks += [_dpi_check(f"print_dpi:{key}", p, layer, design, area),
                       _area_check(f"print_area:{key}", p, layer, design, area),
                       alpha_check(f"print_alpha:{key}", img, sold)]
    loaded = [img for img in cache.values() if img is not None]
    return checks + color_checks(sold, [ink_profile(img) for img in loaded])


def _ready(product: dict, blank: dict | None) -> bool:
    areas = (blank or {}).get("print_areas") or []
    return bool(product.get("design_placements")) and bool(areas) and all(
        a.get("physical_width_cm") for a in areas)


def _load(design: dict, did: str, load_image, cache: dict):
    if did not in cache:
        url = design.get("file_url")
        cache[did] = load_image(url) if url else None
    return cache[did]


def _print_scale(placement: dict, layer: dict, design: dict) -> float:
    s = float(placement.get("scale", 1)) * float(layer.get("scale", 1))
    if layer.get("width"):
        s *= float(layer["width"]) / float(design["width_px"])
    return s


def _dpi_check(cid: str, placement: dict, layer: dict, design: dict, area: dict | None) -> dict:
    try:
        s = _print_scale(placement, layer, design)
        w_px, area_w = float(design["width_px"]), float(area["width"])
        phys = float(area["physical_width_cm"])
        dpi = effective_dpi(area_w, s, phys)
        in_cm = w_px * s / area_w * phys
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return make_check(cid, "print", "na", {}, NA_ACTION)
    sev = dpi_severity(dpi)
    return make_check(cid, "print", sev, {"dpi": round(dpi, 1), "in_cm": round(in_cm, 1)},
                      _dpi_action(sev, dpi, in_cm, w_px))


def _dpi_action(sev: str, dpi: float, in_cm: float, w_px: float) -> str:
    if sev == "pass":
        return f"Độ phân giải in đạt {dpi:.0f} DPI."
    px = math.ceil(MIN_DPI * in_cm / CM_PER_INCH)
    cm = f"{w_px / MIN_DPI * CM_PER_INCH:.1f}".replace(".", ",")
    return f"Tải file ≥ {px} px hoặc thu nhỏ hình xuống ≤ {cm} cm."


def _outside_frac(layer_box: tuple, area_box: tuple) -> float:
    x, y, w, h = layer_box
    ax, ay, aw, ah = area_box
    ow = max(0.0, min(x + w, ax + aw) - max(x, ax))
    oh = max(0.0, min(y + h, ay + ah) - max(y, ay))
    return 1 - ow * oh / (w * h)


def _area_check(cid: str, placement: dict, layer: dict, design: dict, area: dict | None) -> dict:
    try:
        s = _print_scale(placement, layer, design)
        box = (float(layer["x"]), float(layer["y"]),
               float(design["width_px"]) * s, float(design["height_px"]) * s)
        area_box = (float(area["x"]), float(area["y"]), float(area["width"]), float(area["height"]))
        frac = _outside_frac(box, area_box)
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return make_check(cid, "print", "na", {}, NA_ACTION)
    bad = frac > OUT_LIMIT
    action = (f"{frac:.0%} hình nằm ngoài vùng in. Kéo hình vào trong vùng in." if bad
              else "Hình nằm trong vùng in.")
    return make_check(cid, "print", "warn" if bad else "pass", {"outside_frac": round(frac, 3)}, action)


def _sold_hexes(product: dict, blank: dict) -> dict[str, str | None]:
    hexes = {v.get("color"): v.get("color_hex") for v in blank.get("variations") or []}
    return {name: hexes.get(name) for name in product.get("active_colors") or list(hexes)}
