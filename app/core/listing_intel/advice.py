from .features import IMAGE_COLS

MAX_ITEMS = 6
MATERIAL = "missing_material"
FALLBACK_MESSAGE = "Mục này cần được cải thiện."
MATERIAL_MESSAGE = "Chưa nêu chất liệu sản phẩm. Thêm chất liệu vào ô Chất liệu hoặc tiêu đề."
MIN_RATING = 4.0
PINNED = {MATERIAL, "no_reviews", "low_rating"}

FIXES = {
    "title_short": ["title_len", "title_words"],
    "title_long": ["title_len", "title_words"],
    "keyword_stuffing": ["title_repeat_ratio"],
    "banned_word": ["title_banned"],
    "missing_material": ["attr_material"],
    "missing_color": ["attr_color"],
    "missing_size": ["attr_size"],
    "desc_short": ["desc_len", "desc_words"],
    "low_resolution": ["img_w", "img_h"],
    "blurry": ["img_sharpness"],
    "too_dark": ["img_brightness"],
    "too_bright": ["img_brightness"],
    "busy_background": ["img_border_uniform"],
    "text_overlay": ["img_text_ratio"],
    "bad_aspect": ["img_aspect"],
    "few_images": ["n_images"],
    "no_images": ["n_images", *IMAGE_COLS],
}

EFFORT = {
    **dict.fromkeys(["title_short", "title_long", "keyword_stuffing", "banned_word", MATERIAL,
                     "missing_color", "missing_size", "duplicate_tag", "pending_tag", "weak_tag"], 1),
    **dict.fromkeys(["desc_short", "few_tags", "no_tags", "no_trend_keyword", "price_high", "price_low",
                     "near_duplicate"], 2),
}


def _item(axis, issue, evidence, impacts) -> dict:
    code = issue["code"]
    return {
        "axis": axis,
        "code": code,
        "message": issue.get("message") or FALLBACK_MESSAGE,
        "evidence": "practice" if code == MATERIAL else evidence.get(axis, "practice"),
        "effort": EFFORT.get(code, 3),
        "impact": impacts.get(code),
    }


def _key(a) -> tuple:
    return a["evidence"] == "measured", a["impact"] or 0.0, -a["effort"]


def review_issue(inp) -> dict | None:
    if inp.rating_count is None:
        return None
    if inp.rating_count == 0:
        return {"code": "no_reviews", "message": "Sản phẩm chưa có đánh giá nào. Nhắc khách đã mua để lại đánh giá để người mua sau tin tưởng hơn."}
    if inp.average_rating is not None and inp.average_rating < MIN_RATING:
        rating = f"{inp.average_rating:.1f}".replace(".", ",")
        return {"code": "low_rating", "message": f"Điểm đánh giá trung bình {rating}/5, dưới 4. Đọc lại phản hồi của khách để sửa chất lượng hoặc mô tả cho đúng."}
    return None


def build(axes: dict, material: dict, evidence: dict, impacts: dict, review: dict | None = None) -> list[dict]:
    items, seen = [], set()
    for axis, res in axes.items():
        for issue in res.issues:
            if issue["code"] not in seen:
                seen.add(issue["code"])
                items.append(_item(axis, issue, evidence, impacts))
    if material.get("missing") and MATERIAL not in seen:
        items.append(_item("text", {"code": MATERIAL, "message": MATERIAL_MESSAGE}, evidence, impacts))
    if review:
        items.append(_item("market", review, {}, impacts))
    ranked = sorted(items, key=_key, reverse=True)
    best = max(ranked, key=lambda a: a["impact"] or 0.0, default=None)
    pinned = [a for a in ranked[MAX_ITEMS:] if a["code"] in PINNED or (a is best and a["impact"])]
    return ranked[:MAX_ITEMS - len(pinned)] + pinned
