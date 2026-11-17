import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.api.v1._live import _so
from app.api.v1._mart import db

TOI_THIEU_MAU = 30

TU_KHOA = {
    "thoi-trang": ["áo", "váy", "đầm", "quần", "sweater", "giày", "dép", "túi", "set", "khoác"],
    "trang-tri": ["trang trí", "tranh", "decor"],
    "gia-dung": ["cốc", "ly", "gối", "bình", "bếp", "gia dụng"],
}


def doan_slug(danh_muc: List[str]) -> Optional[str]:
    diem = {slug: sum(1 for ten in danh_muc for k in ds if k in ten.lower())
            for slug, ds in TU_KHOA.items()}
    slug = max(diem, key=diem.get)
    return slug if diem[slug] > 0 else None


def doc_tiki(slug: str) -> List[Dict[str, Any]]:
    return list(db()["external_market_products"].find(
        {"platform": "Tiki", "category_slug": slug},
        {"price_vnd": 1, "original_price_vnd": 1, "collected_at": 1}))


def _ngay(v: Any) -> str:
    return (v if isinstance(v, str) else v.isoformat())[:10]


def dong_thi_truong(rows: List[Dict[str, Any]], slug: str) -> Optional[Dict[str, Any]]:
    if len(rows) < TOI_THIEU_MAU:
        return None
    giam = []
    for r in rows:
        gia, goc = _so(r.get("price_vnd")) or 0, _so(r.get("original_price_vnd")) or 0
        if goc > gia:
            giam.append((goc - gia) / goc * 100)
    return {"category_slug": slug, "total": len(rows), "discounted": len(giam),
            "median_discount_pct": int(round(statistics.median(giam))) if giam else 0,
            "collected_at": max((_ngay(r["collected_at"]) for r in rows if r.get("collected_at")), default="")}
