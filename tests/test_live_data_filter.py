import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.api.v1._live import LOC_SP_THAT, LOC_DON_THAT


def test_loc_sp_that_co_seed_ref():
    """LOC_SP_THAT phải lọc seed_ref KHÔNG tồn tại."""
    assert LOC_SP_THAT == {"seed_ref": {"$exists": False}, "is_hidden": {"$ne": True}}, \
        f"LOC_SP_THAT sai: {LOC_SP_THAT}"
    print("  ✓ LOC_SP_THAT = {seed_ref: {$exists: False}}")


def test_loc_don_that_co_seed_ref_va_is_simulated():
    """LOC_DON_THAT phải lọc seed_ref KHÔNG tồn tại và is_simulated không phải True."""
    expected = {
        "seed_ref": {"$exists": False},
        "is_simulated": {"$ne": True}
    }
    assert LOC_DON_THAT == expected, \
        f"LOC_DON_THAT sai: {LOC_DON_THAT}"
    print("  ✓ LOC_DON_THAT = {seed_ref: {$exists: False}, is_simulated: {$ne: True}}")


def test_loc_filters_used_in_functions():
    """LOC_SP_THAT và LOC_DON_THAT phải được dùng trong san_pham_live() và gia_cung_danh_muc_live()."""
    source_file = ROOT_DIR / "app" / "api" / "v1" / "_live.py"
    source_code = source_file.read_text(encoding="utf-8")

    # Kiểm tra định nghĩa
    assert "LOC_SP_THAT = {" in source_code, "LOC_SP_THAT chưa được định nghĩa"
    assert "LOC_DON_THAT = {" in source_code, "LOC_DON_THAT chưa được định nghĩa"

    # Kiểm tra san_pham_live() dùng LOC_SP_THAT
    san_pham_start = source_code.find("def san_pham_live(")
    san_pham_next_func = source_code.find("def ", san_pham_start + 1)
    san_pham_section = source_code[san_pham_start:san_pham_next_func]

    assert "LOC_SP_THAT" in san_pham_section, \
        "san_pham_live() không dùng LOC_SP_THAT"
    assert "LOC_SP_THAT" in san_pham_section and ".find(" in san_pham_section, \
        "san_pham_live() có LOC_SP_THAT nhưng không được dùng trong find()"

    # Kiểm tra gia_cung_danh_muc_live() dùng LOC_SP_THAT
    gia_cung_start = source_code.find("def gia_cung_danh_muc_live(")
    gia_cung_next_func = source_code.find("def ", gia_cung_start + 1)
    gia_cung_section = source_code[gia_cung_start:gia_cung_next_func]

    assert "LOC_SP_THAT" in gia_cung_section, \
        "gia_cung_danh_muc_live() không dùng LOC_SP_THAT"
    assert "LOC_SP_THAT" in gia_cung_section and ".find(" in gia_cung_section, \
        "gia_cung_danh_muc_live() có LOC_SP_THAT nhưng không được dùng trong find()"

    print("  ✓ LOC_SP_THAT được dùng trong san_pham_live()")
    print("  ✓ LOC_SP_THAT được dùng trong gia_cung_danh_muc_live()")


def test_single_location_definition():
    """Bộ lọc phải được định nghĩa ở một chỗ duy nhất trong _live.py."""
    source_file = ROOT_DIR / "app" / "api" / "v1" / "_live.py"
    source_code = source_file.read_text(encoding="utf-8")

    # Kiểm tra chỉ có một định nghĩa LOC_SP_THAT
    count_loc_sp = source_code.count("LOC_SP_THAT = {")
    assert count_loc_sp == 1, \
        f"LOC_SP_THAT định nghĩa {count_loc_sp} lần, phải chỉ 1 lần"

    # Kiểm tra chỉ có một định nghĩa LOC_DON_THAT
    count_loc_don = source_code.count("LOC_DON_THAT = {")
    assert count_loc_don == 1, \
        f"LOC_DON_THAT định nghĩa {count_loc_don} lần, phải chỉ 1 lần"

    print("  ✓ LOC_SP_THAT định nghĩa đúng 1 lần")
    print("  ✓ LOC_DON_THAT định nghĩa đúng 1 lần")


# RUN ALL TESTS

if __name__ == "__main__":
    print("=== KIỂM TRA BỘ LỌC DỮ LIỆU GIẢ (SEED) - PLAN §12 ===\n")

    cac_test = [
        ("LOC_SP_THAT định nghĩa đúng", test_loc_sp_that_co_seed_ref),
        ("LOC_DON_THAT định nghĩa đúng", test_loc_don_that_co_seed_ref_va_is_simulated),
        ("Bộ lọc được dùng trong hàm", test_loc_filters_used_in_functions),
        ("Định nghĩa ở một chỗ duy nhất", test_single_location_definition),
    ]

    hong = 0
    for ten, ham in cac_test:
        try:
            ham()
            print(f"✓ {ten}\n")
        except AssertionError as e:
            hong += 1
            print(f"✗ {ten}\n  {e}\n")
        except Exception as e:
            hong += 1
            print(f"✗ {ten}\n  Lỗi: {e}\n")

    print()
    if hong:
        print(f"❌ {hong}/{len(cac_test)} TEST HỎNG")
        sys.exit(1)
    print(f"✅ {len(cac_test)}/{len(cac_test)} TEST PASS — Bộ lọc dữ liệu giả được implement đúng")
