import csv
import sys
import os

def load_tags_info(csv_path):
    """Loads all tags from tags.csv and maps tag_id to its properties."""
    tags = []
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            tags.append(row)
    return tags

def main():
    print("=== VietCraft Tag-Keyword Mapping Generator & Tester ===")
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    tags_path = os.path.join(script_dir, "tags.csv")
    map_csv_path = os.path.join(script_dir, "tag_keyword_map.csv")
    
    if not os.path.exists(tags_path):
        print(f"Error: tags.csv not found at {tags_path}. Run generate_tags.py first.")
        sys.exit(1)
        
    tags = load_tags_info(tags_path)
    
    # 1. Start with baseline mapping: each tag maps to its source_keyword with weight 1.0
    # Also extract the topic from category_id: e.g., apparel.tet -> topic 'tet'
    raw_mappings = []
    for t in tags:
        tag_id = t["tag_id"]
        source_keyword = t["source_keywords"]
        category_id = t["category_id"]
        
        # Determine topic from category_id
        topic = "evergreen"
        if "." in category_id:
            topic = category_id.split(".")[1]
            
        raw_mappings.append({
            "tag_id": tag_id,
            "keyword": source_keyword,
            "topic": topic,
            "weight": 1.0
        })
        
    # 2. Add extra semantic connections to enrich bi-directional queries
    extra_connections = [
        # General áo thun connections
        {"tag_id": "ao-thun", "keyword": "áo phông nam", "topic": "evergreen", "weight": 0.8},
        {"tag_id": "ao-thun", "keyword": "áo phông nữ", "topic": "evergreen", "weight": 0.8},
        {"tag_id": "ao-thun", "keyword": "in áo thun", "topic": "evergreen", "weight": 0.8},
        {"tag_id": "ao-thun", "keyword": "áo đôi", "topic": "couple", "weight": 0.5},
        {"tag_id": "ao-thun", "keyword": "áo nhóm", "topic": "group", "weight": 0.5},
        {"tag_id": "ao-thun", "keyword": "áo lớp", "topic": "school", "weight": 0.5},
        {"tag_id": "ao-thun", "keyword": "áo gia đình", "topic": "family", "weight": 0.5},
        
        # Mối liên hệ chéo của Áo phông nam/nữ/in áo thun với tag ao-thun
        {"tag_id": "ao-phong-nam", "keyword": "áo thun", "topic": "evergreen", "weight": 0.8},
        {"tag_id": "ao-phong-nu", "keyword": "áo thun", "topic": "evergreen", "weight": 0.8},
        {"tag_id": "in-ao-thun", "keyword": "áo thun", "topic": "evergreen", "weight": 0.8},
        
        # Women's Day connections
        {"tag_id": "qua-tang-phu-nu", "keyword": "quà 20/10", "topic": "womens_day", "weight": 1.0},
        {"tag_id": "qua-tang-phu-nu", "keyword": "quà tặng mẹ", "topic": "womens_day", "weight": 1.0},
        {"tag_id": "qua-tang-phu-nu", "keyword": "quà tặng", "topic": "gift", "weight": 0.5},
        
        # Gift/Occasion tags connections
        {"tag_id": "qua-tang", "keyword": "quà 8/3", "topic": "womens_day", "weight": 0.8},
        {"tag_id": "qua-tang", "keyword": "quà tặng mẹ", "topic": "womens_day", "weight": 0.8},
        {"tag_id": "qua-tang", "keyword": "quà 20/10", "topic": "womens_day", "weight": 0.8},
        {"tag_id": "qua-tang", "keyword": "quà 20/11", "topic": "teachers_day", "weight": 0.8},
        {"tag_id": "qua-tang", "keyword": "quà giáng sinh", "topic": "christmas", "weight": 0.8},
        {"tag_id": "qua-tang", "keyword": "quà valentine", "topic": "valentine", "weight": 0.8},
        {"tag_id": "qua-tang", "keyword": "quà tặng người yêu", "topic": "valentine", "weight": 0.8},
        {"tag_id": "qua-tang", "keyword": "quà cưới", "topic": "wedding", "weight": 0.8},
        {"tag_id": "qua-tang", "keyword": "quà tân gia", "topic": "housewarming", "weight": 0.8},
        {"tag_id": "qua-tang", "keyword": "quà tặng bạn thân", "topic": "friendship", "weight": 0.8},
        {"tag_id": "qua-tang", "keyword": "quà sinh nhật", "topic": "gift", "weight": 0.8},
        {"tag_id": "qua-tang", "keyword": "quà lưu niệm", "topic": "travel", "weight": 0.5},
        
        # Teacher's Day connections
        {"tag_id": "qua-tang-thay-co", "keyword": "quà tặng thầy cô", "topic": "teachers_day", "weight": 1.0},
        {"tag_id": "qua-tang-thay-co", "keyword": "quà 20/11", "topic": "teachers_day", "weight": 1.0},
        {"tag_id": "qua-tang-thay-co", "keyword": "quà tặng", "topic": "gift", "weight": 0.5},
        {"tag_id": "tri-an-thay-co", "keyword": "quà 20/11", "topic": "teachers_day", "weight": 1.0},
        
        # Tet connections
        {"tag_id": "qua-tet", "keyword": "quà tặng", "topic": "gift", "weight": 0.5},
        {"tag_id": "qua-tet", "keyword": "trang trí tết", "topic": "tet", "weight": 0.5},
        {"tag_id": "ao-tet", "keyword": "áo thun", "topic": "evergreen", "weight": 0.5},
        
        # Streetwear connections
        {"tag_id": "ao-oversize", "keyword": "áo local brand", "topic": "streetwear", "weight": 0.8},
        {"tag_id": "ao-oversize", "keyword": "áo thun", "topic": "evergreen", "weight": 0.8},
        {"tag_id": "ao-oversize", "keyword": "áo hoodie", "topic": "streetwear", "weight": 0.8},
        
        {"tag_id": "ao-local-brand", "keyword": "áo oversize", "topic": "streetwear", "weight": 0.8},
        {"tag_id": "ao-local-brand", "keyword": "áo thun", "topic": "evergreen", "weight": 0.8},
        {"tag_id": "ao-vintage", "keyword": "áo thun", "topic": "evergreen", "weight": 0.8},
        {"tag_id": "ao-hoodie", "keyword": "áo oversize", "topic": "streetwear", "weight": 0.8},
        
        # Couple / Valentine connections
        {"tag_id": "ao-doi", "keyword": "quà tặng người yêu", "topic": "valentine", "weight": 0.5},
        {"tag_id": "ao-cap-doi", "keyword": "quà tặng người yêu", "topic": "valentine", "weight": 0.5},
        {"tag_id": "qua-tang-nguoi-yeu", "keyword": "quà valentine", "topic": "valentine", "weight": 0.8},
    ]
    
    # Merge and avoid duplicate pairs (keeping highest weight if duplicates exist)
    merged_map = {}
    for m in raw_mappings + extra_connections:
        key = (m["tag_id"], m["keyword"])
        if key not in merged_map or m["weight"] > merged_map[key]["weight"]:
            merged_map[key] = m
            
    final_mappings = list(merged_map.values())
    
    # Sort by tag_id, then keyword for clean output
    final_mappings = sorted(final_mappings, key=lambda x: (x["tag_id"], x["keyword"]))
    
    # 3. Validation assertions
    # Verify no unmapped tags
    all_mapped_tags = set(m["tag_id"] for m in final_mappings)
    all_design_tags = set(t["tag_id"] for t in tags)
    unmapped_tags = all_design_tags - all_mapped_tags
    if unmapped_tags:
        print(f"FAIL: Unmapped tag_ids exist: {unmapped_tags}")
        sys.exit(1)
        
    # Verify no unmapped keywords
    all_mapped_kws = set(m["keyword"] for m in final_mappings)
    # The official 40 keywords list
    official_kws_set = set([
        "áo thun", "áo phông nam", "áo phông nữ", "in áo thun", "áo đôi",
        "áo nhóm", "áo lớp", "áo đồng phục", "áo gia đình", "túi tote",
        "tranh treo tường", "tranh canvas", "móc khóa", "áo tết", "quà tết",
        "lì xì tết", "trang trí tết", "quà 8/3", "quà tặng mẹ", "quà 20/10",
        "quà 20/11", "quà tặng thầy cô", "quà giáng sinh", "trang trí noel", "quà valentine",
        "quà tặng người yêu", "quà tặng", "quà cưới", "quà tân gia", "quà tặng bạn thân",
        "quà handmade", "quà lưu niệm", "áo anime", "áo oversize", "áo local brand",
        "áo vintage", "áo hoodie", "áo bóng đá việt nam", "áo thun thể thao", "quà sinh nhật"
    ])
    unmapped_kws = official_kws_set - all_mapped_kws
    if unmapped_kws:
        print(f"FAIL: Unmapped keywords exist: {unmapped_kws}")
        sys.exit(1)
        
    # Verify weight format is one of [1.0, 0.8, 0.5]
    for m in final_mappings:
        if m["weight"] not in [1.0, 0.8, 0.5]:
            print(f"FAIL: Tag mapping has invalid weight: {m}")
            sys.exit(1)
            
    print("✅ PASS: 100% of keywords and tags are mapped with correct weight categories.")
    print(f"Total mappings count (cặp tag - từ khoá): {len(final_mappings)}")
    
    # Save to CSV
    fields = ["map_id", "tag_id", "keyword", "topic", "weight"]
    with open(map_csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for idx, m in enumerate(final_mappings, 1):
            writer.writerow({
                "map_id": idx,
                "tag_id": m["tag_id"],
                "keyword": m["keyword"],
                "topic": m["topic"],
                "weight": m["weight"]
            })
            
    print(f"SUCCESS: Wrote maps database to {map_csv_path}")
    
    # 4. Implement Bidirectional queries for validation check
    def get_tags_by_keyword(kw):
        results = []
        for m in final_mappings:
            if m["keyword"] == kw:
                results.append((m["tag_id"], m["weight"]))
        # Sort by weight descending
        results = sorted(results, key=lambda x: x[1], reverse=True)
        return [r[0] for r in results]

    def get_keywords_by_tag(tid):
        results = []
        for m in final_mappings:
            if m["tag_id"] == tid:
                results.append((m["keyword"], m["weight"]))
        # Sort by weight descending
        results = sorted(results, key=lambda x: x[1], reverse=True)
        return [r[0] for r in results]
        
    print("\n--- Bidirectional Testing Examples ---")
    
    # Test case 1: từ khoá 'quà 20/10'
    kw_test = "quà 20/10"
    tags_res = get_tags_by_keyword(kw_test)
    print(f"Thử tra: {kw_test}  ->  {', '.join(tags_res) if tags_res else 'None'}")
    
    # Test case 2: tag 'qua-tang-phu-nu'
    tag_test = "qua-tang-phu-nu"
    kws_res = get_keywords_by_tag(tag_test)
    print(f"Thử tra: {tag_test}  ->  {', '.join(kws_res) if kws_res else 'None'}")
    
    # Test case 3: từ khoá 'áo thun'
    kw_test3 = "áo thun"
    tags_res3 = get_tags_by_keyword(kw_test3)
    print(f"Thử tra: {kw_test3}  ->  {', '.join(tags_res3) if tags_res3 else 'None'}")
    
    # Test case 4: tag 'ao-oversize'
    tag_test4 = "ao-oversize"
    kws_res4 = get_keywords_by_tag(tag_test4)
    print(f"Thử tra: {tag_test4}  ->  {', '.join(kws_res4) if kws_res4 else 'None'}")
    
    # Test case 5: từ khoá 'quà tặng'
    kw_test5 = "quà tặng"
    tags_res5 = get_tags_by_keyword(kw_test5)
    print(f"Thử tra: {kw_test5}  ->  {', '.join(tags_res5) if tags_res5 else 'None'}")

if __name__ == "__main__":
    main()
