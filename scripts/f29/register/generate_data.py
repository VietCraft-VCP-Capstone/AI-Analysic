#!/usr/bin/env python3
"""
VietCraft - Synthetic data generator cho module AI Product Analytics.

Sinh ra:
  shops.csv                  - 500 shop, phan tang top/mid/small
  tags.csv                   - tu vung tag + ground truth xu huong tang truong
  listings.csv               - listing kem cac dac trung quan sat duoc
  listing_daily_metrics.csv  - chuoi views/carts/orders/revenue theo ngay
  gt_listing_quality.csv     - GROUND TRUTH: chat luong an (latent) cua listing
  gt_anomalies.csv           - GROUND TRUTH: cac ngay co bat thuong da tiem vao

Diem quan trong ve mat phuong phap:
  Conversion rate duoc sinh tu bien AN `q` (latent quality).
  Cac dac trung quan sat duoc (so anh, do dai mo ta, so tag, rating) chi la
  BIEN QUAN SAT NHIEU cua q, khong phai nguyen nhan truc tiep cua conversion.
  Nho vay Health Score (tinh tu dac trung quan sat) se tuong quan voi conversion
  o muc ~0.5-0.7 mot cach TU NHIEN, khong bi vong lap logic.

Chay:
    python3 generate_data.py --listings 10000 --shops 500 --out ./data
    python3 generate_data.py --listings 1500 --shops 80 --out ./data_dev   # ban nhe de test
"""

import argparse
import csv
import os
from datetime import date, timedelta

import numpy as np

# --------------------------------------------------------------------------
# Cau hinh
# --------------------------------------------------------------------------

PRODUCT_TYPES = ["tshirt", "hoodie", "mug", "poster", "totebag", "phonecase", "sticker"]

CATEGORIES = [
    "gia-dinh", "thay-co", "ban-than", "thu-cung", "anime", "game",
    "the-thao", "am-nhac", "du-lich", "cong-so", "hai-huoc", "ton-giao",
]

# Tu vung tag: (ten, category, archetype xu huong)
#   rising  = dang len, growth duong manh
#   falling = dang xuong
#   stable  = di ngang
#   seasonal= chi bung theo dip le
TAG_SEEDS = [
    ("qua-tang-thay-co", "thay-co", "seasonal"), ("20-11", "thay-co", "seasonal"),
    ("tri-an-giao-vien", "thay-co", "rising"),   ("lop-hoc", "thay-co", "stable"),
    ("qua-tang-me", "gia-dinh", "seasonal"),     ("gia-dinh-nho", "gia-dinh", "rising"),
    ("bo-va-con", "gia-dinh", "rising"),         ("ky-niem-cuoi", "gia-dinh", "stable"),
    ("ban-than-mai-ben-nhau", "ban-than", "falling"), ("hoi-ban-than", "ban-than", "rising"),
    ("meo-cute", "thu-cung", "rising"),          ("cho-corgi", "thu-cung", "rising"),
    ("hoi-nuoi-meo", "thu-cung", "stable"),      ("golden-retriever", "thu-cung", "stable"),
    ("anime-nhat", "anime", "stable"),           ("manga-vintage", "anime", "rising"),
    ("chibi", "anime", "falling"),               ("waifu", "anime", "falling"),
    ("lien-quan", "game", "falling"),            ("valorant", "game", "rising"),
    ("game-thu", "game", "stable"),              ("pixel-art", "game", "rising"),
    ("bong-da-viet-nam", "the-thao", "seasonal"), ("chay-bo", "the-thao", "rising"),
    ("gym-motivation", "the-thao", "stable"),    ("pickleball", "the-thao", "rising"),
    ("nhac-indie-viet", "am-nhac", "rising"),    ("rock-viet", "am-nhac", "stable"),
    ("rap-viet", "am-nhac", "falling"),          ("vinyl", "am-nhac", "stable"),
    ("da-lat", "du-lich", "seasonal"),           ("ha-giang", "du-lich", "rising"),
    ("phuot", "du-lich", "stable"),              ("bien-viet-nam", "du-lich", "seasonal"),
    ("dan-van-phong", "cong-so", "rising"),      ("deadline", "cong-so", "stable"),
    ("cafe-sang", "cong-so", "stable"),          ("hop-hanh", "cong-so", "falling"),
    ("meme-viet", "hai-huoc", "rising"),         ("cau-noi-vui", "hai-huoc", "stable"),
    ("troll", "hai-huoc", "falling"),            ("phat-giao", "ton-giao", "stable"),
    ("thu-phap", "ton-giao", "rising"),          ("an-lac", "ton-giao", "stable"),
]

# Cac dip le VN: (ten, ngay, so ngay mua truoc, do manh, product types huong loi)
HOLIDAYS = [
    ("phu-nu-vn",   date(2025, 10, 20), 12, 1.8, ["mug", "tshirt", "totebag"]),
    ("nha-giao-vn", date(2025, 11, 20), 18, 3.2, ["mug", "poster", "tshirt"]),
    ("noel",        date(2025, 12, 25), 21, 2.4, ["hoodie", "mug", "sticker"]),
    ("tet-duong",   date(2026,  1,  1), 10, 1.5, ["mug", "poster"]),
    ("valentine",   date(2026,  2, 14), 14, 2.0, ["mug", "phonecase", "tshirt"]),
    ("tet-am-lich", date(2026,  2, 17), 25, 3.6, ["poster", "totebag", "tshirt"]),
    ("quoc-te-pn",  date(2026,  3,  8), 14, 2.2, ["mug", "totebag", "tshirt"]),
    ("30-4",        date(2026,  4, 30), 10, 1.4, ["tshirt", "totebag"]),
    ("thieu-nhi",   date(2026,  6,  1), 10, 1.6, ["tshirt", "sticker", "phonecase"]),
]

PRICE_BY_TYPE = {  # (gia trung binh VND, do lech)
    "tshirt": (185_000, 45_000), "hoodie": (390_000, 80_000),
    "mug": (135_000, 30_000),    "poster": (95_000, 25_000),
    "totebag": (125_000, 28_000), "phonecase": (155_000, 35_000),
    "sticker": (35_000, 12_000),
}


# --------------------------------------------------------------------------
# Sinh du lieu
# --------------------------------------------------------------------------

def build_tags(rng, dates):
    """Tao tu vung tag + duong xu huong that (ground truth cho Gap Score)."""
    n_days = len(dates)
    t = np.arange(n_days) / n_days
    tags = []
    for i, (name, cat, arch) in enumerate(TAG_SEEDS):
        if arch == "rising":
            growth = rng.uniform(0.6, 1.8)
            curve = 1.0 + growth * t ** 1.4
        elif arch == "falling":
            growth = rng.uniform(-0.7, -0.3)
            curve = 1.0 + growth * t
        elif arch == "seasonal":
            growth = rng.uniform(-0.1, 0.2)
            curve = 1.0 + growth * t
        else:
            growth = rng.uniform(-0.12, 0.12)
            curve = 1.0 + growth * t
        curve = np.clip(curve, 0.15, None)
        # nhieu tuan
        curve = curve * (1 + 0.10 * rng.standard_normal(n_days))
        tags.append({
            "tag_id": f"TAG{i:03d}", "name": name, "category": cat,
            "archetype": arch,
            "popularity": float(rng.lognormal(0.0, 0.9)),
            "true_growth": float(growth),
            "curve": np.clip(curve, 0.1, None),
        })
    return tags


def build_shops(rng, n_shops):
    shops = []
    # 10% top, 30% mid, 60% small
    for i in range(n_shops):
        r = rng.random()
        if r < 0.10:
            tier, traffic = "top", rng.uniform(3.0, 6.5)
        elif r < 0.40:
            tier, traffic = "mid", rng.uniform(1.0, 2.8)
        else:
            tier, traffic = "small", rng.uniform(0.2, 0.9)
        shops.append({
            "shop_id": f"SHOP{i:04d}",
            "name": f"Shop {i:04d}",
            "tier": tier,
            "focus_category": CATEGORIES[rng.integers(len(CATEGORIES))],
            "traffic_factor": float(traffic),
            "response_hours": float(np.clip(rng.gamma(2.0, 4.0), 0.5, 48)),
        })
    return shops


def build_listings(rng, shops, tags, n_listings, dates):
    """Sinh listing. `q` la chat luong AN - khong bao gio expose ra API."""
    n_days = len(dates)
    listings, truth = [], []
    tags_by_cat = {}
    for t in tags:
        tags_by_cat.setdefault(t["category"], []).append(t)

    for i in range(n_listings):
        shop = shops[rng.integers(len(shops))]
        # 70% listing thuoc category chinh cua shop
        cat = shop["focus_category"] if rng.random() < 0.70 \
            else CATEGORIES[rng.integers(len(CATEGORIES))]
        ptype = PRODUCT_TYPES[rng.integers(len(PRODUCT_TYPES))]

        q = float(rng.beta(2.0, 5.0))  # <-- BIEN AN

        # --- dac trung QUAN SAT DUOC: chi la bien quan sat nhieu cua q ---
        n_images = int(np.clip(1 + rng.binomial(7, np.clip(0.12 + 0.80 * q, 0, 1)), 1, 8))
        desc_len = int(np.clip(rng.normal(140 + 900 * q, 150), 40, 2500))
        n_tags = int(np.clip(rng.poisson(1.8 + 10.0 * q), 1, 13))
        avg_rating = float(np.clip(rng.normal(3.25 + 1.70 * q, 0.32), 1.0, 5.0))

        pool = tags_by_cat.get(cat, tags)
        w = np.array([t["popularity"] for t in pool], dtype=float)
        idx = rng.choice(len(pool), size=min(n_tags, len(pool)), replace=False,
                         p=w / w.sum())
        chosen = [pool[j] for j in idx]

        mu, sd = PRICE_BY_TYPE[ptype]
        # listing chat luong cao dat gia cao hon mot chut
        price = float(np.clip(rng.normal(mu * (0.90 + 0.25 * q), sd), mu * 0.5, mu * 2.2))
        price = round(price / 1000) * 1000

        created_offset = int(rng.integers(0, max(1, n_days - 30)))

        listings.append({
            "listing_id": f"LST{i:06d}", "shop_id": shop["shop_id"],
            "category": cat, "product_type": ptype,
            "price": price, "n_images": n_images,
            "desc_length": desc_len, "n_tags": len(chosen),
            "tags": "|".join(t["name"] for t in chosen),
            "avg_rating": round(avg_rating, 2),
            "n_reviews": 0,
            "created_at": (dates[created_offset]).isoformat(),
            "_q": q, "_shop": shop, "_tags": chosen,
            "_created_idx": created_offset,
        })
        truth.append({"listing_id": f"LST{i:06d}", "latent_quality": round(q, 5)})
    return listings, truth


def seasonal_multiplier(dates, ptype, rng):
    """He so mua vu theo dip le VN + chu ky tuan + xu huong nen."""
    n = len(dates)
    m = np.ones(n)
    for name, hday, lead, strength, types in HOLIDAYS:
        if ptype not in types:
            strength *= 0.35
        for i, d in enumerate(dates):
            delta = (hday - d).days
            if -3 <= delta <= lead:
                # dinh o khoang 1/3 quang duong truoc ngay le
                peak = lead * 0.35
                m[i] += (strength - 1.0) * np.exp(-((delta - peak) ** 2) / (2 * (lead / 2.2) ** 2))
    # chu ky tuan: cuoi tuan cao hon
    dow = np.array([d.weekday() for d in dates])
    m *= np.where(dow >= 5, 1.22, 1.0) * np.where(dow == 0, 0.92, 1.0)
    # xu huong nen cua san
    m *= np.linspace(0.80, 1.30, n)
    return m


def generate_metrics(rng, listings, dates, anomaly_rate=0.006):
    n_days = len(dates)
    season_cache = {pt: seasonal_multiplier(dates, pt, rng) for pt in PRODUCT_TYPES}
    rows, anomalies = [], []

    for L in listings:
        q, shop = L["_q"], L["_shop"]
        start = L["_created_idx"]
        span = n_days - start
        if span < 14:
            continue

        # --- luot xem ---
        tag_curve = np.mean([t["curve"][start:] for t in L["_tags"]], axis=0)
        tag_pop = np.mean([t["popularity"] for t in L["_tags"]])
        base_views = shop["traffic_factor"] * (0.8 + 2.6 * q) * tag_pop * 4.5
        season = season_cache[L["product_type"]][start:]
        # duong cong tuoi listing: moi dang thi duoc boost, sau do on dinh
        age = np.arange(span)
        age_curve = 0.55 + 0.45 * np.exp(-age / 45) + 0.35 * (1 - np.exp(-age / 90))
        lam = np.clip(base_views * season * tag_curve * age_curve, 0.02, None)
        views = rng.poisson(lam)

        # --- conversion: phu thuoc BIEN AN q, khong phu thuoc dac trung quan sat ---
        mu, _ = PRICE_BY_TYPE[L["product_type"]]
        price_pen = np.clip(1.18 - 0.28 * (L["price"] / mu), 0.70, 1.18)
        tier_boost = {"top": 1.10, "mid": 1.0, "small": 0.92}[shop["tier"]]
        cr = 0.013 * np.exp(2.9 * q - 0.80) * price_pen * tier_boost
        cr = float(np.clip(cr, 0.001, 0.16))

        cart_rate = np.clip(cr * rng.uniform(3.5, 5.5), 0.005, 0.45)
        carts = rng.binomial(views, cart_rate)
        orders = rng.binomial(carts, np.clip(cr / cart_rate, 0.01, 0.95))

        # --- tiem bat thuong (ground truth cho F30 anomaly detection) ---
        n_anom = rng.poisson(anomaly_rate * span)
        for _ in range(int(n_anom)):
            d0 = int(rng.integers(7, span)) if span > 8 else 0
            dur = int(rng.integers(1, 4))
            kind = "spike" if rng.random() < 0.55 else "drop"
            factor = float(rng.uniform(3.0, 8.0)) if kind == "spike" else float(rng.uniform(0.05, 0.3))
            sl = slice(d0, min(d0 + dur, span))
            views[sl] = np.maximum(0, (views[sl] * factor).astype(int))
            orders[sl] = np.maximum(0, (orders[sl] * factor).astype(int))
            carts[sl] = np.maximum(orders[sl], (carts[sl] * factor).astype(int))
            anomalies.append({
                "listing_id": L["listing_id"],
                "date": dates[start + d0].isoformat(),
                "duration_days": dur, "kind": kind, "factor": round(factor, 2),
            })

        revenue = orders * L["price"]
        L["n_reviews"] = int(orders.sum() * rng.uniform(0.05, 0.18))

        for k in range(span):
            if views[k] == 0 and orders[k] == 0 and rng.random() < 0.75:
                continue  # bo bot dong rong cho nhe file
            rows.append((
                L["listing_id"], L["shop_id"], L["category"], L["product_type"],
                dates[start + k].isoformat(), int(views[k]), int(carts[k]),
                int(orders[k]), int(revenue[k]), L["price"],
            ))
    return rows, anomalies


# --------------------------------------------------------------------------

def write_csv(path, rows, header):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shops", type=int, default=500)
    ap.add_argument("--listings", type=int, default=10000)
    ap.add_argument("--end", type=str, default="2026-08-31")
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=str, default="./data")
    args = ap.parse_args()

    rng = np.random.default_rng(args.seed)
    os.makedirs(args.out, exist_ok=True)

    end = date.fromisoformat(args.end)
    dates = [end - timedelta(days=args.days - 1 - i) for i in range(args.days)]

    print(f"Khoang thoi gian: {dates[0]} -> {dates[-1]}  ({args.days} ngay)")

    tags = build_tags(rng, dates)
    shops = build_shops(rng, args.shops)
    listings, truth = build_listings(rng, shops, tags, args.listings, dates)
    print(f"Da tao {len(shops)} shop, {len(listings)} listing, {len(tags)} tag")

    rows, anomalies = generate_metrics(rng, listings, dates)
    print(f"Da tao {len(rows):,} dong metrics, {len(anomalies)} bat thuong")

    write_csv(os.path.join(args.out, "shops.csv"),
              [(s["shop_id"], s["name"], s["tier"], s["focus_category"],
                round(s["traffic_factor"], 3), round(s["response_hours"], 1))
               for s in shops],
              ["shop_id", "name", "tier", "focus_category", "traffic_factor", "response_hours"])

    write_csv(os.path.join(args.out, "tags.csv"),
              [(t["tag_id"], t["name"], t["category"], t["archetype"],
                round(t["popularity"], 4), round(t["true_growth"], 4)) for t in tags],
              ["tag_id", "name", "category", "archetype", "popularity", "true_growth"])

    write_csv(os.path.join(args.out, "tag_daily_interest.csv"),
              [(t["tag_id"], d.isoformat(), round(float(t["curve"][i] * t["popularity"] * 100), 2))
               for t in tags for i, d in enumerate(dates)],
              ["tag_id", "date", "search_interest"])

    write_csv(os.path.join(args.out, "listings.csv"),
              [(L["listing_id"], L["shop_id"], L["category"], L["product_type"],
                L["price"], L["n_images"], L["desc_length"], L["n_tags"],
                L["tags"], L["avg_rating"], L["n_reviews"], L["created_at"])
               for L in listings],
              ["listing_id", "shop_id", "category", "product_type", "price",
               "n_images", "desc_length", "n_tags", "tags", "avg_rating",
               "n_reviews", "created_at"])

    write_csv(os.path.join(args.out, "listing_daily_metrics.csv"), rows,
              ["listing_id", "shop_id", "category", "product_type", "date",
               "views", "add_to_carts", "orders", "revenue", "price"])

    write_csv(os.path.join(args.out, "gt_listing_quality.csv"),
              [(t["listing_id"], t["latent_quality"]) for t in truth],
              ["listing_id", "latent_quality"])

    write_csv(os.path.join(args.out, "gt_anomalies.csv"),
              [(a["listing_id"], a["date"], a["duration_days"], a["kind"], a["factor"])
               for a in anomalies],
              ["listing_id", "date", "duration_days", "kind", "factor"])

    # --- kiem tra nhanh ---
    arr = np.array([(r[5], r[7], r[8]) for r in rows], dtype=float)
    tv, to, tr = arr[:, 0].sum(), arr[:, 1].sum(), arr[:, 2].sum()
    print("\n--- Sanity check ---")
    print(f"Tong views        : {tv:,.0f}")
    print(f"Tong don hang     : {to:,.0f}")
    print(f"Tong doanh thu    : {tr:,.0f} VND")
    print(f"Conversion trung binh: {to / max(tv, 1) * 100:.2f}%  (ky vong 1-3%)")
    print(f"\nGhi ra: {os.path.abspath(args.out)}")


if __name__ == "__main__":
    main()
