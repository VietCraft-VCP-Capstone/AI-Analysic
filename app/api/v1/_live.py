import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.api.v1._mart import client_dung_chung
from app.config import settings

_OBJECT_ID = re.compile(r"^[0-9a-fA-F]{24}$")


def la_shop_live(shop_id: str) -> bool:
    """Mã shop của sàn thật là ObjectId 24 ký tự hex; mã dữ liệu mồi là `shp_00017`."""
    return bool(_OBJECT_ID.match(shop_id or ""))


def db_live():
    """Handle tới database sàn thật. Chỉ ĐỌC — module phân tích không ghi vào sàn."""
    return client_dung_chung()[settings.MONGO_DB_LIVE]


TU_KHOA_VI: List[tuple] = [
    # Đồ uống
    (r"bộ ấm chén|ấm chén|ấm trà", "mug_11oz"),
    (r"bộ ly|ly sứ|ly gốm|tách|cốc|\bly\b", "mug_11oz"),
    (r"bình giữ nhiệt|bình nước", "bottle_sport"),
    # May mặc
    (r"áo khoác|áo choàng|jacket|hoodie|áo hoodie", "hoodie"),
    (r"áo thun|áo phông|áo tee|áo đấu|\bao thun\b", "tshirt_unisex"),
    (r"áo sơ mi", "shirt_button"),
    (r"đầm|váy|dress", "dress"),
    (r"quần", "sweatpants"),
    # Túi và phụ kiện
    (r"túi tote|túi totte|tote", "tote"),
    (r"túi kẹp|túi xách|\btúi\b", "tote"),
    (r"ba lô|balo", "backpack"),
    (r"ví da|\bví\b|wallet", "wallet"),
    (r"dây lưng|thắt lưng|belt", "belt"),
    (r"nón|mũ lưỡi trai", "hat_dad"),
    # In ấn và trang trí tường
    (r"tranh treo tường|tranh canvas|\btranh\b|poster", "canvas_stretched"),
    (r"sticker|nhãn dán", "sticker"),
    # Văn phòng phẩm
    (r"sổ tay|sổ ghi|notebook", "notebook_soft"),
    (r"lịch để bàn|lịch treo", "calendar_wall"),
    # Nhà cửa
    (r"gối|vỏ gối", "pillow_case"),
    (r"chăn|mền|khăn trải", "blanket_fleece"),
    (r"thảm chân|thảm cửa", "doormat"),
    (r"đèn ngủ|đèn trang trí", "night_light"),
    (r"móc khóa|móc khoá", "keychain"),
    (r"khẩu trang", "face_mask"),
]

# Sản phẩm thủ công KHÔNG có loại phôi POD tương ứng. Nhận ra để nói thẳng là không so
# được, thay vì gán bừa vào một loại phôi gần gần rồi đưa ra một khoảng giá vô nghĩa.
THU_CONG_KHONG_CO_PHOI = re.compile(
    r"bình hoa|chậu|thố|khay|đĩa gốm|bát|nhẫn|vòng tay|dây chuyền|trang sức|"
    r"tượng|điêu khắc|đồ gỗ|khay trà|hộp gỗ|"
    # Tên tiếng Anh của cùng nhóm đồ thủ công: sàn có cả sản phẩm đặt tên tiếng Anh.
    r"\bring\b|\bnecklace\b|\bbracelet\b|\bvase\b|\bjewel|\bearring|\bcarv|\bsculpt",
    re.IGNORECASE,
)


# Dấu hiệu hàng thủ công
DAU_HIEU_THU_CONG = re.compile(
    r"thủ công|handmade|hand-made|gốm|sứ\b|sa thạch|bát tràng|men lam|men tro|men hỏa biến|"
    r"xà cừ|da bò|da sáp|dệt tay|thêu tay|thêu hoạ|thêu họa|đan tay|khâu tay|mộc\b|"
    r"điêu khắc|khắc nổi|nguyên tấm",
    re.IGNORECASE,
)


def doan_loai_phoi(title: str, tags: Optional[List[str]] = None) -> Dict[str, Any]:
    """Đoán mã loại phôi từ tên sản phẩm thật."""
    text = " ".join([title or ""] + list(tags or []))
    low = text.lower()
    thu_cong = bool(DAU_HIEU_THU_CONG.search(low))

    for pattern, pt in TU_KHOA_VI:
        if re.search(pattern, low):
            return {"product_type_id": pt, "source": "vi", "handmade_hint": thu_cong}

    try:
        sys.path.insert(0, str(ROOT_DIR / "app" / "seed" / "catalog"))
        from build_catalog import classify_blueprint  # type: ignore[import-not-found]  # noqa: PLC0415

        pt = classify_blueprint(title or "")
        if pt:
            return {"product_type_id": pt, "source": "en", "handmade_hint": thu_cong}
    except Exception:
        pass

    if THU_CONG_KHONG_CO_PHOI.search(low):
        return {"product_type_id": None, "source": "handmade", "handmade_hint": True}
    return {"product_type_id": None, "source": "unknown", "handmade_hint": thu_cong}


LOC_SP_THAT = {"seed_ref": {"$exists": False}}
LOC_DON_THAT = {"seed_ref": {"$exists": False}, "is_simulated": {"$ne": True}}


def _so(x: Any) -> Optional[float]:
    """Decimal128 của Mongo sang float. Giá trên sàn lưu dạng Decimal128."""
    if x is None:
        return None
    try:
        return float(str(x))
    except (TypeError, ValueError):
        return None


def san_pham_live(shop_id: str, gioi_han: int = 200) -> List[Dict[str, Any]]:
    """Sản phẩm thật của shop, kèm giá thật lấy từ `product_variants`.

    Giá đại diện dùng TRUNG VỊ các biến thể đang bán, không dùng trung bình: một biến
    thể cỡ lớn đặt giá cao sẽ kéo trung bình lệch khỏi mức người mua thường thấy.

    CHỈ đọc sản phẩm thật (qua bộ lọc LOC_SP_THAT), bỏ sản phẩm seed.
    """
    from bson import ObjectId  # noqa: PLC0415

    live = db_live()
    try:
        oid = ObjectId(shop_id)
    except Exception:
        return []

    products = list(live["products"].find(
        {**{"shop_id": oid}, **LOC_SP_THAT},
        {"title": 1, "tags": 1, "categories": 1, "images": 1, "description": 1,
         "average_rating": 1, "rating_count": 1, "created_at": 1, "listing_status": 1,
         "status": 1, "is_hidden": 1},
    ).limit(gioi_han))
    if not products:
        return []

    ids = [p["_id"] for p in products]
    bien_the: Dict[Any, List[Dict[str, Any]]] = {}
    for v in live["product_variants"].find(
        {"product_id": {"$in": ids}},
        {"product_id": 1, "retail_price": 1, "base_cost": 1, "stock_quantity": 1, "is_active": 1},
    ):
        bien_the.setdefault(v["product_id"], []).append(v)

    ra: List[Dict[str, Any]] = []
    for p in products:
        vs = [v for v in bien_the.get(p["_id"], []) if v.get("is_active", True)]
        gia = sorted(g for g in (_so(v.get("retail_price")) for v in vs) if g and g > 0)
        von = sorted(c for c in (_so(v.get("base_cost")) for v in vs) if c and c > 0)
        ton = sum(int(v.get("stock_quantity") or 0) for v in vs)
        doan = doan_loai_phoi(p.get("title", ""), p.get("tags"))

        ra.append({
            "product_id": str(p["_id"]),
            "title": p.get("title") or "",
            "tags": p.get("tags") or [],
            "categories": p.get("categories") or [],
            "n_images": len(p.get("images") or []),
            "description_len": len(p.get("description") or ""),
            "rating": _so(p.get("average_rating")),
            "n_reviews": int(p.get("rating_count") or 0),
            "created_at": p.get("created_at"),
            "n_variants": len(vs),
            "price_vnd": int(gia[len(gia) // 2]) if gia else None,
            "price_min_vnd": int(gia[0]) if gia else None,
            "price_max_vnd": int(gia[-1]) if gia else None,
            "cost_vnd": int(von[len(von) // 2]) if von else None,
            "stock": ton,
            "product_type_id": doan["product_type_id"],
            "type_source": doan["source"],
            "handmade_hint": doan["handmade_hint"],
        })
    return ra


def gia_cung_danh_muc_live(danh_muc: List[str], tru_shop: Optional[str] = None,
                           gioi_han: int = 400) -> List[int]:
    """Giá của các sản phẩm THẬT khác trên sàn cùng danh mục (chữ tự do của sàn).

    Dùng khi sản phẩm không ánh xạ được sang loại phôi POD nào, ví dụ đồ gốm thủ công:
    lúc đó mặt bằng đúng là các sản phẩm thật cùng ngành trên sàn, không phải catalog POD.

    CHỈ đọc sản phẩm thật (qua bộ lọc LOC_SP_THAT), bỏ sản phẩm seed.
    """
    from bson import ObjectId  # noqa: PLC0415

    if not danh_muc:
        return []
    live = db_live()
    loc: Dict[str, Any] = {**{"categories": {"$in": danh_muc}}, **LOC_SP_THAT}
    if tru_shop:
        try:
            loc["shop_id"] = {"$ne": ObjectId(tru_shop)}
        except Exception:
            pass

    ids = [p["_id"] for p in live["products"].find(loc, {"_id": 1}).limit(gioi_han)]
    if not ids:
        return []
    gia: List[int] = []
    for v in live["product_variants"].find(
        {"product_id": {"$in": ids}, "is_active": True}, {"retail_price": 1}
    ):
        g = _so(v.get("retail_price"))
        if g and g > 0:
            gia.append(int(g))
    return sorted(gia)


if __name__ == "__main__":
    print("=== TỰ KIỂM TRA _LIVE.PY ===")

    assert la_shop_live("6a7c5269db23367af9fdf13b")
    assert not la_shop_live("shp_00017")
    assert not la_shop_live("")
    print("✓ phân biệt được mã shop sàn thật và mã shop dữ liệu mồi")

    mau = [
        ("Áo Thun Streetwear Local Brand", "tshirt_unisex", "vi"),
        ("Bộ Ly Gốm Mộc Men Lam Bát Tràng", "mug_11oz", "vi"),
        ("Túi Totte cá chép", "tote", "vi"),
        ("Tranh cá chép treo tường", "canvas_stretched", "vi"),
        ("Sổ Tay Bìa Da Bò Mộc Khâu Tay", "notebook_soft", "vi"),
        ("- Áo Khoác Choàng Lông Dáng Ngắn", "hoodie", "vi"),
        ("Đầm Thiết Kế Corset Cổ Yếm", "dress", "vi"),
    ]
    for title, mong, nguon in mau:
        kq = doan_loai_phoi(title)
        assert kq["product_type_id"] == mong, f"{title!r} -> {kq} (mong {mong})"
        assert kq["source"] == nguon, f"{title!r} nguồn {kq['source']}, mong {nguon}"
    print(f"✓ đoán đúng {len(mau)} tên tiếng Việt")

    kq = doan_loai_phoi("Minimalist Geometric T-Shirt")
    assert kq["product_type_id"] and kq["source"] in ("vi", "en"), kq
    print("✓ vẫn đoán được tên tiếng Anh")

    for title in ("Bình Hoa Gốm Điêu Khắc Khía Nổi", "Khay Trà Gỗ Xà Cừ", "Minimalist Silver Ring"):
        kq = doan_loai_phoi(title)
        assert kq["source"] == "handmade", f"{title!r} -> {kq}"
        assert kq["product_type_id"] is None
    print("✓ nhận ra đồ thủ công không có loại phôi POD tương ứng")

    assert doan_loai_phoi("Faker Zed")["source"] == "unknown"
    print("✓ tên không gợi ý gì thì trả unknown, không gán bừa")

    print("✅ TẤT CẢ SELF-CHECKS CỦA _LIVE.PY ĐÃ PASS!")
