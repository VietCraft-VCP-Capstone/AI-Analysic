import re
import csv
import sys
import os

# Define the 11 Level 1 Categories
LEVEL1 = [
    {"category_id": "apparel", "parent_id": "", "name_vi": "Áo", "slug": "ao", "level": 1},
    {"category_id": "bottoms", "parent_id": "", "name_vi": "Quần váy", "slug": "quan-vay", "level": 1},
    {"category_id": "drinkware", "parent_id": "", "name_vi": "Cốc ly bình", "slug": "coc-ly-binh", "level": 1},
    {"category_id": "wallart", "parent_id": "", "name_vi": "Tranh trang trí", "slug": "tranh-trang-tri", "level": 1},
    {"category_id": "bag", "parent_id": "", "name_vi": "Túi", "slug": "tui", "level": 1},
    {"category_id": "tech", "parent_id": "", "name_vi": "Phụ kiện công nghệ", "slug": "phu-kien-cong-nghe", "level": 1},
    {"category_id": "accessory", "parent_id": "", "name_vi": "Phụ kiện cá nhân", "slug": "phu-kien-ca-nhan", "level": 1},
    {"category_id": "home", "parent_id": "", "name_vi": "Nhà cửa", "slug": "nha-cua", "level": 1},
    {"category_id": "stationery", "parent_id": "", "name_vi": "Văn phòng phẩm", "slug": "van-phong-pham", "level": 1},
    {"category_id": "pet", "parent_id": "", "name_vi": "Thú cưng", "slug": "thu-cung", "level": 1},
    {"category_id": "sport", "parent_id": "", "name_vi": "Thể thao", "slug": "the-thao", "level": 1},
]

# Define 21 Topics
TOPICS = [
    "tet", "womens_day", "teachers_day", "christmas", "valentine", 
    "gift", "wedding", "housewarming", "friendship", "travel", 
    "anime", "kpop", "streetwear", "vintage", "sport", 
    "decor", "couple", "group", "school", "family", "evergreen"
]

# Exact 74 Level 2 categories mapping
CUSTOM_NAMES = {
    # 1. apparel (15)
    "apparel.tet": ("Áo Tết", "ao-tet"),
    "apparel.womens_day": ("Áo ngày Phụ nữ", "ao-ngay-phu-nu"),
    "apparel.teachers_day": ("Áo ngày Nhà giáo", "ao-ngay-nha-giao"),
    "apparel.christmas": ("Áo Giáng sinh", "ao-giang-sinh"),
    "apparel.valentine": ("Áo Valentine", "ao-valentine"),
    "apparel.anime": ("Áo Anime", "ao-anime"),
    "apparel.kpop": ("Áo Kpop", "ao-kpop"),
    "apparel.streetwear": ("Áo Streetwear", "ao-streetwear"),
    "apparel.vintage": ("Áo Vintage", "ao-vintage"),
    "apparel.sport": ("Áo thể thao", "ao-the-thao"),
    "apparel.couple": ("Áo cặp đôi", "ao-cap-doi"),
    "apparel.group": ("Áo nhóm", "ao-nhom"),
    "apparel.school": ("Áo lớp học", "ao-lop-hoc"),
    "apparel.family": ("Áo gia đình", "ao-gia-dinh"),
    "apparel.evergreen": ("Áo thun phổ thông", "ao-thun-pho-thong"),

    # 2. bottoms (5)
    "bottoms.streetwear": ("Quần jogger streetwear", "quan-jogger-streetwear"),
    "bottoms.sport": ("Quần short thể thao", "quan-short-the-thao"),
    "bottoms.evergreen": ("Quần váy phổ thông", "quan-vay-pho-thong"),
    "bottoms.anime": ("Quần váy Anime", "quan-vay-anime"),
    "bottoms.kpop": ("Quần váy Kpop", "quan-vay-kpop"),

    # 3. drinkware (9)
    "drinkware.tet": ("Cốc sứ đón Tết", "coc-su-don-tet"),
    "drinkware.womens_day": ("Cốc quà ngày Phụ nữ", "coc-qua-ngay-phu-nu"),
    "drinkware.teachers_day": ("Cốc quà tặng thầy cô", "coc-qua-thay-co"),
    "drinkware.christmas": ("Cốc sứ Giáng sinh", "coc-su-giang-sinh"),
    "drinkware.valentine": ("Cốc đôi Valentine", "coc-doi-valentine"),
    "drinkware.gift": ("Ly cốc quà tặng", "ly-coc-qua-tang"),
    "drinkware.housewarming": ("Cốc quà tân gia", "coc-qua-tan-gia"),
    "drinkware.anime": ("Cốc sứ Anime", "coc-su-anime"),
    "drinkware.evergreen": ("Cốc ly phổ thông", "coc-ly-pho-thong"),

    # 4. wallart (8)
    "wallart.tet": ("Tranh trang trí Tết", "tranh-trang-tri-tet"),
    "wallart.christmas": ("Tranh treo Giáng sinh", "tranh-treo-giang-sinh"),
    "wallart.housewarming": ("Tranh gỗ quà tân gia", "tranh-go-qua-tan-gia"),
    "wallart.anime": ("Tranh Canvas Anime", "tranh-canvas-anime"),
    "wallart.kpop": ("Poster trang trí Kpop", "poster-trang-tri-kpop"),
    "wallart.vintage": ("Tranh Vintage cổ điển", "tranh-vintage-co-dien"),
    "wallart.decor": ("Tranh Canvas decor trang trí", "tranh-canvas-decor-trang-tri"),
    "wallart.evergreen": ("Tranh trang trí phổ thông", "tranh-trang-tri-pho-thong"),

    # 5. bag (6)
    "bag.travel": ("Balo túi xách du lịch", "balo-tui-xach-du-lich"),
    "bag.anime": ("Túi tote Anime", "tui-tote-anime"),
    "bag.kpop": ("Túi Kpop thần tượng", "tui-kpop-than-tuong"),
    "bag.streetwear": ("Balo túi streetwear", "balo-tui-streetwear"),
    "bag.vintage": ("Túi canvas vintage", "tui-canvas-vintage"),
    "bag.evergreen": ("Túi tote phổ thông", "tui-tote-pho-thong"),

    # 6. tech (5)
    "tech.anime": ("Ốp lưng Anime", "op-lung-anime"),
    "tech.kpop": ("Ốp lưng Kpop", "op-lung-kpop"),
    "tech.streetwear": ("Phụ kiện tech streetwear", "phu-kien-tech-streetwear"),
    "tech.decor": ("Deskmat trang trí bàn làm việc", "deskmat-trang-tri-ban-lam-viec"),
    "tech.evergreen": ("Bàn di chuột phổ thông", "ban-di-chuot-pho-thong"),

    # 7. accessory (9)
    "accessory.tet": ("Móc khóa Tết", "moc-khoa-tet"),
    "accessory.christmas": ("Nón len Giáng sinh", "non-len-giang-sinh"),
    "accessory.valentine": ("Móc khóa đôi Valentine", "moc-khoa-doi-valentine"),
    "accessory.travel": ("Kính râm du lịch", "kinh-ram-du-lich"),
    "accessory.anime": ("Móc khóa Anime", "moc-khoa-anime"),
    "accessory.streetwear": ("Nón snapback streetwear", "non-snapback-streetwear"),
    "accessory.friendship": ("Móc khóa tình bạn", "moc-khoa-tinh-ban"),
    "accessory.couple": ("Móc khóa đôi cặp đôi", "moc-khoa-doi-cap-doi"),
    "accessory.evergreen": ("Móc khóa phổ thông", "moc-khoa-pho-thong"),

    # 8. home (6)
    "home.tet": ("Gối trang trí Tết", "goi-trang-tri-tet"),
    "home.christmas": ("Chăn Giáng sinh ấm áp", "chan-giang-sinh-am-ap"),
    "home.wedding": ("Khăn tắm quà cưới", "khan-tam-qua-cuoi"),
    "home.housewarming": ("Thảm trang trí tân gia", "tham-trang-tri-tan-gia"),
    "home.decor": ("Thảm trải sàn trang trí", "tham-trai-san-trang-tri"),
    "home.evergreen": ("Nến thơm phổ thông", "nen-thom-pho-thong"),

    # 9. stationery (5)
    "stationery.teachers_day": ("Sổ ghi quà tặng thầy cô 20/11", "so-ghi-qua-tang-thay-co-20-11"),
    "stationery.gift": ("Sổ tay lò xo quà tặng", "so-tay-lo-xo-qua-tang"),
    "stationery.anime": ("Sổ tay Anime", "so-tay-anime"),
    "stationery.school": ("Sổ tay lớp học học sinh", "so-tay-lop-hoc-hoc-sinh"),
    "stationery.evergreen": ("Sổ tay phổ thông", "so-tay-pho-thong"),

    # 10. pet (3)
    "pet.tet": ("Áo thú cưng đón Tết", "ao-thu-cung-don-tet"),
    "pet.christmas": ("Vòng cổ thú cưng Noel", "vong-co-thu-cung-noel"),
    "pet.evergreen": ("Bát ăn thú cưng phổ thông", "bat-an-thu-cung-pho-thong"),

    # 11. sport (3)
    "sport.sport": ("Thảm tập yoga chuyên dụng", "tham-tap-yoga-chuyen-dung"),
    "sport.evergreen": ("Khăn lau thể thao phổ thông", "khan-lau-the-thao-pho-thong"),
    "sport.travel": ("Bình nước dã ngoại du lịch", "binh-nuoc-da-ngoai-du-lich"),
}

def clean_vietnamese_text(text):
    """Normalize Vietnamese text to simple slug format."""
    text = text.lower()
    replace_dict = {
        '[áàảãạăắằẳẵặâấầẩẫậ]': 'a',
        '[éèẻẽẹêếềểễệ]': 'e',
        '[íìỉĩị]': 'i',
        '[óòỏõọôốồổỗộơớờởỡợ]': 'o',
        '[úùủũụưứừửữự]': 'u',
        '[ýỳỷỹỵ]': 'y',
        'đ': 'd',
        '[^a-z0-9 ]': ' ',
    }
    for regex_str, replacement in replace_dict.items():
        text = re.sub(regex_str, replacement, text)
    text = re.sub(r'\s+', '-', text.strip())
    text = re.sub(r'^-+|-+$', '', text)
    return text

def test_gen():
    db = []
    
    # Add Level 1
    for item in LEVEL1:
        db.append(item)
        
    # Compile Level 2
    l2_count = 0
    assigned_topics = set()
    
    for key, (name, slug) in CUSTOM_NAMES.items():
        p_id, t_id = key.split(".")
        if t_id not in TOPICS:
            print(f"Warning: Topic '{t_id}' in CUSTOM_NAMES is not in official TOPICS list.")
            
        p_exists = any(item["category_id"] == p_id for item in LEVEL1)
        if not p_exists:
            print(f"Error: Parent ID '{p_id}' for '{key}' does not exist in LEVEL1.")
            
        db.append({
            "category_id": key,
            "parent_id": p_id,
            "name_vi": name,
            "slug": slug,
            "level": 2
        })
        l2_count += 1
        assigned_topics.add(t_id)
        
    print(f"\nConfiguration summary:")
    print(f"Level 1: {len(LEVEL1)} rows")
    print(f"Level 2: {l2_count} rows")
    print(f"Total: {len(LEVEL1) + l2_count} rows")
    
    # Check criteria
    all_l1_ok = (len(LEVEL1) == 11)
    all_l2_ok = (l2_count == 74)
    total_ok = (len(db) == 85)
    
    # Check unused topics
    unused_topics = set(TOPICS) - assigned_topics
    
    # Check duplicate slugs
    slugs = [item["slug"] for item in db]
    duplicate_slugs = [s for s in set(slugs) if slugs.count(s) > 1]
    
    # Check parent existence for all level 2
    orphans = [item for item in db if item["level"] == 2 and not any(l1["category_id"] == item["parent_id"] for l1 in LEVEL1)]
    
    bad_slugs = []
    for item in db:
        valid = bool(re.match(r'^[a-z0-9-]+$', item["slug"]))
        if not valid:
            bad_slugs.append((item["name_vi"], item["slug"]))

    print("\nVALDIATION RESULTS:")
    print(f"1. Level 1 Categories count == 11? {'Yes' if all_l1_ok else 'No (' + str(len(LEVEL1)) + ')'}")
    print(f"2. Level 2 Categories count == 74? {'Yes' if all_l2_ok else 'No (' + str(l2_count) + ')'}")
    print(f"3. Total Categories count == 85? {'Yes' if total_ok else 'No (' + str(len(db)) + ')'}")
    print(f"4. Unused topics count == 0? {'Yes' if len(unused_topics) == 0 else 'No (' + str(unused_topics) + ')'}")
    print(f"5. Duplicate slugs count == 0? {'Yes' if len(duplicate_slugs) == 0 else 'No (' + str(duplicate_slugs) + ')'}")
    print(f"6. Orphans count == 0? {'Yes' if len(orphans) == 0 else 'No'}")
    print(f"7. Bad format slugs count == 0? {'Yes' if len(bad_slugs) == 0 else 'No'}")
    
    # Output to categories.csv in the same folder as the script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(script_dir, "categories.csv")
    
    header = ["category_id", "parent_id", "name_vi", "slug", "level"]
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        writer.writeheader()
        for row in db:
            writer.writerow(row)
    print(f"\nSaved categories.csv successfully to {csv_path}!")
    
    if not (all_l1_ok and all_l2_ok and total_ok and len(unused_topics) == 0 and len(duplicate_slugs) == 0 and len(orphans) == 0 and len(bad_slugs) == 0):
        print("CRITICAL VALIDATION FAILED!")
        sys.exit(1)
    else:
        print("ALL VALIDATION PASSED!")

if __name__ == "__main__":
    test_gen()
