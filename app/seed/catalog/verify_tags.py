#!/usr/bin/env python3
"""
verify_tags.py — QA Verification Suite for VietCraft Tags & Categories.
Supports CLI arguments for custom data paths with sensible project defaults.
"""

import argparse
import csv
import os
import re
import sys
import unicodedata
from pathlib import Path

TEST_CASES = [
    ("Áo Tết", "ao-tet"),
    ("ao tet", "ao-tet"),
    ("  áo   tết  ", "ao-tet"),
    ("AO TET!!!", "ao-tet"),
    ("áo tết 2027", "ao-tet"),
    ("aó tết", "ao-tet"),
    ("Áo-Tết", "ao-tet"),
    ("qua 20/10", "qua-20-10"),
    ("quà tặng mẹ", "qua-tang-me"),
    ("xyz123", "xyz123"),
]


def resolve_file(cli_path: str, filename: str) -> Path:
    """Resolve file path from CLI argument or standard repository data locations."""
    if cli_path:
        p = Path(cli_path).resolve()
        if p.exists():
            return p
        print(f"Warning: Specified file not found: {cli_path}")

    # Standard lookup locations relative to current working dir and script location
    script_dir = Path(__file__).resolve().parent
    search_dirs = [
        Path.cwd() / "app" / "data",
        Path.cwd() / "data",
        Path.cwd(),
        script_dir.parent.parent / "data",
        script_dir / "data",
        script_dir,
    ]

    for d in search_dirs:
        candidate = d / filename
        if candidate.is_file():
            return candidate.resolve()

    return script_dir / filename


def load_csv_data(filepath: Path):
    if not filepath.exists():
        return []
    with open(filepath, "r", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def clean_tag(raw_tag, tags_list):
    if not raw_tag:
        return ""
    q = raw_tag.lower().strip()
    q = q.replace("-", " ").replace("/", " ")
    q = re.sub(r"\s+", " ", q)
    q = re.sub(r"[^\w\sáàảãạăắằẳẵặâấầẩẫậéèẻẽẹêếềểễệíìỉĩịóòỏõọôốồổỗộơớờởỡợúùủũụưứừửữựýỳỷỹỵđ]", "", q).strip()
    q_nfc = unicodedata.normalize("NFC", q)

    map_chars = {
        "à": "a", "á": "a", "ả": "a", "ã": "a", "ạ": "a",
        "ă": "a", "ắ": "a", "ằ": "a", "ẳ": "a", "ẵ": "a", "ặ": "a",
        "â": "a", "ấ": "a", "ầ": "a", "ẩ": "a", "ẫ": "a", "ậ": "a",
        "è": "e", "é": "e", "ẻ": "e", "ẽ": "e", "ẹ": "e",
        "ê": "e", "ế": "e", "ề": "e", "ể": "e", "ễ": "e", "ệ": "e",
        "ì": "i", "í": "i", "ỉ": "i", "ĩ": "i", "ị": "i",
        "ò": "o", "ó": "o", "ỏ": "o", "õ": "o", "ọ": "o",
        "ô": "o", "ố": "o", "ồ": "o", "ổ": "o", "ỗ": "o", "ộ": "o",
        "ơ": "o", "ớ": "o", "ờ": "o", "ở": "o", "ỡ": "o", "ợ": "o",
        "ù": "u", "ú": "u", "ủ": "u", "ũ": "u", "ụ": "u",
        "ư": "u", "ứ": "u", "ừ": "u", "ử": "u", "ự": "u", "ữ": "u",
        "ỳ": "y", "ý": "y", "ỷ": "y", "ỹ": "y", "ỵ": "y",
        "đ": "d",
    }
    q_stripped = "".join(map_chars.get(c, c) for c in q_nfc)
    q_stripped_noyear = re.sub(r"\b20\d\d\b", "", q_stripped).strip()
    q_stripped_noyear = re.sub(r"\s+", " ", q_stripped_noyear)

    for t in tags_list:
        tag_id = t["tag_id"]
        aliases_list = [a.strip() for a in t["aliases"].split("|")]
        for alias in aliases_list:
            alias_clean = alias.lower().replace("-", " ").replace("/", " ")
            alias_clean = re.sub(r"\s+", " ", alias_clean).strip()
            alias_nfc = unicodedata.normalize("NFC", alias_clean)
            alias_stripped = "".join(map_chars.get(c, c) for c in alias_nfc)
            if q == alias_clean or q_stripped == alias_stripped or q_stripped_noyear == alias_stripped:
                return tag_id
    return raw_tag.strip()


def parse_args():
    parser = argparse.ArgumentParser(description="VietCraft Tags QA Suite")
    parser.add_argument("--tags", type=str, default=None, help="Đường dẫn file tags.csv")
    parser.add_argument("--categories", type=str, default=None, help="Đường dẫn file categories.csv")
    parser.add_argument("--report", type=str, default=None, help="Đường dẫn xuất file báo cáo Markdown")
    return parser.parse_args()


def main():
    args = parse_args()
    print("=== VietCraft QA Verification Suite & Tags QA Logger ===")

    tags_path = resolve_file(args.tags, "tags.csv")
    categories_path = resolve_file(args.categories, "categories.csv")

    if not tags_path.exists() or not categories_path.exists():
        print(f"❌ Lỗi: Không tìm thấy file dữ liệu đầu vào.")
        print(f"  - tags.csv       : {tags_path} (exists: {tags_path.exists()})")
        print(f"  - categories.csv : {categories_path} (exists: {categories_path.exists()})")
        print("💡 Hướng dẫn: Đặt file vào app/data/ hoặc truyền flag --tags <path> --categories <path>")
        sys.exit(1)

    tags = load_csv_data(tags_path)
    categories = load_csv_data(categories_path)
    valid_category_ids = set(c["category_id"] for c in categories)

    results = []

    # Check 1: Duplicate tag ids
    tag_ids = [t["tag_id"] for t in tags]
    duplicate_tags = [t for t in set(tag_ids) if tag_ids.count(t) > 1]
    check1_passed = len(duplicate_tags) == 0
    results.append({
        "check": "1. Có tag nào trùng mã không",
        "detail": f"{len(duplicate_tags)} tag bị trùng" if not check1_passed else "0 tag bị trùng",
        "status": "ĐẠT" if check1_passed else "KHÔNG ĐẠT",
    })

    # Check 2: Unmapped keywords
    official_keywords = [
        "áo thun", "áo phông nam", "áo phông nữ", "in áo thun", "áo đôi",
        "áo nhóm", "áo lớp", "áo đồng phục", "áo gia đình", "túi tote",
        "tranh treo tường", "tranh canvas", "móc khóa", "áo tết", "quà tết",
        "lì xì tết", "trang trí tết", "quà 8/3", "quà tặng mẹ", "quà 20/10",
        "quà 20/11", "quà tặng thầy cô", "quà giáng sinh", "trang trí noel", "quà valentine",
        "quà tặng người yêu", "quà tặng", "quà cưới", "quà tân gia", "quà tặng bạn thân",
        "quà handmade", "quà lưu niệm", "áo anime", "áo oversize", "áo local brand",
    ]
    unmapped_kw = []
    for kw in official_keywords:
        mapped = clean_tag(kw, tags)
        if mapped == kw:
            unmapped_kw.append(kw)

    check2_passed = len(unmapped_kw) == 0
    results.append({
        "check": "2. Có từ khoá Google nào chưa có tag không",
        "detail": f"Còn {len(unmapped_kw)} từ khóa chưa map ({', '.join(unmapped_kw)})" if not check2_passed else "0 từ khóa bị sót",
        "status": "ĐẠT" if check2_passed else "KHÔNG ĐẠT",
    })

    # Check 3: Tag count
    total_tags = len(tags)
    check3_passed = 60 <= total_tags <= 80
    results.append({
        "check": "3. Tổng số tag",
        "detail": f"{total_tags} tag (phạm vi: từ 60 tới 80)",
        "status": "ĐẠT" if check3_passed else "KHÔNG ĐẠT",
    })

    # Check 4: Orphan tags
    orphan_tags = [t["tag_id"] for t in tags if t.get("category_id") not in valid_category_ids]
    check4_passed = len(orphan_tags) == 0
    results.append({
        "check": "4. Có tag nào không thuộc danh mục nào không",
        "detail": f"{len(orphan_tags)} tag mồ côi ({', '.join(orphan_tags)})" if not check4_passed else "0 tag mồ côi",
        "status": "ĐẠT" if check4_passed else "KHÔNG ĐẠT",
    })

    # Check 5: 10 test cases
    print("\nChạy 10 test làm sạch tag:")
    failed_tests = []
    for inp, expected in TEST_CASES:
        res = clean_tag(inp, tags)
        if res == expected:
            print(f"  [OK] '{inp}' -> '{res}'")
        else:
            print(f"  [FAIL] '{inp}' -> expected '{expected}', got '{res}'")
            failed_tests.append((inp, expected, res))

    check5_passed = len(failed_tests) == 0
    results.append({
        "check": "5. Chạy 10 test làm sạch tag",
        "detail": f"Thông qua {10 - len(failed_tests)}/10 bài test" if not check5_passed else "10/10 bài test thông qua",
        "status": "ĐẠT" if check5_passed else "KHÔNG ĐẠT",
    })

    all_passed = all(r["status"] == "ĐẠT" for r in results)
    print("\nQA SUMMARY TABLE:")
    for idx, r in enumerate(results, 1):
        print(f"  {idx}. {r['check']:<45} [{r['status']}] ({r['detail']})")

    if all_passed:
        print("\n🎉 ALL QA CHECKS PASSED!")
    else:
        print("\n❌ SOME QA CHECKS FAILED!")

    # Determine report output path
    if args.report:
        report_path = Path(args.report).resolve()
    else:
        # Default report in docs/qc/tags.md
        report_candidates = [
            Path.cwd() / "docs" / "qc" / "tags.md",
            Path(__file__).resolve().parent.parent.parent.parent / "docs" / "qc" / "tags.md",
        ]
        report_path = report_candidates[0]

    report_path.parent.mkdir(parents=True, exist_ok=True)

    md_content = f"""# Báo cáo Kiểm tra Chất lượng (QC) - Bộ Dữ liệu Tags

Báo cáo kiểm tra tính toàn vẹn của mã tag (`tags.csv`), quan hệ với từ khóa Google Trends (`tag_keyword_map.csv`), danh mục sản phẩm (`categories.csv`) và kiểm tra tự động thuật toán chuẩn hóa tag.

---

## 1. Kết quả kiểm tra chất lượng (5 bài kiểm tra)

| # | Nội dung kiểm tra | Kết quả thực tế | Trạng thái |
|---|---|---|---|
"""
    for idx, r in enumerate(results, 1):
        md_content += f"| {idx} | {r['check']} | {r['detail']} | **{r['status']}** |\n"

    md_content += f"""
---

## 2. Chi tiết kết quả 10 bài test chuẩn hóa làm sạch tag (`clean_tag`)

Hàm `clean_tag` giúp xử lý các tag nhập tự do từ người bán để quy đổi về tag chuẩn trong hệ thống (hoặc giữ nguyên nếu là tag mới lạ).

| Dữ liệu người bán gõ | Kết quả mong đợi | Kết quả thực tế | Trạng thái |
|---|---|---|---|
"""
    for inp, expected in TEST_CASES:
        res = clean_tag(inp, tags)
        status = "ĐẠT" if res == expected else "LỖI"
        md_content += f"| `{inp}` | `{expected}` | `{res}` | **{status}** |\n"

    md_content += """
---
*Báo cáo được chạy và tạo tự động bởi verify_tags.py.*
"""

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    print(f"\nReport written to {report_path} successfully!")

    if not all_passed:
        sys.exit(1)


if __name__ == "__main__":
    main()
