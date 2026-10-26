import math

from .features import STYLES, image_semantics, market_vec
from .market_axis import knn_features
from .text_axis import text_issues
from .types import AxisResult, ListingInput
from .vision import hamming, quality_issues

MIN_IMAGES = 3
DUP_HAMMING = 5
NEIGHBORS = 20
NO_IMAGE = "Listing chưa có ảnh nên chưa chấm được trục ảnh."
FAILED = "Không tải được ảnh nào của listing nên chưa chấm được trục ảnh."
NO_MARKET_IMAGE = "Cần ít nhất một ảnh tải được để so với sản phẩm tương tự trên thị trường."
NO_MARKET_GROUP = "Danh mục này chưa có dữ liệu tham chiếu (hoặc chưa chọn danh mục) nên chưa so được với thị trường."


def issue(code: str, message: str) -> dict:
    return {"code": code, "message": message}


def strip(issues) -> list[dict]:
    return [issue(i["code"], i.get("message")) for i in issues]


def _style(sem: dict):
    probs = {s: sem.get(f"style_{s}") for s in STYLES}
    probs = {k: v for k, v in probs.items() if v is not None and not math.isnan(v)}
    return max(probs, key=probs.get) if probs else None


def image_list(urls, loaded, title_vec, group, prompt_vecs) -> list[dict]:
    out, hashes = [], []
    for url, item in zip(urls, loaded):
        if item is None:
            out.append({"url": url, "metrics": {}, "issues": [issue("fetch_failed", "Không tải được ảnh này.")],
                        "style": None, "sim_title": None})
            continue
        issues = strip(quality_issues(item["display"]))
        h = int(item["dhash"], 16)
        if any(hamming(h, o) <= DUP_HAMMING for o in hashes):
            issues.append(issue("duplicate_image", "Ảnh gần như trùng với một ảnh khác của listing."))
        hashes.append(h)
        sem = {} if item["vec"] is None else image_semantics(item["vec"], title_vec, group, prompt_vecs)
        out.append({"url": url, "metrics": dict(item["display"]), "issues": issues,
                    "style": _style(sem), "sim_title": sem.get("sim_title")})
    return out


def image_axis(score, inp: ListingInput, images: list[dict]) -> AxisResult:
    ok = [i for i in images if i["metrics"]]
    issues = [] if inp.image_urls else [issue("no_images", "Thêm ít nhất 3 ảnh sản phẩm rõ nét.")]
    if 0 < len(inp.image_urls) < MIN_IMAGES:
        issues.append(issue("few_images", "Nên có ít nhất 3 ảnh: toàn cảnh, cận chất liệu và ảnh dùng thực tế."))
    if ok:
        issues += ok[0]["issues"]
        if any(c["code"] == "duplicate_image" for i in ok[1:] for c in i["issues"]):
            issues.append(issue("duplicate_image", "Có ảnh gần như trùng nhau, nên thay bằng góc chụp khác."))
    reason = None if ok else (FAILED if inp.image_urls else NO_IMAGE)
    metrics = {"n_images": len(inp.image_urls), "n_loaded": len(ok),
               "sim_title": ok[0]["sim_title"] if ok else None}
    return AxisResult(score=score if ok else None, features=metrics, issues=issues, missing_reason=reason)


def text_axis(score, inp: ListingInput, feats: dict, cols) -> AxisResult:
    return AxisResult(score=score, features={c: feats[c] for c in cols}, issues=strip(text_issues(inp, feats)))


def market(inp: ListingInput, img_vec, title_vec, ctx):
    index = ctx.knn.get(inp.group)
    if img_vec is None or title_vec is None or index is None:
        return None
    k = knn_features(market_vec(img_vec, title_vec), inp.price, index)
    return {"price_pct": k["knn_price_pct"], "neighbors": min(NEIGHBORS, len(index.vecs)),
            "near_duplicates": int(k["knn_dup_count"]), "median_price": k["knn_median_price"]}


def market_axis(score, m, feats: dict, has_image: bool = True) -> AxisResult:
    metrics = {"top_centroid_margin": feats.get("top_centroid_margin")}
    if m is None:
        reason = None if score is not None else NO_MARKET_GROUP if has_image else NO_MARKET_IMAGE
        return AxisResult(score=score, features=metrics, missing_reason=reason)
    issues, pct = [], m["price_pct"]
    if m["near_duplicates"]:
        issues.append(issue("near_duplicate", f"Có {m['near_duplicates']} sản phẩm gần như giống hệt trong nhóm."))
    if pct >= 90:
        issues.append(issue("price_high", "Giá cao hơn hầu hết sản phẩm tương tự, cần nêu rõ điểm khác biệt."))
    if pct <= 10:
        issues.append(issue("price_low", "Giá thấp hơn hầu hết sản phẩm tương tự, kiểm tra lại biên lợi nhuận."))
    return AxisResult(score=score, features={**metrics, **m}, issues=issues)
