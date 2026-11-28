"""Nhóm ngành dùng chung cho module Seasonal (một bộ mã duy nhất cho AI, BE và FE).

Danh mục thật của sàn (collection `categories`) là danh mục lá, phẳng (ao-thun, tui, laptop…).
Module này quy danh mục lá về nhóm ngành; danh mục mới chưa có trong bảng thì đoán theo tên.
"""
import re
from collections import Counter
from typing import Any, Dict, Iterable, List, Optional, Tuple

GROUP_LABELS: Dict[str, str] = {
    "thoi-trang": "Thời trang & May mặc",
    "phu-kien": "Phụ kiện & Túi ví",
    "sac-dep": "Sắc đẹp & Mỹ phẩm",
    "dien-tu": "Thiết bị điện tử & Phụ kiện số",
    "nha-cua-doi-song": "Nhà cửa & Đời sống",
    "me-be": "Mẹ & Bé",
    "bach-hoa": "Bách hóa & Thực phẩm",
    "the-thao": "Thể thao & Dã ngoại",
    "van-phong-pham": "Văn phòng phẩm",
    "thu-cong-qua-tang": "Thủ công & Quà tặng",
    "tong-hop": "Toàn ngành hàng TMĐT",
}
GROUPS: List[str] = list(GROUP_LABELS)

# Danh mục lá hiện có trên sàn → nhóm ngành. Danh mục rác/thử nghiệm (vd. "2011", "la-cay") không có ở đây.
LEAF_TO_GROUP: Dict[str, str] = {
    **{s: "thoi-trang" for s in (
        "ao-da", "ao-dai", "ao-khoac", "ao-kieu", "ao-long", "ao-thun", "do-bo", "do-ngu", "jacket", "leather",
        "quan", "quan-dai", "set-ao-quan", "set-ao-vay", "sweater", "vay-dam", "vai-len",
        "giay-cao-got", "giay-dep", "sneaker",
    )},
    **{s: "phu-kien" for s in ("phu-kien", "that-lung", "trang-suc", "tui")},
    **{s: "dien-tu" for s in ("dien-thoai", "laptop", "phu-kien-dien-thoai")},
    **{s: "nha-cua-doi-song" for s in ("nha-cua", "ly-tach")},
    **{s: "thu-cong-qua-tang" for s in ("hop-qua", "trang-tri", "tranh-anh")},
    "ao-quan-bong-da": "the-thao",
}

# Đoán nhóm theo chữ (tên danh mục mới hoặc tiêu đề sản phẩm). Thứ tự = ưu tiên khi trùng điểm.
_KEYWORDS: List[Tuple[str, str]] = [
    ("thoi-trang", r"áo|quần|váy|đầm|hoodie|sweater|thời trang|nỉ|jacket|khoác|jeans|sơ mi|blazer|giày|dép|sneaker|guốc|sandal"),
    ("sac-dep", r"mỹ phẩm|son|kem|serum|phấn|nước hoa|sữa rửa mặt|toner|dưỡng da|chăm sóc da|makeup|skincare|dầu gội|sữa tắm|mặt nạ"),
    ("dien-tu", r"điện tử|công nghệ|điện thoại|laptop|tai nghe|sạc|cáp|loa|bluetooth|ốp lưng|chuột|bàn phím|máy ảnh|cường lực|smartwatch"),
    ("nha-cua-doi-song", r"gia dụng|nhà cửa|đời sống|bếp|nồi|chảo|bát|đĩa|cốc|ly|gốm|sứ|bình|thớt|chăn|gối|nệm|tủ|bàn|ghế|đèn|khăn tắm"),
    ("me-be", r"mẹ và bé|sơ sinh|bỉm|tã|bình sữa|đồ chơi|xe đẩy|trẻ em|đồ bầu|ăn dặm"),
    ("bach-hoa", r"thực phẩm|bách hóa|đồ ăn|bánh|kẹo|snack|khô bò|hạt|mứt|trà|cà phê|gia vị|gạo|đặc sản"),
    ("the-thao", r"thể thao|dã ngoại|gym|yoga|bóng đá|cầu lông|vợt|lều|chạy bộ|đồ bơi"),
    ("van-phong-pham", r"văn phòng phẩm|sách|vở|sổ|bút|thước|họa cụ|màu vẽ|giấy in"),
    ("phu-kien", r"trang sức|vòng|dây chuyền|nhẫn|khuyên tai|lắc tay|đồng hồ|mắt kính|kính râm|thắt lưng|túi|ví|bóp|nón|mũ|khăn"),
    ("thu-cong-qua-tang", r"thủ công|handmade|quà lưu niệm|quà tặng|hộp quà|mây tre|khắc gỗ|thêu|tranh|trang trí|decor|nến"),
]
_KEYWORD_RE = [(g, re.compile(rf"(?<!\w)(?:{p})(?!\w)")) for g, p in _KEYWORDS]

# Mã danh mục trong catalog sàn khác (external_market_products) ứng với từng nhóm
CATALOG_SLUGS: Dict[str, List[str]] = {
    "nha-cua-doi-song": ["nha-cua-doi-song", "gia-dung"],
    "thu-cong-qua-tang": ["thu-cong-qua-tang", "trang-tri"],
}


def catalog_slugs_for(group: str) -> List[str]:
    return CATALOG_SLUGS.get(group, [group])


def _guess_by_text(text: str) -> Optional[str]:
    t = (text or "").lower()
    best, best_hits = None, 0
    for g, rx in _KEYWORD_RE:
        hits = len(rx.findall(t))
        if hits > best_hits:
            best, best_hits = g, hits
    return best


def group_for_category(slug: Optional[str], name: Optional[str]) -> Optional[str]:
    """Nhóm ngành của một danh mục lá; không nhận ra thì None."""
    if slug and slug in LEAF_TO_GROUP:
        return LEAF_TO_GROUP[slug]
    return _guess_by_text(name or "")


def detect_shop_group(products: Iterable[Dict[str, Any]], categories: Dict[str, Tuple[str, str]]) -> Dict[str, Any]:
    """Nhóm ngành chính của shop: ưu tiên danh mục thật của sản phẩm, không có thì đoán theo tiêu đề.

    `categories`: {category_id(str): (slug, name)}.
    """
    products = list(products)
    by_cat: Counter = Counter()
    for p in products:
        groups = {
            g for cid in (p.get("category_ids") or [])
            if (g := group_for_category(*categories.get(str(cid), (None, None))))
        }
        for g in groups:
            by_cat[g] += 1
    if by_cat:
        g, n = by_cat.most_common(1)[0]
        return {"slug": g, "name": GROUP_LABELS[g], "source": "category", "share_pct": round(100 * n / max(1, len(products)))}

    by_text: Counter = Counter()
    for p in products:
        text = " ".join([str(p.get("title") or "")] + [str(x) for x in (p.get("categories") or [])] + [str(x) for x in (p.get("tags") or [])])
        g = _guess_by_text(text)
        if g:
            by_text[g] += 1
    if by_text:
        g, n = by_text.most_common(1)[0]
        return {"slug": g, "name": GROUP_LABELS[g], "source": "keywords", "share_pct": round(100 * n / max(1, len(products)))}
    return {"slug": "tong-hop", "name": GROUP_LABELS["tong-hop"], "source": "none", "share_pct": None}
