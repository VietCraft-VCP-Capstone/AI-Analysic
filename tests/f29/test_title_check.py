from app.core.f29.material import materials_of
from app.core.f29.title_check import check


def _types(title):
    return [(h["type"], h["message"].split(":")[0]) for h in check(title)]


def test_scraped_ui_text_is_warning_with_clean_title():
    hints = check("icon arrow left boldicon arrow right bold Share: Favorite (48) Thắt lưng vải canvas nam - TL05D")
    assert hints[0]["type"] == "warning"
    assert hints[0]["target"] == "Thắt lưng vải canvas nam - TL05D"


def test_sold_counter_copied_from_marketplace():
    hints = check("Áo Thun Nam Nữ Form Rộng Cotton - Đã bán 1,2k")
    assert hints[0]["target"] == "Áo Thun Nam Nữ Form Rộng Cotton"


def test_contact_info_is_warning():
    hints = check("Vòng tay bạc 925 handmade liên hệ zalo 0912.345.678")
    assert hints[0]["type"] == "warning" and "liên hệ" in hints[0]["message"]
    assert hints[0]["target"] == "Vòng tay bạc 925 handmade"


def test_style_issues_are_info_only():
    assert [h["type"] for h in check("ÁO KHOÁC LÔNG CỪU NHIỀU MÀU VẢI DÀY")] == ["info"]
    assert [h["type"] for h in check("Áo thun nam áo thun nữ áo thun cặp đôi")] == ["info"]


def test_clean_titles_pass():
    assert check("Bộ Cốc Gốm Men Mộc Không Quai 5 Món – 1 Cốc Lớn Và 4 Cốc Nhỏ") == []
    assert check("Tranh in canvas 40x60 cm, khung gỗ sồi tự nhiên, mã 01234") == []


def test_length_hint_kept():
    assert check("Áo thun")[0]["type"] == "info"


def test_materials_prefer_declared_then_title():
    assert materials_of({"materials": ["100% Cotton"], "title": "Áo thun"}) == {"cotton"}
    assert materials_of({"materials": ["Titan không gỉ"]}) == {"titan không gỉ"}
    assert materials_of({"materials": "cotton"}) == {"cotton"}
    assert materials_of({"materials": None, "title": "Túi Tote Canvas"}) == {"canvas"}
    assert materials_of({"title": "Giày Sneaker Nam Êm Chân"}) == frozenset()


def test_declared_material_conflicting_with_title_is_flagged_and_not_compared():
    from app.core.f29.material import material_conflict
    belt = {"materials": ["nỉ", "da bò"], "title": "Thắt lưng vải canvas nam"}
    assert material_conflict(belt) == (["da bò", "nỉ"], ["canvas"])
    assert materials_of(belt) == frozenset()
    assert material_conflict({"materials": ["da"], "title": "Ví da bò"}) is None
    assert materials_of({"materials": ["da"], "title": "Ví da bò"}) == {"da"}
    assert material_conflict({"materials": ["100% Cotton"], "title": "Áo thun cotton"}) is None
    assert material_conflict({"materials": ["da bò"], "title": "Túi xách da PU nữ"}) == (["da bò"], ["da pu"])
    assert material_conflict({"materials": ["gỗ"], "title": "Bàn gỗ sồi"}) is None


def test_common_non_material_words_are_ignored():
    from app.core.listing_intel.lexicon import attributes
    assert attributes("Quà tặng đồng nghiệp, đồng hồ dạ quang, váy dạ hội")["material"] == []
    assert sorted(attributes("Tượng đồng đúc tay, áo khoác dạ")["material"]) == ["dạ", "đồng"]


def test_better_category_only_when_one_clear_match():
    from app.core.f29.category_check import better_category
    names = ["Giày dép", "Sneaker", "Thắt Lưng", "Áo thun", "Áo khoác", "quần"]
    assert better_category("Giày Sneaker Nam Êm Chân", "Giày dép", names) == "Sneaker"
    assert better_category("Thắt lưng vải canvas", "Thắt Lưng", names) is None
    assert better_category("Đồng hồ thời trang nam", "Trang sức", names) is None
    assert better_category("Set áo thun và áo khoác", "Váy Đầm", names) is None
    assert better_category("Giày Sneaker", None, names) is None
    assert better_category(12345, "Giày dép", names) is None


def test_category_hint_skips_real_world_false_cases():
    from app.core.f29.category_check import better_category
    names = ["Áo thun", "Áo khoác", "Áo Lông", "Áo quần bóng đá", "Trang trí", "Tranh ảnh", "Set áo váy",
             "Set Áo Quần", "quần", "Điện Thoại", "phụ kiện điện thoại"]
    assert better_category("Áo Thun Messi Phong Cách Thể Thao", "Áo quần bóng đá", names) is None
    assert better_category("Tranh In Chùa Cầu Hội An Màu Nước Trang Trí Hành Lang", "Tranh ảnh", names) is None
    assert better_category("Áo Khoác Lông Cừu Teddy Dáng Rộng", "Áo Lông", names) is None
    assert better_category("Set Áo Khoác Hoodie Chân Váy Phối Ren", "Set áo váy", names) is None
    assert better_category("Áo 2 Dây Xếp Tầng Hannie Top + Quần", "Set áo váy", names) is None
    assert better_category("Điện thoại OPPO Reno15 F 5G 12GB/256GB", "phụ kiện điện thoại", names) == "Điện Thoại"
