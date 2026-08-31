import re
import csv
import sys
import os
import unicodedata

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
    ("xyz123", "xyz123")
]

def load_csv_data(filepath):
    if not os.path.exists(filepath):
        return []
    with open(filepath, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def clean_tag(raw_tag, tags_list):
    if not raw_tag:
        return ""
    q = raw_tag.lower().strip()
    q = q.replace("-", " ").replace("/", " ")
    q = re.sub(r"\s+", " ", q)
    q = re.sub(r"[^\w\sáàảãạăắằẳẵặâấầẩẫậéèẻẽẹêếềểễệíìỉĩịóòỏõọôốồổỗộơớờởỡợúùủũụưứừửữựýỳỷỹỵđ]", "", q).strip()
    q_nfc = unicodedata.normalize('NFC', q)
    
    map_chars = {
        'à': 'a', 'á': 'a', 'ả': 'a', 'ã': 'a', 'ạ': 'a',
        'ă': 'a', 'ắ': 'a', 'ằ': 'a', 'ẳ': 'a', 'ẵ': 'a', 'ặ': 'a',
        'â': 'a', 'ấ': 'a', 'ầ': 'a', 'ẩ': 'a', 'ẫ': 'a', 'ậ': 'a',
        'è': 'e', 'é': 'e', 'ẻ': 'e', 'ẽ': 'e', 'ẹ': 'e',
        'ê': 'e', 'ế': 'e', 'ề': 'e', 'ể': 'e', 'ễ': 'e', 'ệ': 'e',
        'ì': 'i', 'í': 'i', 'ỉ': 'i', 'ĩ': 'i', 'ị': 'i',
        'ò': 'o', 'ó': 'o', 'ỏ': 'o', 'õ': 'o', 'ọ': 'o',
        'ô': 'o', 'ố': 'o', 'ồ': 'o', 'ổ': 'o', 'ỗ': 'o', 'ộ': 'o',
        'ơ': 'o', 'ớ': 'o', 'ờ': 'o', 'ở': 'o', 'ỡ': 'o', 'ợ': 'o',
        'ù': 'u', 'ú': 'u', 'ủ': 'u', 'ũ': 'u', 'ụ': 'u',
        'ư': 'u', 'ứ': 'u', 'ừ': 'u', 'ử': 'u', 'ự': 'u', 'ữ': 'u',
        'ỳ': 'y', 'ý': 'y', 'ỷ': 'y', 'ỹ': 'y', 'ỵ': 'y',
        'đ': 'd'
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
            alias_nfc = unicodedata.normalize('NFC', alias_clean)
            alias_stripped = "".join(map_chars.get(c, c) for c in alias_nfc)
            if q == alias_clean or q_stripped == alias_stripped or q_stripped_noyear == alias_stripped:
                return tag_id
    return raw_tag.strip()

def main():
    print("=== VietCraft QA Verification Suite & Tags QA Logger ===")
    script_dir = os.path.dirname(os.path.abspath(__file__))
    tags_path = os.path.join(script_dir, "tags.csv")
    categories_path = os.path.join(script_dir, "categories.csv")
    
    if not os.path.exists(tags_path) or not os.path.exists(categories_path):
        print("Error: tags.csv or categories.csv missing.")
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
        "status": "ĐẠT" if check1_passed else "KHÔNG ĐẠT"
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
        "áo vintage", "áo hoodie", "áo bóng đá việt nam", "áo thun thể thao", "quà sinh nhật"
    ]
    mapped_kws = set(t["source_keywords"] for t in tags)
    missing_kws = set(official_keywords) - mapped_kws
    check2_passed = len(missing_kws) == 0
    results.append({
        "check": "2. Có từ khoá Google nào chưa có tag không",
        "detail": f"Thiếu từ khóa: {missing_kws}" if not check2_passed else "0 từ khóa bị sót",
        "status": "ĐẠT" if check2_passed else "KHÔNG ĐẠT"
    })
    
    # Check 3: Tag count boundaries
    total_tags = len(tags)
    check3_passed = 60 <= total_tags <= 80
    results.append({
        "check": "3. Tổng số tag",
        "detail": f"{total_tags} tag (phạm vi: từ 60 tới 80)",
        "status": "ĐẠT" if check3_passed else "KHÔNG ĐẠT"
    })
    
    # Check 4: Orphan categories check
    orphan_tags = [t["tag_id"] for t in tags if t["category_id"] not in valid_category_ids]
    check4_passed = len(orphan_tags) == 0
    results.append({
        "check": "4. Có tag nào không thuộc danh mục nào không",
        "detail": f"Tag mồ côi: {orphan_tags}" if not check4_passed else "0 tag mồ côi",
        "status": "ĐẠT" if check4_passed else "KHÔNG ĐẠT"
    })
    
    # Check 5: Run 10 cleanup test cases
    failed_tests = []
    print("\nChạy 10 test làm sạch tag:")
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
        "status": "ĐẠT" if check5_passed else "KHÔNG ĐẠT"
    })
    
    all_passed = all(r["status"] == "ĐẠT" for r in results)
    print("\nQA SUMMARY TABLE:")
    for idx, r in enumerate(results, 1):
        print(f"  {idx}. {r['check']:<45} [{r['status']}] ({r['detail']})")
        
    if all_passed:
        print("\n🎉 ALL QA CHECKS PASSED!")
    else:
        print("\n❌ SOME QA CHECKS FAILED!")
        
    workspace_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(script_dir))))
    docs_qc_dir = os.path.join(workspace_root, "docs", "qc")
    os.makedirs(docs_qc_dir, exist_ok=True)
    report_path = os.path.join(docs_qc_dir, "tags.md")
    
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
