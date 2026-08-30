import os
import sys
import json
import random
import datetime
from pathlib import Path
import pandas as pd
import numpy as np

# Set random seed for reproducibility
random.seed(42)
np.random.seed(42)

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
SAMPLES_DIR = DATA_DIR / "seed_out" / "samples"

# Target date bounds
NOW_DATE = datetime.datetime(2026, 8, 30, 17, 48, 41, tzinfo=datetime.timezone.utc)
START_DATE = datetime.datetime(2025, 3, 1, 0, 0, 0, tzinfo=datetime.timezone.utc)


def ensure_directories():
    """Ensure data and samples output directories exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)


def slugify(text: str) -> str:
    """Convert text to URL-friendly slug."""
    import re
    import unicodedata
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('utf-8').lower()
    text = re.sub(r'[^a-z0-9]+', '-', text).strip('-')
    return text


# ==============================================================================
# TASK 1: Generate Provinces (63 provinces, 3 regions, utf-8-sig)
# ==============================================================================
PROVINCES_DATA = [
    # Miền Bắc (25)
    {"province_code": "01", "name_vi": "Thành phố Hà Nội", "region": "bac"},
    {"province_code": "02", "name_vi": "Tỉnh Hà Giang", "region": "bac"},
    {"province_code": "04", "name_vi": "Tỉnh Cao Bằng", "region": "bac"},
    {"province_code": "06", "name_vi": "Tỉnh Bắc Kạn", "region": "bac"},
    {"province_code": "08", "name_vi": "Tỉnh Tuyên Quang", "region": "bac"},
    {"province_code": "10", "name_vi": "Tỉnh Lào Cai", "region": "bac"},
    {"province_code": "11", "name_vi": "Tỉnh Điện Biên", "region": "bac"},
    {"province_code": "12", "name_vi": "Tỉnh Lai Châu", "region": "bac"},
    {"province_code": "14", "name_vi": "Tỉnh Sơn La", "region": "bac"},
    {"province_code": "15", "name_vi": "Tỉnh Yên Bái", "region": "bac"},
    {"province_code": "17", "name_vi": "Tỉnh Hòa Bình", "region": "bac"},
    {"province_code": "19", "name_vi": "Tỉnh Thái Nguyên", "region": "bac"},
    {"province_code": "20", "name_vi": "Tỉnh Lạng Sơn", "region": "bac"},
    {"province_code": "22", "name_vi": "Tỉnh Quảng Ninh", "region": "bac"},
    {"province_code": "24", "name_vi": "Tỉnh Bắc Giang", "region": "bac"},
    {"province_code": "25", "name_vi": "Tỉnh Phú Thọ", "region": "bac"},
    {"province_code": "26", "name_vi": "Tỉnh Vĩnh Phúc", "region": "bac"},
    {"province_code": "27", "name_vi": "Tỉnh Bắc Ninh", "region": "bac"},
    {"province_code": "30", "name_vi": "Tỉnh Hải Dương", "region": "bac"},
    {"province_code": "31", "name_vi": "Thành phố Hải Phòng", "region": "bac"},
    {"province_code": "33", "name_vi": "Tỉnh Hưng Yên", "region": "bac"},
    {"province_code": "34", "name_vi": "Tỉnh Thái Bình", "region": "bac"},
    {"province_code": "35", "name_vi": "Tỉnh Hà Nam", "region": "bac"},
    {"province_code": "36", "name_vi": "Tỉnh Nam Định", "region": "bac"},
    {"province_code": "37", "name_vi": "Tỉnh Ninh Bình", "region": "bac"},

    # Miền Trung (19)
    {"province_code": "38", "name_vi": "Tỉnh Thanh Hóa", "region": "trung"},
    {"province_code": "40", "name_vi": "Tỉnh Nghệ An", "region": "trung"},
    {"province_code": "42", "name_vi": "Tỉnh Hà Tĩnh", "region": "trung"},
    {"province_code": "44", "name_vi": "Tỉnh Quảng Bình", "region": "trung"},
    {"province_code": "45", "name_vi": "Tỉnh Quảng Trị", "region": "trung"},
    {"province_code": "46", "name_vi": "Tỉnh Thừa Thiên Huế", "region": "trung"},
    {"province_code": "48", "name_vi": "Thành phố Đà Nẵng", "region": "trung"},
    {"province_code": "49", "name_vi": "Tỉnh Quảng Nam", "region": "trung"},
    {"province_code": "51", "name_vi": "Tỉnh Quảng Ngãi", "region": "trung"},
    {"province_code": "52", "name_vi": "Tỉnh Bình Định", "region": "trung"},
    {"province_code": "54", "name_vi": "Tỉnh Phú Yên", "region": "trung"},
    {"province_code": "56", "name_vi": "Tỉnh Khánh Hòa", "region": "trung"},
    {"province_code": "58", "name_vi": "Tỉnh Ninh Thuận", "region": "trung"},
    {"province_code": "60", "name_vi": "Tỉnh Bình Thuận", "region": "trung"},
    {"province_code": "62", "name_vi": "Tỉnh Kon Tum", "region": "trung"},
    {"province_code": "64", "name_vi": "Tỉnh Gia Lai", "region": "trung"},
    {"province_code": "66", "name_vi": "Tỉnh Đắk Lắk", "region": "trung"},
    {"province_code": "67", "name_vi": "Tỉnh Đắk Nông", "region": "trung"},
    {"province_code": "68", "name_vi": "Tỉnh Lâm Đồng", "region": "trung"},

    # Miền Nam (19)
    {"province_code": "70", "name_vi": "Tỉnh Bình Phước", "region": "nam"},
    {"province_code": "72", "name_vi": "Tỉnh Tây Ninh", "region": "nam"},
    {"province_code": "74", "name_vi": "Tỉnh Bình Dương", "region": "nam"},
    {"province_code": "75", "name_vi": "Tỉnh Đồng Nai", "region": "nam"},
    {"province_code": "77", "name_vi": "Tỉnh Bà Rịa - Vũng Tàu", "region": "nam"},
    {"province_code": "79", "name_vi": "Thành phố Hồ Chí Minh", "region": "nam"},
    {"province_code": "80", "name_vi": "Tỉnh Long An", "region": "nam"},
    {"province_code": "82", "name_vi": "Tỉnh Tiền Giang", "region": "nam"},
    {"province_code": "83", "name_vi": "Tỉnh Bến Tre", "region": "nam"},
    {"province_code": "84", "name_vi": "Tỉnh Trà Vinh", "region": "nam"},
    {"province_code": "86", "name_vi": "Tỉnh Vĩnh Long", "region": "nam"},
    {"province_code": "87", "name_vi": "Tỉnh Đồng Tháp", "region": "nam"},
    {"province_code": "89", "name_vi": "Tỉnh An Giang", "region": "nam"},
    {"province_code": "91", "name_vi": "Tỉnh Kiên Giang", "region": "nam"},
    {"province_code": "92", "name_vi": "Thành phố Cần Thơ", "region": "nam"},
    {"province_code": "93", "name_vi": "Tỉnh Hậu Giang", "region": "nam"},
    {"province_code": "94", "name_vi": "Tỉnh Sóc Trăng", "region": "nam"},
    {"province_code": "95", "name_vi": "Tỉnh Bạc Liêu", "region": "nam"},
    {"province_code": "96", "name_vi": "Tỉnh Cà Mau", "region": "nam"},
]


def generate_provinces() -> pd.DataFrame:
    file_path = DATA_DIR / "provinces.csv"
    if file_path.exists() and file_path.stat().st_size > 0:
        print(f"[EXISTS] {file_path.name} already exists. Loading data...")
        df = pd.read_csv(file_path, dtype={'province_code': str}, encoding='utf-8-sig')
        return df

    print(f"[GENERATE] Creating Task 1: {file_path.name} (63 provinces)...")
    df = pd.DataFrame(PROVINCES_DATA)
    df.to_csv(file_path, index=False, encoding='utf-8-sig')
    return df


# ==============================================================================
# TASK 2: Generate Shops (80 shops: 5 large, 20 medium, 55 small; 3 suspended)
# ==============================================================================
SHOP_NAME_PREFIXES = [
    "Gốm Sứ", "Mây Tre Đan", "Thêu Tay", "Lụa Vóc", "Sơn Mài", "Đồ Gỗ", "Trầm Hương",
    "Nón Lá", "Khảm Trai", "Tranh Dân Gian", "Kim Hoàn", "Đồ Da", "Cói Xoan", "Đất Nung",
    "Ngọc Bích", "Hoa Khô", "Nến Thơm", "Họa Tiết Thổ Cẩm", "Đá Mỹ Nghệ", "Tre Xanh"
]

SHOP_NAME_SUFFIXES = [
    "Tâm Việt", "Đồng Kỵ", "Bát Tràng", "Hà Đông", "Hội An", "Đà Lạt", "Phú Vinh",
    "Phước Kiều", "Kim Bồng", "Vạn Phúc", "Đại Bái", "Đông Hồ", "Bình Dương", "Sài Gòn",
    "Thăng Long", "Cố Đô", "Việt Heritage", "Artisan Studio", "Craft Workshop", "Mộc An"
]

IMAGE_PLACEHOLDERS = [
    "https://images.unsplash.com/photo-1578749556568-bc2c40e68b61?auto=format&fit=crop&w=600&q=80",
    "https://images.unsplash.com/photo-1565193566173-7a0ee3dbe261?auto=format&fit=crop&w=600&q=80",
    "https://images.unsplash.com/photo-1606744888344-493238951221?auto=format&fit=crop&w=600&q=80",
    "https://images.unsplash.com/photo-1513519245088-0e12902e5a38?auto=format&fit=crop&w=600&q=80",
    "https://images.unsplash.com/photo-1579783900882-c0d3dad7b119?auto=format&fit=crop&w=600&q=80",
    "https://images.unsplash.com/photo-1610701596007-11502861dcfa?auto=format&fit=crop&w=600&q=80",
]


def generate_shops(provinces_df: pd.DataFrame) -> pd.DataFrame:
    file_path = DATA_DIR / "shops.csv"
    if file_path.exists() and file_path.stat().st_size > 0:
        print(f"[EXISTS] {file_path.name} already exists. Loading data...")
        df = pd.read_csv(file_path, encoding='utf-8-sig')
        return df

    print(f"[GENERATE] Creating Task 2: {file_path.name} (80 shops)...")
    
    # Tier breakdown: 5 large, 20 medium, 55 small
    tiers = ['large'] * 5 + ['medium'] * 20 + ['small'] * 55
    random.shuffle(tiers)

    # Status breakdown: 3 suspended, 77 active
    statuses = ['suspended'] * 3 + ['active'] * 77
    random.shuffle(statuses)

    # Distribute created_at evenly across 18 months (March 2025 - August 2026)
    total_seconds = int((NOW_DATE - START_DATE).total_seconds())
    time_step = total_seconds / 80

    province_codes = provinces_df['province_code'].tolist()
    # Give higher weight to major craft hubs
    weights = [3.0 if code in ['01', '79', '48', '46', '49', '74', '27'] else 1.0 for code in province_codes]
    weight_sum = sum(weights)
    prob_weights = [w / weight_sum for w in weights]

    shops = []
    used_names = set()

    for i in range(80):
        shop_id = f"SHOP_{i+1:03d}"
        
        # Name generation
        while True:
            pfx = random.choice(SHOP_NAME_PREFIXES)
            sfx = random.choice(SHOP_NAME_SUFFIXES)
            name = f"{pfx} {sfx}"
            if i > 40 and random.random() > 0.5:
                name += f" {i+1}"
            if name not in used_names:
                used_names.add(name)
                break
        
        slug = f"{slugify(name)}-{shop_id.lower()}"
        description = f"Xưởng sản xuất và phân phối sản phẩm {name} chất lượng cao, đậm đà bản sắc thủ công truyền thống Việt Nam."
        logo_url = random.choice(IMAGE_PLACEHOLDERS)
        banner_url = random.choice(IMAGE_PLACEHOLDERS)
        prov_code = np.random.choice(province_codes, p=prob_weights)
        
        # created_at timestamp
        created_dt = START_DATE + datetime.timedelta(seconds=int(i * time_step + random.randint(0, int(time_step // 2))))
        if created_dt > NOW_DATE:
            created_dt = NOW_DATE - datetime.timedelta(days=random.randint(1, 10))
        created_at_str = created_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        tier = tiers[i]
        status = statuses[i]

        if tier == 'large':
            response_time = random.randint(5, 15)
            rating = round(random.uniform(4.5, 5.0), 2)
        elif tier == 'medium':
            response_time = random.randint(10, 30)
            rating = round(random.uniform(4.2, 4.8), 2)
        else:
            response_time = random.randint(20, 120)
            rating = round(random.uniform(4.0, 4.7), 2)

        if status == 'suspended':
            rating = round(random.uniform(3.5, 4.2), 2)

        return_policies = [
            "Đổi trả miễn phí trong 7 ngày nếu lỗi nhà sản xuất",
            "Hỗ trợ đổi sản phẩm trong 15 ngày với tem nguyên vẹn",
            "Đổi trả trong 30 ngày đối với hàng lỗi do vận chuyển",
            "Chính sách bảo hành 12 tháng, đổi trả trong 7 ngày"
        ]
        return_policy = random.choice(return_policies)

        shops.append({
            "shop_id": shop_id,
            "name": name,
            "slug": slug,
            "description": description,
            "logo_url": logo_url,
            "banner_url": banner_url,
            "province_code": str(prov_code),
            "created_at": created_at_str,
            "return_policy": return_policy,
            "response_time_minutes": response_time,
            "rating_avg": rating,
            "status": status,
            "tier": tier
        })

    df = pd.DataFrame(shops)
    df.to_csv(file_path, index=False, encoding='utf-8-sig')
    return df


# ==============================================================================
# TASK 3, 4, 5: Catalog, Price Bands, and Listings (5,000 items)
# ==============================================================================
CRAFT_GROUPS = [
    ("Gốm Sứ", "Gốm Sứ Bát Tràng, Chu Đậu, Phù Lãng", 15, 50000, 2000000),
    ("Mây Tre Đan", "Mây Tre Đan Phú Vinh, Bao La", 15, 30000, 1500000),
    ("Thêu Tay", "Thêu Tay Đà Lạt, Quất Động", 15, 80000, 3000000),
    ("Sơn Mài", "Sơn Mài Tương Bình Hiệp, Hạ Thái", 15, 120000, 5000000),
    ("Đồ Gỗ", "Mỹ Nghệ Đồng Kỵ, Kim Bồng", 15, 150000, 8000000),
    ("Lụa Tơ Tằm", "Lụa Hà Đông, Bảo Lộc", 12, 100000, 4000000),
    ("Tranh Dân Gian", "Tranh Đông Hồ, Hàng Trống, Kim Hoàng", 12, 40000, 2500000),
    ("Trầm Hương", "Trầm Hương Xứ Quảng, Khánh Hòa", 12, 200000, 10000000),
    ("Đồ Da Thủ Công", "Ví, Túi Da Khâu Tay Studio", 12, 90000, 3500000),
    ("Kim Hoàn & Bạc", "Trang Sức Bạc Định Công, Đồng Phước Kiều", 15, 70000, 4500000),
]


def ensure_catalog_and_price_bands() -> (pd.DataFrame, pd.DataFrame):
    cat_file = DATA_DIR / "catalog.csv"
    pb_file = DATA_DIR / "price_bands.csv"

    if not cat_file.exists() or cat_file.stat().st_size == 0:
        print(f"[GENERATE] Creating Mock Catalog (138 categories)...")
        cats = []
        cat_idx = 1
        for group_name, group_desc, count, c_min, c_max in CRAFT_GROUPS:
            for k in range(count):
                cat_id = f"CAT_{cat_idx:03d}"
                name = f"{group_name} - Dòng Sản Phẩm {k+1}"
                cats.append({
                    "category_id": cat_id,
                    "category_name": name,
                    "parent_category": group_name,
                    "description": f"Sản phẩm {group_desc} loại {k+1}"
                })
                cat_idx += 1
        df_cat = pd.DataFrame(cats)
        df_cat.to_csv(cat_file, index=False, encoding='utf-8-sig')
    else:
        df_cat = pd.read_csv(cat_file, encoding='utf-8-sig')

    if not pb_file.exists() or pb_file.stat().st_size == 0:
        print(f"[GENERATE] Creating Mock Price Bands...")
        pbs = []
        for idx, row in df_cat.iterrows():
            c_id = row['category_id']
            # Default bounds if not matched
            c_min, c_max = 50000, 2000000
            for g_name, _, _, g_min, g_max in CRAFT_GROUPS:
                if g_name in row.get('parent_category', ''):
                    c_min, c_max = g_min, g_max
                    break
            pbs.append({
                "category_id": c_id,
                "cost_min": c_min,
                "cost_max": c_max,
                "target_margin_min": 2.0,
                "target_margin_max": 3.0
            })
        df_pb = pd.DataFrame(pbs)
        df_pb.to_csv(pb_file, index=False, encoding='utf-8-sig')
    else:
        df_pb = pd.read_csv(pb_file, encoding='utf-8-sig')

    return df_cat, df_pb


PRODUCT_NAME_TEMPLATES = [
    "Bình Hoa {cat} Thủ Công Mỹ Nghệ",
    "Tượng Wood/Gốm {cat} Trang Trí Cao Cấp",
    "Bộ Sản Phẩm {cat} Khảm Họa Tiết Truyền Thống",
    "Hộp Đựng {cat} Chạm Khắc Tinh Xảo",
    "Khay Trà {cat} Đồ Mỹ Nghệ Độc Bản",
    "Tranh Treo Tường {cat} Nghệ Thuật",
    "Đèn Trang Trí {cat} Phong Cách Vintage",
    "Bộ Ly/Tách {cat} Men Cổ Thủ Công",
    "Túi/Ví {cat} May Tay Tinh Tế",
    "Vòng Tay/Trang Sức {cat} Đính Đá Tự Nhiên",

    "Mô Hình {cat} Đồ Chơi Mỹ Nghệ Dân Gian",
    "Đĩa Biểu Tượng {cat} Quà Tặng Đối Ngoại",
    "Thảm/Khăn {cat} Họa Tiết Thổ Cẩm",
    "Ống Trầm/Đốt Trầm {cat} Phong Thủy",
    "Bộ Bàn Ghế {cat} Mini Trang Trí Table"
]

PRODUCT_IMAGES_POOL = [
    "https://images.unsplash.com/photo-1578749556568-bc2c40e68b61?auto=format&fit=crop&w=800&q=80",
    "https://images.unsplash.com/photo-1565193566173-7a0ee3dbe261?auto=format&fit=crop&w=800&q=80",
    "https://images.unsplash.com/photo-1606744888344-493238951221?auto=format&fit=crop&w=800&q=80",
    "https://images.unsplash.com/photo-1513519245088-0e12902e5a38?auto=format&fit=crop&w=800&q=80",
    "https://images.unsplash.com/photo-1579783900882-c0d3dad7b119?auto=format&fit=crop&w=800&q=80",
    "https://images.unsplash.com/photo-1610701596007-11502861dcfa?auto=format&fit=crop&w=800&q=80",
    "https://images.unsplash.com/photo-1584589167171-541ce45f1eea?auto=format&fit=crop&w=800&q=80",
    "https://images.unsplash.com/photo-1513151233558-d860c5398176?auto=format&fit=crop&w=800&q=80",
    "https://images.unsplash.com/photo-1526304640581-d334cdbbf45e?auto=format&fit=crop&w=800&q=80",
    "https://images.unsplash.com/photo-1544816155-12df9643f363?auto=format&fit=crop&w=800&q=80",
]


def generate_listings(shops_df: pd.DataFrame, catalog_df: pd.DataFrame, price_bands_df: pd.DataFrame) -> pd.DataFrame:
    file_path = DATA_DIR / "listings.csv"
    if file_path.exists() and file_path.stat().st_size > 0:
        print(f"[EXISTS] {file_path.name} already exists. Loading data...")
        df = pd.read_csv(file_path, encoding='utf-8-sig')
        # Assert safety check on existing data
        assert (df['selling_price'] >= 1.6 * df['cost_price']).all(), "Selling price constraint failed!"
        return df

    print(f"[GENERATE] Creating Tasks 3-5: {file_path.name} (5,000 listings)...")

    # Map categories to price bands
    pb_map = {}
    for idx, row in price_bands_df.iterrows():
        pb_map[row['category_id']] = (row['cost_min'], row['cost_max'])

    # Map shop created_at
    shops_info = []
    for idx, row in shops_df.iterrows():
        dt = datetime.datetime.strptime(row['created_at'], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
        shops_info.append((row['shop_id'], row['province_code'], dt))

    categories = catalog_df[['category_id', 'category_name']].to_dict('records')
    num_cats = len(categories)  # 138

    # 1. Allocate at least 20 listings to each category (138 * 20 = 2760)
    # 2. Remaining 2240 distributed among categories
    remaining_slots = 5000 - (num_cats * 20)  # 2240
    extra_allocations = np.random.multinomial(remaining_slots, [1.0 / num_cats] * num_cats)

    cat_listing_counts = [20 + extra_allocations[i] for i in range(num_cats)]

    # Tier breakdown: 500 hot, 1500 medium, 3000 tail
    tiers = ['hot'] * 500 + ['medium'] * 1500 + ['tail'] * 3000
    random.shuffle(tiers)

    listings = []
    listing_counter = 1

    for cat_idx, cat in enumerate(categories):
        c_id = cat['category_id']
        c_name = cat['category_name']
        c_min, c_max = pb_map.get(c_id, (50000, 2000000))
        count = cat_listing_counts[cat_idx]

        for _ in range(count):
            listing_id = f"PROD_{listing_counter:05d}"
            tier = tiers[listing_counter - 1]
            listing_counter += 1

            # Pick random shop
            shop_id, prov_code, shop_created_dt = random.choice(shops_info)

            # Product created_at between shop_created_dt and NOW_DATE
            sec_delta = int((NOW_DATE - shop_created_dt).total_seconds())
            if sec_delta > 0:
                prod_created_dt = shop_created_dt + datetime.timedelta(seconds=random.randint(0, sec_delta))
            else:
                prod_created_dt = shop_created_dt
            prod_created_str = prod_created_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

            # Name & slug
            tmpl = random.choice(PRODUCT_NAME_TEMPLATES)
            short_cat = c_name.split('-')[0].strip()
            name = tmpl.format(cat=short_cat) + f" #{listing_id}"
            slug = f"{slugify(name)}-{listing_id.lower()}"

            description = f"Sản phẩm {name} được chế tác thủ công tỉ mỉ từ làng nghề truyền thống. Chất liệu tự nhiên, bền đẹp và mang giá trị thẩm mỹ cao."

            # Cost & Selling price calculation
            # Cost price in thousands
            raw_cost = random.randint(int(c_min), int(c_max))
            cost_price = int(round(raw_cost / 1000.0) * 1000)
            if cost_price < 10000:
                cost_price = 10000

            # Multiplier between 2.0 and 3.0
            mult = random.uniform(2.0, 3.0)
            selling_price = int(round((cost_price * mult) / 1000.0) * 1000)

            # Strict Assertion Check
            assert selling_price >= 1.6 * cost_price, f"Selling price {selling_price} < 1.6 * cost {cost_price}"

            # Images: 3 to 8 URLs
            num_imgs = random.randint(3, 8)
            img_list = random.sample(PRODUCT_IMAGES_POOL, num_imgs)
            images_json = json.dumps(img_list, ensure_ascii=False)

            listings.append({
                "listing_id": listing_id,
                "shop_id": shop_id,
                "category_id": c_id,
                "category_name": c_name,
                "name": name,
                "slug": slug,
                "description": description,
                "cost_price": cost_price,
                "selling_price": selling_price,
                "tier": tier,
                "status": "active",
                "images": images_json,
                "created_at": prod_created_str,
                "updated_at": prod_created_str,
                "province_code": str(prov_code)
            })

    df = pd.DataFrame(listings)
    
    # Run assertion on entire dataframe
    assert (df['selling_price'] >= 1.6 * df['cost_price']).all(), "Assertion failed: selling_price >= 1.6 * cost_price"

    df.to_csv(file_path, index=False, encoding='utf-8-sig')
    return df


# ==============================================================================
# TASK 8: Generate Listing Variants (~40,000 variants, ~8/item)
# ==============================================================================
OPTION_TYPES = [
    ("Màu sắc", ["Tự Nhiên", "Mộc", "Cánh Gián", "Đỏ Son", "Xanh Rêu", "Đen Huyền", "Vàng Men"]),
    ("Kích thước", ["Nhỏ (S)", "Vừa (M)", "Lớn (L)", "Đặc Biệt (XL)", "Standard 20cm", "Standard 30cm"]),
    ("Chất liệu", ["Lụa Hà Đông", "Gỗ Hương", "Gỗ Mun", "Gốm Men Hỏa Biến", "Tre Già", "Đồng Thau"]),
    ("Đóng gói", ["Hộp Thường", "Hộp Quà Tặng Miễn Phí", "Hộp Gỗ Bọc Lụa Premium"])
]


def generate_variants(listings_df: pd.DataFrame) -> pd.DataFrame:
    file_path = DATA_DIR / "listing_variants.csv"
    if file_path.exists() and file_path.stat().st_size > 0:
        print(f"[EXISTS] {file_path.name} already exists. Loading data...")
        df = pd.read_csv(file_path, encoding='utf-8-sig')
        assert (df['selling_price'] >= 1.6 * df['cost_price']).all(), "Selling price constraint failed!"
        return df

    print(f"[GENERATE] Creating Task 8: {file_path.name} (~40,000 variants)...")

    variants = []
    variant_counter = 1

    for idx, prod in listings_df.iterrows():
        listing_id = prod['listing_id']
        prod_cost = prod['cost_price']
        prod_created = prod['created_at']

        # Determine variants count per product (average ~8, range 4 to 12)
        v_count = random.randint(4, 12)

        # Select 2 option types
        opt1_name, opt1_vals = random.choice(OPTION_TYPES[:2])
        opt2_name, opt2_vals = random.choice(OPTION_TYPES[2:])

        chosen_combos = []
        for v1 in random.sample(opt1_vals, min(v_count, len(opt1_vals))):
            for v2 in random.sample(opt2_vals, min(2, len(opt2_vals))):
                chosen_combos.append((v1, v2))
                if len(chosen_combos) >= v_count:
                    break
            if len(chosen_combos) >= v_count:
                break

        for combo_idx, (val1, val2) in enumerate(chosen_combos):
            variant_id = f"VAR_{variant_counter:07d}"
            sku = f"SKU-{listing_id}-{combo_idx+1:02d}"
            variant_name = f"{val1} / {val2}"

            attributes_dict = {opt1_name: val1, opt2_name: val2}
            attributes_json = json.dumps(attributes_dict, ensure_ascii=False)

            # Cost adjustment: 0.85 to 1.25 of product cost
            cost_mult = random.uniform(0.85, 1.25)
            v_cost = int(round((prod_cost * cost_mult) / 1000.0) * 1000)
            if v_cost < 10000:
                v_cost = 10000

            # Multiplier between 2.0 and 3.0
            mult = random.uniform(2.0, 3.0)
            v_selling = int(round((v_cost * mult) / 1000.0) * 1000)

            # Assert check
            assert v_selling >= 1.6 * v_cost, f"Variant selling {v_selling} < 1.6 * cost {v_cost}"

            # Stock qty: ~3% out of stock (stock_qty = 0)
            if random.random() < 0.03:
                stock_qty = 0
            else:
                stock_qty = random.randint(1, 100)

            variants.append({
                "variant_id": variant_id,
                "listing_id": listing_id,
                "sku": sku,
                "variant_name": variant_name,
                "attributes": attributes_json,
                "cost_price": v_cost,
                "selling_price": v_selling,
                "stock_qty": stock_qty,
                "created_at": prod_created
            })

            variant_counter += 1

    df = pd.DataFrame(variants)
    
    # DataFrame level assertion
    assert (df['selling_price'] >= 1.6 * df['cost_price']).all(), "Variant price ratio assertion failed!"

    df.to_csv(file_path, index=False, encoding='utf-8-sig')
    return df


# ==============================================================================
# TASK 11: Export Samples (100 rows per CSV)
# ==============================================================================
def export_samples():
    print(f"[GENERATE] Exporting Task 11 sample files to {SAMPLES_DIR}...")
    csv_files = list(DATA_DIR.glob("*.csv"))
    
    for csv_file in csv_files:
        df = pd.read_csv(csv_file, encoding='utf-8-sig')
        sample_df = df.head(100)
        sample_path = SAMPLES_DIR / csv_file.name
        sample_df.to_csv(sample_path, index=False, encoding='utf-8-sig')


# ==============================================================================
# QUALITY CONTROL CHECK (QC Report)
# ==============================================================================
def qc_check():
    print("\n" + "=" * 80)
    print("                        VIETCRAFT SEED DATA QC REPORT")
    print("=" * 80)

    # 1. Provinces
    prov_df = pd.read_csv(DATA_DIR / "provinces.csv", encoding='utf-8-sig', dtype={'province_code': str})
    reg_counts = prov_df['region'].value_counts().to_dict()
    print("1. PROVINCES (provinces.csv):")
    print(f"   - Total Provinces : {len(prov_df)}")
    print(f"   - Region Breakdown: Bac = {reg_counts.get('bac', 0)} | Trung = {reg_counts.get('trung', 0)} | Nam = {reg_counts.get('nam', 0)}")

    # 2. Shops
    shops_df = pd.read_csv(DATA_DIR / "shops.csv", encoding='utf-8-sig')
    tier_counts = shops_df['tier'].value_counts().to_dict()
    status_counts = shops_df['status'].value_counts().to_dict()
    min_date = shops_df['created_at'].min()
    max_date = shops_df['created_at'].max()
    print("\n2. SHOPS (shops.csv):")
    print(f"   - Total Shops     : {len(shops_df)}")
    print(f"   - Tier Breakdown  : Large = {tier_counts.get('large', 0)} | Medium = {tier_counts.get('medium', 0)} | Small = {tier_counts.get('small', 0)}")
    print(f"   - Status          : Active = {status_counts.get('active', 0)} | Suspended = {status_counts.get('suspended', 0)}")
    print(f"   - Created Range   : {min_date} to {max_date}")

    # 3. Listings
    listings_df = pd.read_csv(DATA_DIR / "listings.csv", encoding='utf-8-sig')
    l_tier_counts = listings_df['tier'].value_counts().to_dict()
    cat_counts = listings_df['category_id'].value_counts()
    min_items_per_cat = cat_counts.min()
    max_items_per_cat = cat_counts.max()
    total_cats = len(cat_counts)
    
    price_ratio = (listings_df['selling_price'] / listings_df['cost_price']).min()
    img_counts = listings_df['images'].apply(lambda x: len(json.loads(x)))
    min_imgs, max_imgs = img_counts.min(), img_counts.max()

    print("\n3. PRODUCTS (listings.csv):")
    print(f"   - Total Products  : {len(listings_df)}")
    print(f"   - Tier Breakdown  : Hot = {l_tier_counts.get('hot', 0)} ({l_tier_counts.get('hot', 0)/len(listings_df)*100:.1f}%) | Medium = {l_tier_counts.get('medium', 0)} ({l_tier_counts.get('medium', 0)/len(listings_df)*100:.1f}%) | Tail = {l_tier_counts.get('tail', 0)} ({l_tier_counts.get('tail', 0)/len(listings_df)*100:.1f}%)")
    print(f"   - Category Coverage: {total_cats}/138 categories present (Min per cat = {min_items_per_cat}, Max per cat = {max_items_per_cat})")
    print(f"   - Price Margin    : Min Selling/Cost Ratio = {price_ratio:.2f} (Assertion >= 1.6: {'PASSED' if price_ratio >= 1.6 else 'FAILED'})")
    print(f"   - Image URLs Range: Min = {min_imgs} | Max = {max_imgs}")

    # 4. Variants
    variants_df = pd.read_csv(DATA_DIR / "listing_variants.csv", encoding='utf-8-sig')
    total_vars = len(variants_df)
    avg_vars = total_vars / len(listings_df)
    zero_stock_count = (variants_df['stock_qty'] == 0).sum()
    zero_stock_pct = (zero_stock_count / total_vars) * 100
    v_price_ratio = (variants_df['selling_price'] / variants_df['cost_price']).min()

    print("\n4. VARIANTS (listing_variants.csv):")
    print(f"   - Total Variants  : {total_vars} (Avg {avg_vars:.2f} variants/product)")
    print(f"   - Out of Stock    : {zero_stock_count} variants ({zero_stock_pct:.2f}% with stock_qty = 0)")
    print(f"   - Price Margin    : Min Selling/Cost Ratio = {v_price_ratio:.2f} (Assertion >= 1.6: {'PASSED' if v_price_ratio >= 1.6 else 'FAILED'})")

    # 5. Sample Files Verification
    print("\n5. SAMPLE FILES EXPORTED (seed_out/samples/):")
    sample_files = list(SAMPLES_DIR.glob("*.csv"))
    for sf in sorted(sample_files):
        with open(sf, 'r', encoding='utf-8-sig') as f:
            lines = f.readlines()
        line_count = len(lines)
        print(f"   - {sf.name:<20}: {line_count} lines (Header + {line_count-1} data rows) - {'PASSED' if line_count == 101 else 'CHECK'}")

    print("=" * 80 + "\n")


def main():
    ensure_directories()
    
    # Step 1: Provinces
    provinces_df = generate_provinces()
    
    # Step 2: Shops
    shops_df = generate_shops(provinces_df)
    
    # Step 3, 4, 5: Catalog, Price Bands, Listings
    catalog_df, price_bands_df = ensure_catalog_and_price_bands()
    listings_df = generate_listings(shops_df, catalog_df, price_bands_df)
    
    # Step 8: Listing Variants
    variants_df = generate_variants(listings_df)
    
    # Step 11: Export Samples
    export_samples()
    
    # Run Quality Control Checks
    qc_check()


if __name__ == "__main__":
    main()
