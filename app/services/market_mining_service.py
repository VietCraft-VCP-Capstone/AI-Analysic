import re
from typing import Any, Dict, List, Optional
from app.api.v1._mart import db
from app.api.v1._live import db_live


CATEGORY_TO_MARTS = {
    "thoi-trang": ["apparel", "bottoms"],
    "gia-dung": ["drinkware", "home"],
    "phu-kien": ["accessory", "bag"],
    "trang-tri": ["wallart", "home"],
}

# Ánh xạ từ khóa mùa vụ sang nhóm thuộc tính đặc trưng trong ngành
SEASONAL_ATTRIBUTE_CLUSTERS = {
    "quà tết": {
        "thoi-trang": "Áo dài cách tân & Trang phục du xuân gia đình",
        "gia-dung": "Khay mứt gốm sứ & Bộ ấm chén tiếp khách Tết",
        "phu-kien": "Bộ bao lì xì mỹ thuật & Túi vải du xuân",
        "trang-tri": "Tranh câu đối thư pháp & Đèn lồng trang trí",
        "default": "Hộp quà Tết & Đồ trang trí đón xuân"
    },
    "trang trí tết": {
        "thoi-trang": "Trang phục màu đỏ & Áo in họa tiết năm mới",
        "gia-dung": "Khay mứt men lam & Cốc sứ tài lộc",
        "phu-kien": "Dây treo đồng xu & Phụ kiện decor Tết",
        "trang-tri": "Tranh liễn xuân & Đèn lồng phòng khách",
        "default": "Đồ decor & Trang trí không gian Tết"
    },
    "quà 8/3": {
        "thoi-trang": "Khăn lụa choàng cổ & Áo thun hoa nhí nữ tính",
        "gia-dung": "Ly sứ in hoa & Bình giữ nhiệt quà tặng",
        "phu-kien": "Túi Tote Canvas & Set phụ kiện quà tặng mẹ",
        "trang-tri": "Khung tranh in hoa & Nến thơm thư giãn",
        "default": "Set quà tặng phái đẹp & Mỹ phẩm thủ công"
    },
    "quà valentine": {
        "thoi-trang": "Áo thun cặp đôi & Đồ đôi dạo phố",
        "gia-dung": "Cặp ly sứ tình nhân & Bình nước đôi",
        "phu-kien": "Vòng tay đôi & Móc khóa kỷ niệm",
        "trang-tri": "Tranh in kỷ niệm tình yêu & Khung ảnh",
        "default": "Set quà socola & Đồ kỷ niệm tình nhân"
    },
    "mùa đông": {
        "thoi-trang": "Quần áo dày, áo phao chần bông & Đồ nỉ giữ nhiệt",
        "gia-dung": "Bình giữ nhiệt inox & Cốc uống trà nóng",
        "phu-kien": "Khăn len, găng tay & Tất ấm mùa lạnh",
        "trang-tri": "Chăn lông cừu & Đèn ngủ ánh sáng ấm",
        "default": "Đồ giữ nhiệt & Phụ kiện mùa đông"
    },
    "quà 20/10": {
        "thoi-trang": "Khăn dạ mỏng thu đông & Áo thun thanh lịch",
        "gia-dung": "Bình giữ nhiệt văn phòng & Cốc sứ in thông điệp",
        "phu-kien": "Túi xách dạo phố & Set quà tặng phụ nữ",
        "trang-tri": "Nến thơm hoa khô & Tranh treo tường nhẹ nhàng",
        "default": "Quà tặng tri ân phụ nữ Việt Nam"
    },
    "quà 20/11": {
        "thoi-trang": "Khăn choàng cổ trang nhã cho thầy cô",
        "gia-dung": "Cốc sứ tri ân & Bình giữ nhiệt cao cấp",
        "phu-kien": "Bút ký kim loại & Sổ tay bìa da may chỉ",
        "trang-tri": "Tranh chữ tri ân & Bảng gỗ khắc laser",
        "default": "Quà tặng tri ân Thầy Cô giáo"
    },
    "áo đồng phục": {
        "thoi-trang": "Áo thun polo, áo nỉ nhóm & Áo lớp phong cách GenZ",
        "gia-dung": "Bộ cốc in logo nhóm / công ty",
        "phu-kien": "Mũ lưỡi trai đồng phục & Balo nhóm",
        "trang-tri": "Cờ lưu niệm & Bảng vinh danh",
        "default": "Đồng phục nhóm & Phụ kiện teambuilding"
    }
}


class MarketMiningService:
    """Thuật toán khai phá số liệu thị trường thực tế từ MongoDB."""

    @staticmethod
    def detect_category_key(category_slug: Optional[str]) -> str:
        if not category_slug:
            return "thoi-trang"
        s = category_slug.lower()
        if any(x in s for x in ["ao", "quan", "vay", "dam", "thoi-trang", "apparel", "sweater", "jacket"]):
            return "thoi-trang"
        if any(x in s for x in ["ly", "tach", "nha-cua", "gia-dung", "bep", "home", "mug"]):
            return "gia-dung"
        if any(x in s for x in ["tui", "phu-kien", "trang-suc", "giay", "leather", "wallet", "bag"]):
            return "phu-kien"
        if any(x in s for x in ["trang-tri", "tranh", "khung"]):
            return "trang-tri"
        return "thoi-trang"

    @classmethod
    def mine_seasonal_cluster(
        cls,
        keyword: str,
        category_slug: Optional[str] = None
    ) -> Dict[str, Any]:
        """Khai phá nhóm hàng cụ thể từ MongoDB theo danh mục của seller."""
        cat_key = cls.detect_category_key(category_slug)
        kw_norm = (keyword or "").strip().lower()

        # 1. Xác định tên nhóm hàng chuyên biệt theo ngữ cảnh ngành hàng & mùa vụ
        clusters_for_kw = SEASONAL_ATTRIBUTE_CLUSTERS.get(kw_norm, {})
        cluster_name = clusters_for_kw.get(cat_key) or clusters_for_kw.get("default")
        if not cluster_name:
            if cat_key == "thoi-trang":
                cluster_name = f"Trang phục & Phụ kiện thời trang đón {keyword}"
            elif cat_key == "gia-dung":
                cluster_name = f"Đồ gia dụng & Cốc ly quà tặng dịp {keyword}"
            elif cat_key == "phu-kien":
                cluster_name = f"Phụ kiện & Quà tặng tiện ích {keyword}"
            else:
                cluster_name = f"Sản phẩm thịnh hành theo mùa {keyword}"

        # 2. Truy vấn dữ liệu số thực tế từ mart_competitor
        target_cats = CATEGORY_TO_MARTS.get(cat_key, ["apparel"])
        comp_coll = db()["mart_competitor"]

        # Tìm các listing bán chạy trong cùng danh mục
        loc: Dict[str, Any] = {"category_id": {"$in": target_cats}}
        kw_words = [w for w in kw_norm.split() if len(w) > 2]
        if kw_words:
            regex_p = "|".join(kw_words)
            loc["$or"] = [
                {"title": {"$regex": regex_p, "$options": "i"}},
                {"tags": {"$in": kw_words}}
            ]

        rows = list(comp_coll.find(loc, {
            "title": 1, "revenue_90d_vnd": 1, "est_sales_90d": 1, "tags": 1
        }).sort("est_sales_90d", -1).limit(10))

        # Fallback nếu bộ lọc từ khóa quá hẹp: lấy top bán chạy nhất của toàn category đó
        if len(rows) < 3:
            rows = list(comp_coll.find(
                {"category_id": {"$in": target_cats}},
                {"title": 1, "revenue_90d_vnd": 1, "est_sales_90d": 1, "tags": 1}
            ).sort("est_sales_90d", -1).limit(8))

        # 3. Tính toán dải giá trung vị thật của thị trường
        unit_prices: List[float] = []
        sample_listings: List[Dict[str, Any]] = []

        for r in rows:
            rev = r.get("revenue_90d_vnd") or 0
            sales = r.get("est_sales_90d") or 1
            avg_p = round(rev / max(1, sales))
            if 30000 <= avg_p <= 2000000:
                unit_prices.append(avg_p)
                sample_listings.append({
                    "title": r.get("title", ""),
                    "price": avg_p,
                    "sales": sales
                })

        unit_prices.sort()
        if unit_prices:
            median_price = unit_prices[len(unit_prices) // 2]
            p_min = unit_prices[max(0, int(len(unit_prices) * 0.2))]
            p_max = unit_prices[min(len(unit_prices) - 1, int(len(unit_prices) * 0.8))]
        else:
            if cat_key == "thoi-trang":
                median_price, p_min, p_max = 220000, 160000, 350000
            elif cat_key == "gia-dung":
                median_price, p_min, p_max = 130000, 85000, 240000
            else:
                median_price, p_min, p_max = 95000, 50000, 180000

        # Làm tròn đẹp
        p_min = int(round(p_min / 5000.0) * 5000)
        p_max = int(round(p_max / 5000.0) * 5000)

        # 4. Trích xuất top tags đang có cầu cao từ niche_score
        niche_coll = db()["niche_score"]
        niches = list(niche_coll.find(
            {"category_id": {"$in": target_cats}},
            {"keyword": 1, "gap_score": 1, "trend": 1}
        ).sort("gap_score", -1).limit(5))

        top_attributes = [n["keyword"] for n in niches if n.get("keyword")]

        return {
            "cluster_name": cluster_name,
            "category_key": cat_key,
            "target_marts": target_cats,
            "median_price": median_price,
            "market_price_range": f"{p_min:,}đ - {p_max:,}đ".replace(",", "."),
            "price_min": p_min,
            "price_max": p_max,
            "top_attributes": top_attributes,
            "sample_listings": sample_listings[:4],
        }
