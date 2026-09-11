"""
Tạo listing_variants.csv cho 5.000 sản phẩm trong data/external/products/listings.csv
Mỗi sản phẩm có 6-8 biến thể (size, màu), giá vốn 50k-120k, giá bán 150k-320k (margin >= 1.6).
"""

import csv
import os
import random
import sys
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AI_ANALYSIC_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "..", ".."))

LISTINGS_PATH = os.path.join(AI_ANALYSIC_DIR, "data", "external", "products", "listings.csv")
OUT_VARIANTS_PATH = os.path.join(AI_ANALYSIC_DIR, "data", "external", "products", "listing_variants.csv")

def main():
    random.seed(42)
    listings = pd.read_csv(LISTINGS_PATH)
    
    colors = [("den", "Đen"), ("trang", "Trắng"), ("xam", "Xám"), ("navy", "Xanh Navy"), ("do", "Đỏ Đô")]
    sizes = ["S", "M", "L", "XL", "2XL"]
    
    rows = []
    var_counter = 0
    
    for row in listings.itertuples(index=False):
        lst_id = getattr(row, "listing_id")
        num_variants = random.randint(6, 8)
        base_cost = random.randint(55, 110) * 1000
        base_price = int(base_cost * random.uniform(1.8, 2.5) // 1000 * 1000)
        
        for _ in range(num_variants):
            var_counter += 1
            var_id = f"var_{var_counter:07d}"
            color = random.choice(colors)[0]
            size = random.choice(sizes)
            price = base_price + (20000 if size == "2XL" else 0)
            cost = base_cost
            stock = 0 if random.random() < 0.03 else random.randint(10, 200)
            
            rows.append({
                "variant_id": var_id,
                "listing_id": lst_id,
                "color_code": color,
                "size_code": size,
                "cost": cost,
                "price": price,
                "stock_qty": stock
            })
            
    os.makedirs(os.path.dirname(OUT_VARIANTS_PATH), exist_ok=True)
    with open(OUT_VARIANTS_PATH, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
        
    print(f"Đã tạo {OUT_VARIANTS_PATH} với {len(rows):,} biến thể cho {len(listings):,} sản phẩm.")

if __name__ == "__main__":
    main()
