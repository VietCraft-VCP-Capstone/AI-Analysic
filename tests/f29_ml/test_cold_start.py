from unittest.mock import MagicMock
from bson import ObjectId
from app.core.f29.ml.cold_start import estimate_cold_start_propensity


def test_cold_start_invalid_id():
    db = MagicMock()
    assert estimate_cold_start_propensity("invalid_id", db) is None


def test_cold_start_missing_product():
    db = MagicMock()
    db["products"].find_one.return_value = None
    assert estimate_cold_start_propensity(str(ObjectId()), db) is None


def test_cold_start_valid_estimation(monkeypatch):
    p_id = str(ObjectId())
    db = MagicMock()
    db["products"].find_one.return_value = {
        "_id": ObjectId(p_id),
        "title": "Túi thổ cẩm dệt tay",
        "categories": ["Túi ví"],
        "images": ["img1.jpg", "img2.jpg"],
        "description": "Mô tả túi thổ cẩm cao cấp dệt tay từ làng nghề truyền thống.",
    }
    db["product_daily_metrics"].aggregate.return_value = [{"views": 25, "carts": 3}]
    db["products"].count_documents.return_value = 15

    res = estimate_cold_start_propensity(p_id, db)
    assert res is not None
    assert res["product_id"] == p_id
    assert 0 <= res["score"] <= 100
    assert 0.0 < res["probability"] < 1.0
    assert res["peer_group"]["name"] == "Túi ví"
    assert res["model"]["test_auc"] == 0.845
    assert len(res["compare"]) == 4


def test_cold_start_sparse_peers_benchmark():
    p_id = str(ObjectId())
    db = MagicMock()
    db["products"].find_one.return_value = {
        "_id": ObjectId(p_id),
        "title": "Gốm Bát Tràng men rạn",
        "categories": ["Gốm sứ thủ công"],
        "images": ["img1.jpg"],
        "description": "Bình gốm rạn phong cách cổ.",
    }
    db["product_daily_metrics"].aggregate.return_value = []
    db["products"].count_documents.side_effect = [2, 10]

    res = estimate_cold_start_propensity(p_id, db)
    assert res is not None
    assert res["peer_group"]["name"] == "Gốm sứ thủ công (Tiêu chuẩn ngành)"


def test_cold_start_listing_health_scores_axes_advice():
    p_id = str(ObjectId())
    db = MagicMock()
    db["products"].find_one.return_value = {
        "_id": ObjectId(p_id),
        "title": "Mũ cói vintage",
        "categories": ["Mũ nón"],
        "images": ["img1.jpg"],
        "description": "Mũ cói đi biển thời trang.",
    }
    db["listing_health_scores"].find_one.return_value = {
        "score": 65.0,
        "axes": {"image": 30.0, "description": 50.0, "price": 40.0}
    }
    db["product_daily_metrics"].aggregate.return_value = []
    db["products"].count_documents.return_value = 20

    res = estimate_cold_start_propensity(p_id, db)
    assert res is not None
    assert len(res["advice"]) > 0
    features = [a["feature"] for a in res["advice"]]
    assert "photos" in features or "description_length" in features or "log_price_rel" in features


