from app.core.f29.score import factors as f3
from app.core.f29.score import price as qr
from app.core.f29.score import scoring
from app.core.f29.score.recommend import BLOCKER_TITLES, METHOD_RANK, build, sort_recs
from app.core.f29.score.recommend import todos_of, warnings_of
from tests.f29.fake_mongo import make_calculator
from tests.f29.samples import PRODUCT_ID, base_product, with_id

PRICED = [{"is_active": True, "stock_quantity": 10, "retail_price": "150000", "base_cost": "80000"}]
PEERS = {"level": "category", "image": [1, 2, 3, 4, 5, 6], "description": [10, 20, 30, 40, 50, 60],
         "tags": [0, 1, 1, 2, 3, 4], "review": [40, 50, 60, 70, 80, 90]}


def _run(monkeypatch, queries=(), **overrides):
    monkeypatch.setattr(qr, "category_queries", lambda db, cat, since: list(queries))
    product = with_id(base_product(**overrides))
    variants = [{**v, "product_id": product["_id"]} for v in PRICED]
    return make_calculator(products=[product], product_variants=variants).calculate(PRODUCT_ID)


def _factors(queries=(), approved=1, pending=0, image=None, median=0, price=None, desc=None, review=None):
    return scoring.rescore_all([
        f3.image_row(image or {"state": "seller_missing", "useful": 0, "method": "heuristic"}, median),
        desc or f3.description_row({"title": "Áo", "description": "Áo thun cotton mềm giặt máy"}, 0),
        f3.tags_row(approved, pending, list(queries), "rule"),
        review or f3.review_row(0, 0, 1.0, 5.0),
        f3.price_row(price or {"state": "not_applicable", "n": 0}),
    ], PEERS)


def _build(queries=(), blockers=(), factors=None, zero=()):
    factors = factors or _factors(queries)
    result = {"factors": factors, "blockers": list(blockers), "content_snapshot": {"title": "Áo thun"},
              "search": {"category": "Thời trang", "queries": list(queries), "zero_result": list(zero)}}
    return build(result, factors[0], list(queries), list(zero))


def _q(query, searches, covered=False):
    return {"query": query, "searches": searches, "covered": covered}


def test_blockers_first_then_gain_per_effort():
    recs = _build(queries=[_q("áo nữ", 3), _q("áo thun nữ", 12)], blockers=[{"field": "images", "message": "Chưa có ảnh"}])
    assert recs[0]["kind"] == "blocker"
    ratios = [r["gain_points"] / r["effort"] for r in recs[1:]]
    assert ratios == sorted(ratios, reverse=True)
    search = [r for r in recs if r["kind"] == "search"]
    assert [r["id"] for r in search] == ["search:missing"]
    assert [q["query"] for q in search[0]["evidence"]["queries"]] == ["áo nữ", "áo thun nữ"]


def test_sort_ties_follow_method_order():
    recs = [{"kind": "price", "gain_points": 5, "effort": 1, "method": "ml_unvalidated"},
            {"kind": "image", "gain_points": 5, "effort": 1, "method": "weak_supervision"},
            {"kind": "info", "gain_points": 5, "effort": 1, "method": "heuristic"},
            {"kind": "search", "gain_points": 5, "effort": 1, "method": "rule"},
            {"kind": "blocker", "gain_points": 0, "effort": 1, "method": "rule"}]
    assert [r["kind"] for r in sort_recs(recs)] == ["blocker", "search", "info", "image", "price"]
    assert [METHOD_RANK[r["method"]] for r in sort_recs(recs)[1:]] == [0, 1, 2, 3]


def test_search_rec_cites_real_count_and_exact_gain(monkeypatch):
    result = _run(monkeypatch, queries=[{"query": "áo thun nữ", "searches": 12}])
    rec = next(r for r in result["recommendations"] if r["kind"] == "search")
    assert rec["why"] == '30 ngày qua khách hay tìm trong danh mục Thời trang: "áo thun nữ" (12 lần). Tên và tag của bạn chưa có các từ này'
    assert rec["field"] == "tags" and rec["gain_points"] == 0.0


def test_no_review_rec_when_not_applicable(monkeypatch):
    result = _run(monkeypatch)
    assert result["recommendations"] == []
    assert all(r["field"] != "review" for r in result["recommendations"])


def test_every_rec_has_text_field_and_method():
    image = {"state": "scored", "useful": 1, "method": "ml_unvalidated", "images": [
        {"url": "a", "duplicate": True, "issues": ["blurry"]}]}
    price = {"state": "scored", "pct": 5, "n": 8, "factor": 1.0, "confidence": 1.0, "p10": 50000, "p90": 120000}
    queries = [_q("áo nữ", 3)]
    recs = _build(queries=queries, blockers=[{"field": "title", "message": "Tên có chữ thừa"}],
                  factors=_factors(queries, image=image, median=4, price=price))
    assert len(recs) >= 4
    for r in recs:
        assert r["why"] and r["action"] and r["field"] and r["title"]
        assert r["method"] in METHOD_RANK


def test_image_quality_rec_cites_index_and_gain():
    image = {"state": "scored", "useful": 1, "method": "heuristic", "images": [
        {"url": "a", "duplicate": False, "issues": []},
        {"url": "b", "duplicate": True, "issues": ["blurry"]}]}
    factors = _factors(image=image, median=4)
    rec = next(r for r in _build(factors=factors) if r["id"] == "image:2")
    assert rec["why"] == "Ảnh số 2: trùng, mờ"
    assert rec["gain_points"] == scoring.gain(factors[0], 2) > 0 and rec["method"] == "heuristic"


def test_high_price_asks_for_reasons_never_to_cut_price():
    price = {**{"state": "scored", "pct": 5, "n": 8, "factor": 1.0, "confidence": 1.0, "p10": 50000, "p90": 120000}, "pct": 95}
    rec = next(r for r in _build(factors=_factors(price=price)) if r["kind"] == "price")
    assert rec["why"] == "Giá cao hơn vùng phổ biến 50.000–120.000 đ của 8 sản phẩm tương đồng"
    assert rec["gain_points"] == 0.0 and "hạ giá" not in rec["action"] and "giảm giá" not in rec["action"]


def test_low_price_only_asks_to_check():
    rec = _by_id(_build(factors=_factors(price={"state": "scored", "pct": 5, "n": 8, "factor": 1.0, "confidence": 1.0, "p10": 50000, "p90": 120000})), "info:price_low")
    assert rec["action"] == "Kiểm tra lại giá có nhập nhầm không" and rec["gain_points"] == 0.0


def test_missing_size_material_care_are_info(monkeypatch):
    result = _run(monkeypatch, title="Áo unisex form rộng", description="Áo mềm mại thoáng khí phù hợp mặc hằng ngày",
                  dimensions_cm={"length": 10, "width": 10, "height": 10}, weight_g=500)
    info = {r["id"]: r for r in result["recommendations"] if r["kind"] == "info"}
    assert set(info) == {"info:size", "info:material", "info:care"}
    assert info["info:size"]["why"] == "Kích thước đang là giá trị mặc định 10×10×10 cm / 500 g"
    assert info["info:size"]["gain_points"] == 0.0 and info["info:care"]["gain_points"] == 0.0


def test_todos_and_warnings_derive_from_recs(monkeypatch):
    result = _run(monkeypatch, images=[], moderation_status="REJECTED")
    recs = result["recommendations"]
    assert result["warnings"] == warnings_of(recs)
    assert result["todos"] == todos_of(recs)
    assert {w["field"] for w in result["warnings"]} >= {"images", "moderation_status"}
    assert all(w["type"] == "warning" and w["impact"] == 0 for w in result["warnings"])
    assert all(t["type"] == "todo" for t in result["todos"])


def test_todo_and_warning_items_have_full_shape(monkeypatch):
    result = _run(monkeypatch, images=[], moderation_status="REJECTED")
    keys = {"type", "code", "field", "message", "current_value", "target", "impact", "method"}
    items = result["warnings"] + result["todos"]
    assert items and all(set(i) == keys for i in items)
    assert next(w for w in result["warnings"] if w["field"] == "images")["code"] == "image"


def test_zero_result_query_is_search_rec_with_no_gain():
    recs = _build(zero=[{"query": "áo len", "searches": 4}])
    rec = next(r for r in recs if r["id"] == "search:zero")
    assert rec["why"] == '30 ngày qua khách tìm "áo len" (4 lần) nhưng sàn không có sản phẩm nào khớp'
    assert rec["gain_points"] == 0.0 and rec["method"] == "rule"


def _by_id(recs, rec_id):
    return next(r for r in recs if r["id"] == rec_id)


def test_short_description_cites_word_count_and_median():
    desc = f3.description_row({"title": "Áo", "description": "Áo thun cotton mềm"}, 40, True)
    factors = _factors(desc=desc)
    rec = _by_id(_build(factors=factors), "info:words")
    assert rec["why"] == "Mô tả có 4 từ, mặt bằng danh mục Thời trang là 40 từ"
    assert rec["field"] == "description" and rec["gain_points"] == scoring.gain(factors[1], 40) > 0


def test_description_equal_to_title_rec():
    desc = f3.description_row({"title": "Áo thun", "description": "Áo thun"}, 0)
    rec = _by_id(_build(factors=_factors(desc=desc)), "info:not_title")
    assert rec["why"] == "Mô tả đang giống hệt tên sản phẩm" and rec["gain_points"] == 0.0


def test_empty_description_rec_gains_what_median_length_would_score():
    desc = f3.description_row({"title": "Áo", "description": ""}, 40, True)
    factors = _factors(desc=desc)
    rec = _by_id(_build(factors=factors), "info:empty")
    assert rec["why"] == "Chưa có mô tả, mặt bằng danh mục Thời trang là 40 từ. Mô tả đủ dài sẽ được cộng điểm"
    assert rec["field"] == "description" and rec["gain_points"] == scoring.gain(factors[1], 40) > 0


def test_missing_price_rec():
    rec = _by_id(_build(factors=_factors(price={"state": "seller_missing"})), "price:missing")
    assert rec["why"] == "Chưa có giá bán (0/20 điểm). Nhập giá để được chấm mục này"
    assert rec["field"] == "price" and rec["gain_points"] == 20.0


def test_no_approved_tag_rec_mentions_pending():
    rec = _by_id(_build(factors=_factors(approved=0, pending=2)), "info:tags")
    assert rec["why"] == "Chưa có tag đã duyệt, còn 2 tag đang chờ duyệt"
    assert rec["action"].startswith("Chọn ít nhất 1 tag có sẵn của sàn") and rec["field"] == "tags"
    assert rec["gain_points"] > 0


def test_image_coverage_rec_when_below_median():
    image = {"state": "scored", "useful": 1, "method": "heuristic", "images": [
        {"url": "a", "duplicate": False, "issues": []}]}
    factors = _factors(image=image, median=4)
    rec = _by_id(_build(factors=factors), "image:coverage")
    assert rec["why"] == "Thêm ảnh khác góc: bạn có 1 ảnh đạt, sản phẩm toàn sàn thường có 4 ảnh"
    assert rec["field"] == "images" and rec["gain_points"] == scoring.gain(factors[0], 2) > 0


def test_scored_review_below_full_gets_rec():
    review = f3.review_row(1, 2, 0.5, 5.0)
    rec = _by_id(_build(factors=_factors(review=review)), "info:review")
    assert rec["why"] == "Có 1/2 đánh giá tốt, mỗi đánh giá tốt thêm sẽ nâng điểm"
    assert rec["field"] == "review" and rec["gain_points"] > 0






def test_blocker_titles_name_the_problem_per_field():
    blockers = [{"field": field, "message": "msg"} for field in BLOCKER_TITLES]
    recs = [r for r in _build(blockers=blockers) if r["kind"] == "blocker"]
    titles = {r["field"]: r["title"] for r in recs}
    assert len(recs) == len(BLOCKER_TITLES)
    assert len(set(titles.values())) == len(BLOCKER_TITLES)
    assert "Lỗi chặn" not in titles.values()
    assert titles["images"] == "Chưa có ảnh" and titles["variants.stock"] == "Hết hàng"
