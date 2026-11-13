"""F42: lọc thẻ gợi ý — ngắn, đúng sản phẩm seller đăng. Không gọi mạng/DB."""

from app.services.f42.tag_curator import curate_tags, normalize_tag


def test_drops_fragments_and_unrelated_platform_tags():
    out = curate_tags(["tay ngắn", "thời trang", "nam cổ tròn", "tròn nam", "pt cổ tròn", "áo thun",
                       "phá cách", "set áo váy", "#Áo Thun Nam"],
                      "Áo thun nam cổ tròn tay ngắn", product="Áo thun")
    assert out[:3] == ["tay ngắn", "áo thun", "áo thun nam"]
    for bad in ("thời trang", "nam cổ tròn", "tròn nam", "pt cổ tròn", "phá cách", "set áo váy"):
        assert bad not in out
    assert "áo thun cổ tròn" in out and "cổ tròn" in out          # dựng từ chính tên seller ghi


def test_long_or_wrong_model_google_phrases_dropped():
    out = curate_tags(["ốp lưng iphone 17 pro max cho iphone 14 pro max", "ốp lưng iphone 14", "ốp lưng",
                       "áo thun", "chân váy"], "Ốp lưng iPhone 17 Pro Max", product="Ốp lưng")
    assert out == ["ốp lưng", "ốp lưng iphone 17 pro max"]


def test_risky_banned_generic_and_duplicates():
    out = curate_tags(["nến thơm chính hãng", "nến thơm giá sốc", "nen thom", "Nến thơm", "nến", "đen"],
                      "Nến thơm sáp đậu nành màu đen", banned=["giá sốc"])
    assert out[0] == "nến thơm"                                     # bản có dấu thay bản không dấu
    assert "nến" not in out and "đen" not in out
    assert not any("chính hãng" in t or "giá sốc" in t for t in out)
    assert "sáp đậu nành" in out and len(out) <= 10


def test_brand_kept_and_normalize():
    assert "zippo" in curate_tags(["zippo", "hộp quẹt"], "Bật lửa Zippo", brand="Zippo")
    assert normalize_tag("  #Gốm   Bát Tràng, ") == "gốm bát tràng"
