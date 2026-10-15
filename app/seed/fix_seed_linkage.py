"""
fix_seed_linkage.py — Vá liên kết dữ liệu giữa Hưng, Nhi, Hạt.

Không sửa code gốc. Chỉ patch file CSV kết quả.
3 bước:
  1. Thêm category_id vào vc_product_type.csv (Hưng)
  2. Đổi province_code sang mã số trong shops.csv (Hạt)
  3. Khớp product_type_id, category_id, tags trong listings.csv (Hạt)
"""

import csv
import os
import random
import sys
from copy import deepcopy

random.seed(42)  # Kết quả tái lập được

# ─── Đường dẫn ───
BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(BASE)))

HUNG_DIR = os.path.join(ROOT, "SE16-AI", "data", "Hung_TaskAI")
NHI_DIR  = os.path.join(ROOT, "SE16-AI", "data", "Nhi_Bui_Data Collection")
HAT_DIR  = os.path.join(ROOT, "SE16-AI", "data", "Le_Hat_Task_AI")
HIEU_DIR = os.path.join(ROOT, "SE16-AI", "data", "seed_out", "v1")

# ─── Bảng ánh xạ product_group → category_id (level 1 của Nhi) ───
GROUP_TO_CATEGORY = {
    "apparel_top":    "apparel",
    "apparel_bottom": "bottoms",
    "drinkware":      "drinkware",
    "wallart":        "wallart",
    "bag":            "bag",
    "tech":           "tech",
    "accessory":      "accessory",
    "home":           "home",
    "stationery":     "stationery",
    "pet":            "pet",
    "sport":          "sport",
}


def read_csv(path):
    with open(path, mode="r", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, fieldnames=None):
    if not rows:
        return
    fieldnames = fieldnames or list(rows[0].keys())
    with open(path, mode="w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


# ═══════════════════════════════════════════════════════════════
# BƯỚC 1: Thêm category_id vào vc_product_type.csv
# ═══════════════════════════════════════════════════════════════
def patch_product_types():
    path = os.path.join(HUNG_DIR, "vc_product_type.csv")
    rows = read_csv(path)

    patched = 0
    for row in rows:
        group = row.get("product_group", "")
        cat_id = GROUP_TO_CATEGORY.get(group)
        if cat_id:
            row["category_id"] = cat_id
            patched += 1
        else:
            row["category_id"] = ""
            print(f"  ⚠ Không map được group '{group}' cho {row['product_type_id']}")

    # Đảm bảo category_id nằm sau product_type_id
    cols = list(rows[0].keys())
    if "category_id" not in cols:
        idx = cols.index("product_type_id") + 1
        cols.insert(idx, "category_id")

    write_csv(path, rows, fieldnames=cols)
    print(f"[Bước 1] vc_product_type.csv: thêm category_id cho {patched}/{len(rows)} dòng.")
    return rows


# ═══════════════════════════════════════════════════════════════
# BƯỚC 2: Đổi province_code trong shops.csv sang mã số
# ═══════════════════════════════════════════════════════════════
def patch_shops():
    prov_path = os.path.join(HIEU_DIR, "provinces.csv")
    shop_path = os.path.join(HAT_DIR, "shops.csv")

    provinces = read_csv(prov_path)
    valid_codes = [p["province_code"] for p in provinces]

    shops = read_csv(shop_path)
    patched = 0
    for shop in shops:
        old = shop["province_code"]
        # Nếu không phải mã số hợp lệ → random lại
        if old not in valid_codes:
            shop["province_code"] = random.choice(valid_codes)
            patched += 1

    write_csv(shop_path, shops)
    print(f"[Bước 2] shops.csv: đổi province_code cho {patched}/{len(shops)} shop.")
    return shops


# ═══════════════════════════════════════════════════════════════
# BƯỚC 3: Khớp product_type_id, category_id, tags trong listings.csv
# ═══════════════════════════════════════════════════════════════
def patch_listings(product_types):
    listing_path = os.path.join(HAT_DIR, "listings.csv")
    tags_path    = os.path.join(NHI_DIR, "tags.csv")

    # Load tag chuẩn
    tag_rows = read_csv(tags_path)
    valid_tags = [t["tag_id"] for t in tag_rows]

    # Build lookup: product_type_id → category_id
    pt_lookup = {pt["product_type_id"]: pt.get("category_id", "apparel") for pt in product_types}
    pt_ids = list(pt_lookup.keys())

    listings = read_csv(listing_path)

    patched_pt = 0
    patched_tags = 0

    for row in listings:
        # --- Patch product_type_id & category_id ---
        old_pt = row.get("product_type_id", "")
        if old_pt not in pt_lookup:
            new_pt = random.choice(pt_ids)
            row["product_type_id"] = new_pt
            row["category_id"] = pt_lookup[new_pt]
            patched_pt += 1
        else:
            # ID đúng rồi, chỉ cần sync category_id
            row["category_id"] = pt_lookup[old_pt]

        # --- Patch tags ---
        old_tags = row.get("tags", "").split(";")
        bad_tags = [t for t in old_tags if t and t not in valid_tags]
        if bad_tags:
            n = random.randint(1, 5)
            row["tags"] = ";".join(random.sample(valid_tags, n))
            patched_tags += 1

    write_csv(listing_path, listings)
    print(f"[Bước 3] listings.csv: đổi product_type_id cho {patched_pt}/{len(listings)}, "
          f"đổi tags cho {patched_tags}/{len(listings)}.")
    return listings


# ═══════════════════════════════════════════════════════════════
# KIỂM TRA SAU KHI VÁ
# ═══════════════════════════════════════════════════════════════
def verify(product_types):
    print("\n─── Kiểm tra toàn vẹn ───")
    errors = 0

    # 1. shops.csv province_code phải là số
    shops = read_csv(os.path.join(HAT_DIR, "shops.csv"))
    provinces = read_csv(os.path.join(HIEU_DIR, "provinces.csv"))
    valid_prov = {p["province_code"] for p in provinces}
    bad_prov = [s for s in shops if s["province_code"] not in valid_prov]
    if bad_prov:
        print(f"  ✗ {len(bad_prov)} shop có province_code sai: {[s['province_code'] for s in bad_prov[:5]]}")
        errors += 1
    else:
        print(f"  ✓ shops.csv: {len(shops)} shop có province_code hợp lệ.")

    # 2. listings.product_type_id phải nằm trong vc_product_type
    pt_set = {pt["product_type_id"] for pt in product_types}
    listings = read_csv(os.path.join(HAT_DIR, "listings.csv"))
    bad_pt = [l for l in listings if l["product_type_id"] not in pt_set]
    if bad_pt:
        print(f"  ✗ {len(bad_pt)} listing có product_type_id sai: {[l['product_type_id'] for l in bad_pt[:5]]}")
        errors += 1
    else:
        print(f"  ✓ listings.csv: {len(listings)} listing có product_type_id hợp lệ.")

    # 3. listings.tags chỉ chứa tag chuẩn
    tags_rows = read_csv(os.path.join(NHI_DIR, "tags.csv"))
    valid_tags = {t["tag_id"] for t in tags_rows}
    bad_tag_listings = []
    for l in listings:
        for t in l.get("tags", "").split(";"):
            if t and t not in valid_tags:
                bad_tag_listings.append((l["listing_id"], t))
                break
    if bad_tag_listings:
        print(f"  ✗ {len(bad_tag_listings)} listing chứa tag rác: {bad_tag_listings[:5]}")
        errors += 1
    else:
        print(f"  ✓ listings.csv: tags hợp lệ.")

    # 4. vc_product_type có category_id
    pt_no_cat = [pt for pt in product_types if not pt.get("category_id")]
    if pt_no_cat:
        print(f"  ✗ {len(pt_no_cat)} product_type thiếu category_id")
        errors += 1
    else:
        print(f"  ✓ vc_product_type.csv: {len(product_types)} loại đều có category_id.")

    if errors == 0:
        print("\n✅ Tất cả kiểm tra PASS.")
    else:
        print(f"\n❌ {errors} kiểm tra FAIL.")
    return errors


def main():
    print("=" * 60)
    print("fix_seed_linkage.py — Vá liên kết dữ liệu")
    print("=" * 60)

    product_types = patch_product_types()
    patch_shops()
    patch_listings(product_types)
    errors = verify(product_types)
    sys.exit(errors)


if __name__ == "__main__":
    main()
