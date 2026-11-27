import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from app.api.v1._live import db_live, la_shop_live, san_pham_live
from app.api.v1._mart import db

log = logging.getLogger("f38_seasonal")


def analyze_product_seasonal_readiness(
    product: Dict[str, Any],
    active_camp: Dict[str, Any],
    spending_growth_pct: Optional[int] = None,
) -> Dict[str, Any]:
    """Phân tích độ sẵn sàng của sản phẩm shop đón dịp cao điểm."""
    camp_name = re.sub(r"Lễ Hội |Mùa ", "", active_camp.get("name", "Chiến dịch"), flags=re.IGNORECASE)
    raw_title = (product.get("title") or "Sản phẩm").strip()

    clean_title = re.sub(r"\[[^\]]*\]|【[^】]*】", "", raw_title).strip()
    clean_title = re.sub(
        r"^(mẫu mới|hot|xả kho|chính hãng|cao cấp)\s*[-–—:]\s*", "", clean_title, flags=re.IGNORECASE
    ).strip()
    clean_title = re.sub(r"^[-–—:/|\s]+", "", clean_title).strip()
    parts = [p.strip() for p in re.split(r"[-–—|]", clean_title) if p.strip()]
    core_title = parts[0] if parts and len(parts[0]) >= 6 else (clean_title or raw_title)

    prod_category = (product.get("category") or "").lower()
    categories_text = " ".join(product.get("categories") or []).lower()
    tags_text = " ".join(product.get("tags") or []).lower()
    combined_text = f"{raw_title} {prod_category} {categories_text} {tags_text}".lower()

    imgs = product.get("images") or []
    has_images = len(imgs) >= 2 or bool(product.get("thumbnail") or product.get("image_url"))

    camp_keywords = [k.lower() for k in active_camp.get("search_keywords", []) if len(k) >= 3]
    has_keywords = any(kw in combined_text for kw in camp_keywords) or len(product.get("tags") or []) >= 2

    has_combo = bool(re.search(r"set|combo|hộp quà|quà tặng|bundle|pack", raw_title, re.IGNORECASE))

    title_len = len(raw_title)
    has_seo = title_len >= 30 and any(
        k in raw_title.lower() for k in [camp_name.lower(), "quà", "tết", "20/11", "noel", "12/12", "lễ", "tri ân"]
    )

    if any(w in combined_text for w in ["áo", "quần", "đầm", "váy", "khoác", "len", "thun", "hoodie", "thời trang", "may mặc"]):
        cat_label = "Thời trang & May mặc"
        combo_tip = "kèm hộp quà nơ sang trọng, thiệp chúc hoặc phụ kiện phối kèm (khăn/tất)"
        sample_combo = f"Set {core_title} Kèm Hộp Quà Sang Trọng & Thiệp {camp_name}"
        sample_keywords = f'"quà tặng thời trang", "set đồ {camp_name.lower()}", "thời trang {camp_name.lower()}"'
        seller_action_tip = 'Thêm phân loại "Kèm Hộp Quà Sang Trọng & Thiệp" (tự đặt giá phụ thu theo chi phí hộp) ngay trên sản phẩm hiện tại mà không cần nhập thêm mặt hàng mới.'
    elif any(w in combined_text for w in ["khăn", "choàng", "lụa", "túi", "ví", "mũ", "nón", "phụ kiện"]):
        cat_label = "Phụ kiện thời trang"
        combo_tip = "kèm hộp đựng lót nhung hoặc túi quà quai xách và thiệp mừng"
        sample_combo = f"Hộp Quà Cao Cấp {core_title} Kèm Thiệp Tri Ân {camp_name}"
        sample_keywords = f'"khăn quà tặng", "hộp quà phụ kiện", "quà {camp_name.lower()} tinh tế"'
        seller_action_tip = 'Thêm tùy chọn "Đóng Hộp Quà Nơ + Thiệp Kỷ Niệm" (tự đặt giá phụ thu theo chi phí hộp) để khách mua làm quà biếu tặng trọn gói.'
    elif any(w in combined_text for w in ["gốm", "sứ", "ly", "cốc", "bình", "chén", "ấm", "tách", "gia dụng"]):
        cat_label = "Gốm sứ & Gia dụng"
        combo_tip = "ghép cặp đôi hoặc kèm thìa mạ vàng, đế lót gỗ và hộp quà kraft"
        sample_combo = f"Set 2 {core_title} Kèm Thìa Vàng & Hộp Quà {camp_name}"
        sample_keywords = f'"ly sứ quà tặng", "quà lưu niệm {camp_name.lower()}", "set gốm quà tặng"'
        seller_action_tip = "Tạo combo bán theo cặp (set 2 chiếc) hoặc kèm hộp quà lót rơm mộc mạc để tăng giá trị đơn hàng."
    elif any(w in combined_text for w in ["tranh", "đèn", "decor", "trang trí", "nến", "tượng", "gỗ", "thủ công", "mỹ nghệ"]):
        cat_label = "Thủ công mỹ nghệ & Decor"
        combo_tip = "kèm hộp giấy kraft bọc rơm mộc mạc, tag thiệp handmade và nến thơm"
        sample_combo = f"Combo Quà Handmade {core_title} Kèm Thiệp Gỗ {camp_name}"
        sample_keywords = f'"quà handmade", "đồ decor {camp_name.lower()}", "quà thủ công mỹ nghệ"'
        seller_action_tip = "Đóng gói theo phong cách quà tặng mộc (Eco-friendly) với dây cói và thiệp chúc viết tay."
    elif any(w in combined_text for w in ["trà", "cà phê", "bánh", "mứt", "kẹo", "thực phẩm"]):
        cat_label = "Thực phẩm & Quà biếu"
        combo_tip = "kèm tách thưởng trà hoặc giỏ quà mây tre đan cao cấp"
        sample_combo = f"Hộp Quà Thưởng Trà {core_title} Kèm Thiệp Chúc {camp_name}"
        sample_keywords = f'"hộp quà thực phẩm", "quà biếu {camp_name.lower()}", "trà quà tặng"'
        seller_action_tip = "Ghép set 2-3 vị khác nhau đóng hộp quà tết hoặc kèm bình giữ nhiệt cao cấp."
    else:
        cat_label = "Sản phẩm thủ công & Quà tặng"
        combo_tip = "kèm hộp quà nơ đóng sẵn và thiệp chúc mừng"
        sample_combo = f"Set Quà Tặng {core_title} Cao Cấp Dịp {camp_name}"
        sample_keywords = f'"quà tặng {camp_name.lower()}", "set quà tri ân"'
        seller_action_tip = "Thêm phân loại đóng hộp quà nơ và thiệp chúc mừng trên trang chỉnh sửa sản phẩm."

    best_keyword = (active_camp.get("search_keywords") or [f"quà tặng {camp_name.lower()}"])[0]
    if len(core_title) < 24:
        suggested_seo_title = f"{core_title} Cao Cấp - {best_keyword.title()} Dịp {camp_name} Sang Trọng Ý Nghĩa"
    else:
        suggested_seo_title = f"{core_title} - {best_keyword.title()} Dịp {camp_name} Cao Cấp"

    checklist = [
        {
            "id": "images",
            "label": f"Ảnh concept dịp {camp_name}",
            "is_done": has_images,
            "action_title": f"Bổ sung ảnh concept dịp {camp_name}",
            "action_detail": f"Tải thêm ít nhất 2 ảnh chụp sản phẩm với bối cảnh hoặc hộp quà theo chủ đề dịp {camp_name}.",
            "seller_tip": "Chụp 1 ảnh sản phẩm đặt cạnh hộp quà hoặc bối cảnh ngày lễ để thu hút khách bấm vào xem.",
            "market_data": "Ảnh chụp bối cảnh hoặc hộp quà theo chủ đề dịp giúp khách thấy ngay sản phẩm hợp để mua làm quà.",
        },
        {
            "id": "keywords",
            "label": "Từ khoá ngách đón tìm kiếm sớm",
            "is_done": has_keywords,
            "action_title": "Gắn từ khoá ngách đón tìm kiếm sớm",
            "action_detail": f"Bổ sung các từ khóa tìm kiếm theo dịp vào thẻ tag hoặc danh mục (gợi ý: {sample_keywords}).",
            "seller_tip": f"Thêm các tag: #{camp_name.lower().replace(' ', '')}, #{best_keyword.replace(' ', '')} vào phần mô tả sản phẩm.",
            "market_data": "Cập nhật từ khóa sớm giúp sản phẩm xuất hiện đúng lúc khách bắt đầu tìm kiếm theo dịp.",
        },
        {
            "id": "combo",
            "label": "Đóng gói combo set quà tặng",
            "is_done": has_combo,
            "action_title": "Tạo combo set quà tặng",
            "action_detail": f'Tạo thêm phân loại {combo_tip} (gợi ý: "{sample_combo}").',
            "seller_tip": seller_action_tip,
            "market_data": (
                f"Giá trị đơn hàng (AOV) dịp này {'tăng' if spending_growth_pct >= 0 else 'giảm'} {spending_growth_pct:+d}% so với ngày thường."
                if spending_growth_pct is not None
                else "Chưa đủ đơn để đo giá trị đơn hàng dịp này so với ngày thường."
            ),
        },
        {
            "id": "seo",
            "label": "Tiêu đề & mô tả chuẩn SEO sàn",
            "is_done": has_seo,
            "action_title": f"Kéo dài tiêu đề chuẩn SEO (hiện {title_len}/30+ ký tự)",
            "action_detail": f'Tiêu đề quá ngắn khiến sàn khó phân bổ tìm kiếm. Gợi ý đổi thành: "{suggested_seo_title}".',
            "seller_tip": "Chèn tên dịp lễ và từ khóa chính vào 30 ký tự đầu tiên của tiêu đề để tối ưu công cụ tìm kiếm sàn.",
            "market_data": "Tiêu đề có tên dịp và từ khóa chính ở phần đầu giúp khách tìm theo dịp dễ thấy sản phẩm hơn.",
        },
    ]

    done_count = sum(1 for item in checklist if item["is_done"])
    readiness_score = int((done_count / len(checklist)) * 100)

    return {
        "category_detected": cat_label,
        "readiness_score": readiness_score,
        "done_count": done_count,
        "total_criteria": len(checklist),
        "is_ready_100": done_count == len(checklist),
        "checklist": checklist,
        "uncompleted": [item for item in checklist if not item["is_done"]],
    }


def load_and_audit_shop_products(
    shop_id: str,
    active_camp: Dict[str, Any],
    spending_growth_pct: Optional[int],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Lấy danh sách sản phẩm THẬT của shop & rà soát sản phẩm khớp với dịp."""
    shop_products: List[Dict[str, Any]] = []
    try:
        if la_shop_live(shop_id):
            raw_sp = san_pham_live(shop_id, gioi_han=100)
            for p in raw_sp:
                imgs = p.get("images") or []
                if not imgs and p.get("image_url"):
                    imgs = [p["image_url"]]
                shop_products.append(
                    {
                        "_id": p["product_id"],
                        "title": p["title"],
                        "price_vnd": p.get("price_vnd") or 0,
                        "stock": p.get("stock") or 0,
                        "images": imgs,
                        "thumbnail": imgs[0] if imgs else None,
                        "image_url": imgs[0] if imgs else None,
                        "tags": p.get("tags") or [],
                        "categories": p.get("categories") or [],
                        "source_idea_id": p.get("source_idea_id"),
                        "orders": 0,
                        "revenue_vnd": 0,
                    }
                )
        else:
            proj = {
                "title": 1,
                "tags": 1,
                "images": 1,
                "categories": 1,
                "price": 1,
                "retail_price": 1,
                "stock": 1,
                "sold_count": 1,
                "thumbnail": 1,
                "image_url": 1,
            }
            seed_prods: List[Dict[str, Any]] = []
            try:
                seed_prods = list(db_live()["products"].find({}, proj).limit(20))
            except Exception as exc:
                log.warning("seasonal: %s: %s", type(exc).__name__, exc)
            if not seed_prods:
                try:
                    seed_prods = list(db()["products"].find({}, proj).limit(20))
                except Exception as exc:
                    log.warning("seasonal: %s: %s", type(exc).__name__, exc)

            for p in seed_prods:
                raw_imgs = p.get("images") or []
                if isinstance(raw_imgs, str):
                    raw_imgs = [raw_imgs]
                imgs = [x if isinstance(x, str) else x.get("url") for x in raw_imgs if x]
                if not imgs and p.get("thumbnail"):
                    imgs = [p["thumbnail"]]
                if not imgs and p.get("image_url"):
                    imgs = [p["image_url"]]

                shop_products.append(
                    {
                        "_id": str(p["_id"]),
                        "title": p.get("title") or "",
                        "price_vnd": int(p.get("price") or p.get("retail_price") or 150000),
                        "stock": int(p.get("stock") or 25),
                        "images": imgs,
                        "thumbnail": imgs[0] if imgs else None,
                        "image_url": imgs[0] if imgs else None,
                        "tags": p.get("tags") or [],
                        "categories": p.get("categories") or [],
                        "orders": int(p.get("sold_count") or 0),
                        "revenue_vnd": int(p.get("sold_count") or 0) * int(p.get("price") or 150000),
                    }
                )
    except Exception as exc:
        log.warning("seasonal: %s: %s", type(exc).__name__, exc)
        shop_products = []

    search_terms = [k.lower() for k in active_camp.get("search_keywords", [])] + [
        active_camp.get("name", "").lower(),
        active_camp.get("id", "").lower(),
    ]
    matching_shop_products: List[Dict[str, Any]] = []
    for p in shop_products:
        text_to_check = f"{p.get('title') or ''} {' '.join(p.get('tags') or [])} {' '.join(p.get('categories') or [])}".lower()
        if any(term in text_to_check for term in search_terms if len(term) >= 3):
            p["readiness_analysis"] = analyze_product_seasonal_readiness(p, active_camp, spending_growth_pct)
            matching_shop_products.append(p)

    return shop_products, matching_shop_products

