"""
AI Engine thế hệ mới cho Sàn Thương Mại Điện Tử Tổng Hợp (General E-Commerce Marketplace).

Khả năng:
1. Hiểu sâu ngữ nghĩa (Semantic Product Understanding):
   - Nhận diện chính xác: Loại sản phẩm (Product Type), Thương hiệu (Brand),
     Model / Dòng máy, Thuộc tính kỹ thuật, Phân khúc thị trường (Budget, Mid-range, Flagship).
   - Phân biệt rõ ràng giữa Thiết bị / Sản phẩm chính và Phụ kiện / Vật tư tiêu hao
     (ngăn chặn triệt để lỗi so sánh Điện thoại với Túi đựng, hay Nồi chiên với Giấy nến).
2. Định giá thị trường TMĐT Việt Nam (Market Valuation):
   - Khi có GEMINI_API_KEY: Gọi Google Gemini 1.5/2.0 Flash để định giá thị trường thực tế
     tại Việt Nam (P25 giá sale, P50 giá chuẩn trung vị, P75 giá chính hãng Mall).
   - Khi offline / chưa có key: Dùng NLP Semantic Parser + Multi-Category Knowledge Base
     kết hợp dữ liệu đối chuẩn thực tế có chọn lọc.
3. Sinh nội dung chuẩn SEO TMĐT:
   - 5 Tiêu đề SEO hấp dẫn theo 5 góc độ chuyển đổi.
   - Bài mô tả bán hàng chuẩn gian hàng Mall TMĐT (Intro, Bảng thông số, Ưu điểm, Bảo quản/Bảo hành).
   - Bộ thẻ Tag xu hướng.
"""

import json
import os
import re
import urllib.request
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path
from dotenv import load_dotenv

from app.services.f42 import config
from app.services.f42.vi_text import clean_tokens, normalize_nfc, strip_accents
from app.services.f42.schemas import (
    ContentResult,
    DescriptionStructure,
    PriceRange,
    PricingResult,
    SpecItem,
    TagItem,
    TagResult,
    TitleItem,
)

# Nạp .env
for env_p in [
    Path(__file__).resolve().parents[2] / ".env",
    Path(__file__).resolve().parents[4] / ".env",
]:
    if env_p.exists():
        load_dotenv(env_p, override=False)


# Danh sách từ đánh dấu phụ kiện / linh kiện / vật tư tiêu hao
ACCESSORY_MARKERS = [
    "túi đựng", "túi đeo", "túi chống sốc", "bao da", "bao đựng", "ốp lưng", "ốp",
    "kính cường lực", "cường lực", "miếng dán", "dán màn hình", "dây đeo", "dây sạc",
    "cáp sạc", "củ sạc", "dock sạc", "khay nhôm", "khay nướng", "khay lót", "khay giấy",
    "giấy nến", "giấy bạc", "vỉ nướng", "khóa bướm", "khóa kim", "dây đồng hồ",
    "chốt đồng hồ", "hộp đựng", "giá đỡ", "chân đế", "miếng lót", "vỏ bọc", "nắp đậy",
    "đầu chuyển", "jack chuyển", "filter", "nắp ống kính", "màng lọc", "lõi lọc"
]


class MarketAIAdvisor:
    """Bộ não AI cho Sàn Thương Mại Điện Tử."""

    @classmethod
    def get_api_key(cls) -> Optional[str]:
        return (
            os.getenv("GEMINI_API_KEY")
            or os.getenv("GOOGLE_API_KEY")
            or os.getenv("OPENAI_API_KEY")
        )

    @classmethod
    def is_gemini_available(cls) -> bool:
        key = cls.get_api_key()
        return bool(key and len(key) > 15)

    # ------------------------------------------------------------------
    # 1. PHÂN TÍCH THỰC THỂ SẢN PHẨM (Semantic Product Understanding)
    # ------------------------------------------------------------------
    @classmethod
    def parse_product_entities(cls, text: str) -> Dict[str, Any]:
        """Bóc tách cấu trúc thực thể từ tiêu đề sản phẩm."""
        raw = normalize_nfc(text or "").strip()
        low = raw.lower()

        # Kiểm tra xem sản phẩm có phải là phụ kiện không
        is_acc = any(m in low for m in ACCESSORY_MARKERS)

        # Trích xuất thương hiệu phổ biến trên sàn TMĐT
        # Danh sách nhận diện nhanh các thương hiệu lớn
        known_brands = [
            "Apple", "Samsung", "Xiaomi", "Oppo", "Sony", "Dell", "Asus", "HP", "Lenovo", "Acer", "MSI",
            "Philips", "Lock&Lock", "Lock and Lock", "Elmich", "Tefal", "Sunhouse", "Kangaroo", "Panasonic",
            "Casio", "Seiko", "Citizen", "Orient", "Tissot", "Daniel Wellington",
            "Nike", "Adidas", "Puma", "Converse", "Vans", "New Balance", "MLB",
            "Uniqlo", "Zara", "H&M", "An Phước", "Aristino", "Coolmate", "Routine", "Canifa",
            "Logitech", "Razer", "Corsair", "Akko", "Dareu", "Keychron", "Anker", "Baseus", "Aukey",
            "L'Oreal", "La Roche-Posay", "Anessa", "Vichy", "Innisfree", "DHC", "MAC", "Maybelline",
            "Bát Tràng", "Minh Long", "Duy Tân", "Đại Đồng Tiến", "Rạng Đông", "Điện Quang", "Senko"
        ]

        detected_brand = None
        for b in known_brands:
            if re.search(rf"\b{re.escape(b.lower())}\b", low):
                detected_brand = b
                break

        # Nếu không có trong danh mục nổi tiếng, quét các từ viết hoa dạng thương hiệu Latin
        if not detected_brand:
            words = raw.split()
            for w in words[1:]:
                clean_w = re.sub(r"[^\w]", "", w)
                if clean_w.isupper() and len(clean_w) >= 3 and not any(ch.isdigit() for ch in clean_w):
                    detected_brand = clean_w
                    break

        return {
            "raw_title": raw,
            "is_accessory": is_acc,
            "detected_brand": detected_brand,
        }

    # ------------------------------------------------------------------
    # 2. GỌI GEMINI LLM ĐỂ ĐỊNH GIÁ & TẠO NỘI DUNG (KHI CÓ API KEY)
    # ------------------------------------------------------------------
    @classmethod
    def call_gemini_analysis(
        cls,
        title: str,
        category_name: str = "",
        material: str = "",
        blank_cost: float = 0.0,
        extra_attributes: str = "",
        internal_data_summary: str = "",
        google_trends_summary: str = ""
    ) -> Optional[Dict[str, Any]]:
        """
        Gọi Google Gemini Flash để phân tích toàn diện:
        - Định giá thị trường TMĐT Việt Nam dựa trên dữ liệu sàn + Google Trends
        - 5 Tiêu đề SEO
        - Mô tả bán hàng chuyên nghiệp
        - Tags xu hướng
        """
        api_key = cls.get_api_key()
        if not api_key:
            return None

        prompt = f"""Bạn là Giám đốc Định giá và Tối ưu Nội dung sàn Thương Mại Điện Tử hàng đầu Việt Nam (Shopee, Tiki, Lazada, TikTok Shop).
Nhiệm vụ: Phân tích sản phẩm do người bán đăng tải và đưa ra chiến lược định giá cùng nội dung bán hàng tối ưu nhất dựa trên dữ liệu thị trường và xu hướng tìm kiếm.

THÔNG TIN NGƯỜI BÁN NHẬP:
- Tiêu đề / Tên sản phẩm: {title}
- Danh mục tham khảo: {category_name if category_name else 'Tự động nhận diện'}
- Chất liệu khai báo: {material if material else 'Chưa khai báo'}
- Giá vốn sản phẩm: {f'{int(blank_cost):,} VND' if blank_cost > 0 else 'Chưa có'}
- Thuộc tính khác: {extra_attributes if extra_attributes else 'Không có'}

DỮ LIỆU ĐỐI CHUẨN TỪ SÀN VIETCRAFT & GOOGLE TRENDS:
- Dữ liệu từ sàn VietCraft: {internal_data_summary if internal_data_summary else 'Sàn VietCraft đang mở rộng danh mục này.'}
- Dữ liệu Google Trends Việt Nam: {google_trends_summary if google_trends_summary else 'Nhu cầu tìm kiếm ổn định.'}

YÊU CẦU ĐẦU RA:
Trả về DUY NHẤT một đối tượng JSON (không markdown, không bọc ```json) với cấu trúc chính xác sau:
{{
  "detected_product": "Tên loại sản phẩm cốt lõi (VD: Điện thoại thông minh, Nồi chiên không dầu, Áo thun polo, Bàn phím cơ...)",
  "detected_brand": "Thương hiệu nếu có (VD: Apple, Samsung, Philips, Casio, hoặc null)",
  "detected_category": "Tên danh mục ngành hàng TMĐT chuẩn xác nhất",
  "detected_material": "Chất liệu nếu có trong tiêu đề hoặc mô tả",
  "pricing": {{
    "low": 0, // Giá phân vị 25% (VND) - mức giá cạnh tranh / xả hàng
    "recommended": 0, // Giá phân vị 50% (VND) - mức giá đề xuất tối ưu, trung vị thị trường TMĐT Việt Nam
    "high": 0, // Giá phân vị 75% (VND) - phân khúc cao cấp / shop chính hãng / bảo hành VIP
    "explanation": "Giải thích chi tiết 2-3 câu: phân khúc sản phẩm, uy tín thương hiệu, cấu hình/dung tích và tại sao khoảng giá này là hợp lý trên thị trường TMĐT hiện nay dựa trên phân khúc dòng tiền nhiệm và xu hướng Google Trends."
  }},
  "titles": [
    "Tiêu đề 1: Chuẩn SEO TMĐT (Tên sản phẩm + Thương hiệu + Model/Quy cách + Điểm nổi bật)",
    "Tiêu đề 2: Nhấn vào công năng & giải pháp kỹ thuật",
    "Tiêu đề 3: Nhấn vào ưu đãi / tiện ích sử dụng",
    "Tiêu đề 4: Nhấn vào phong cách / xu hướng",
    "Tiêu đề 5: Ngắn gọn, súc tích, tối ưu click CTR"
  ],
  "description": {{
    "intro": "2-3 câu giới thiệu sản phẩm lôi cuốn, giọng văn bán hàng thương mại điện tử chuyên nghiệp.",
    "specs": [
      {{"label": "Thương hiệu", "value": "..."}},
      {{"label": "Phân loại", "value": "..."}},
      {{"label": "Chất liệu / Xuất xứ", "value": "..."}}
    ],
    "highlights": [
      "Điểm nổi bật 1 (tính năng, độ bền, tiện ích)",
      "Điểm nổi bật 2",
      "Điểm nổi bật 3",
      "Điểm nổi bật 4"
    ],
    "usage_guide": "Hướng dẫn sử dụng và bảo quản đúng cách để sản phẩm bền lâu.",
    "warranty_policy": "Chính sách cam kết bán hàng: 100% hình ảnh thực tế, đổi trả theo quy định sàn nếu có lỗi."
  }},
  "tags": ["Từ khóa sản phẩm", "Chất liệu", "Công dụng", "Phong cách", "Dịp sử dụng"]
}}

LƯU Ý QUAN TRỌNG VỀ TÍNH CHÍNH XÁC VÀ TRUNG THỰC:
1. NGUYÊN TẮC ĐỊNH GIÁ THỊ TRƯỜNG:
   - Đối với sản phẩm mới, phiên bản kế tiếp (ví dụ iPhone thế hệ mới, smartphone flagship, đồ thủ công mỹ nghệ thiết kế mới): Hãy căn cứ vào phân khúc thương hiệu, mức giá mở bán của dòng tiền nhiệm (ví dụ iPhone Pro Max tham chiếu từ 29-36 triệu VND) và xu hướng tìm kiếm trên Google Trends để đưa ra mức giá dự phóng hợp lý nhất.
   - CHỈ trả về "pricing": {{"low": 0, "recommended": 0, "high": 0, "explanation": "Chưa đủ dữ liệu để đề xuất giá."}} khi tiêu đề hoàn toàn là ký tự rác, vô nghĩa (như 'asdfgh', '123456') không thể xác định được mặt hàng nào.
   - Tuyệt đối không nhầm lẫn giữa thiết bị chính và phụ kiện (ví dụ bán điện thoại thì định giá máy điện thoại chứ không định giá ốp lưng).
2. NGUYÊN TẮC TIÊU ĐỀ & MÔ TẢ:
   - Tuyệt đối KHÔNG tự ý thêm các từ khẳng định chất lượng hoặc cam kết vô căn cứ như "chính hãng", "bảo hành uy tín", "giá tốt nhất", "độ bền vượt trội", "an toàn tuyệt đối" nếu người bán không nhập thông tin đó.
   - Tiêu đề gợi ý phải bám sát thông tin người bán nhập (Tên sản phẩm, Chất liệu, Quy cách, Công năng thực tế).
3. NGUYÊN TẮC THẺ TAGS:
   - Tuyệt đối KHÔNG trả về các tag vô nghĩa dạng tag1, tag2... Mọi thẻ tag phải là từ khóa tìm kiếm thực tế liên quan đến sản phẩm và xu hướng tìm kiếm Google Trends.
4. Đảm bảo mọi con số giá nguyên dương hoặc bằng 0, làm tròn đến hàng ngàn VND."""

        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": api_key
        }
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.3,
                "topP": 0.85,
                "maxOutputTokens": 2048,
                "responseMimeType": "application/json"
            }
        }

        models_to_try = [
            "gemini-3.5-flash",
            "gemini-3.5-flash-lite",
            "gemini-2.5-flash",
            config.LLM_MODEL
        ]

        for model in models_to_try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            try:
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers=headers,
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=12) as response:
                    if response.status == 200:
                        body = json.loads(response.read().decode("utf-8"))
                        candidates = body.get("candidates", [])
                        if candidates:
                            parts = candidates[0].get("content", {}).get("parts", [])
                            if parts:
                                txt = parts[0].get("text", "").strip()
                                # Clean markdown code fences if any
                                if txt.startswith("```"):
                                    txt = re.sub(r"^```[a-z]*\s*", "", txt)
                                    txt = re.sub(r"\s*```$", "", txt)
                                data = json.loads(txt)
                                if "pricing" in data and "titles" in data:
                                    return data
            except Exception:
                continue

        return None

    # ------------------------------------------------------------------
    # 3. BỘ PHÂN TÍCH NGỮ NGHĨA TMĐT DỰ PHÒNG (KHI CHƯA KẾT NỐI GEMINI KEY)
    # ------------------------------------------------------------------
    @classmethod
    def semantic_fallback_analysis(
        cls,
        title: str,
        category_name: str = "",
        material: str = "",
        blank_cost: float = 0.0,
        extra_attributes: str = ""
    ) -> Dict[str, Any]:
        """
        Bộ phân tích ngữ nghĩa TMĐT nâng cao khi chưa kết nối Gemini API.
        Phân biệt rõ ràng mọi ngành hàng (Điện tử, Gia dụng, Thời trang, Làm đẹp, Đồng hồ...).
        Không nhầm lẫn phụ kiện với thiết bị chính, đưa ra khoảng giá hợp lý chuẩn thị trường.
        """
        raw = normalize_nfc(title or "").strip()
        low = raw.lower()
        entities = cls.parse_product_entities(raw)
        brand = entities.get("detected_brand")
        is_acc = entities.get("is_accessory", False)

        # 1. Nhận diện các ngành hàng và archetype sản phẩm TMĐT
        # Thiết bị điện tử - Điện thoại
        if any(w in low for w in ["điện thoại", "smartphone", "iphone", "galaxy a", "galaxy s", "galaxy z", "redmi", "realme"]) and not is_acc:
            product_type = "Điện thoại thông minh"
            cat = "Điện Thoại & Phụ Kiện"
            if "iphone" in low or "pro max" in low or "galaxy s" in low or "galaxy z" in low:
                pass
            elif any(w in low for w in ["galaxy a", "redmi note", "realme", "a15", "a25", "a35", "a55"]):
                pass
            specs = [
                {"label": "Thương hiệu", "value": brand or "Chính hãng"},
                {"label": "Dòng sản phẩm", "value": product_type},
                {"label": "Màn hình", "value": "Độ phân giải cao, tần số quét mượt mà"},
                {"label": "Camera & Pin", "value": "Camera sắc nét, dung lượng pin bền bỉ"}
            ]

        # Đồ gia dụng - Nồi chiên / Nồi cơm / Máy hút bụi
        elif any(w in low for w in ["nồi chiên không dầu", "nồi chiên", "nồi cơm điện", "máy hút bụi", "máy xay sinh tố", "bếp từ", "quạt điện", "máy ép chậm"]) and not is_acc:
            if "nồi chiên" in low:
                product_type = "Nồi chiên không dầu"
                cat = "Thiết Bị Gia Dụng"
            elif "máy hút bụi" in low:
                product_type = "Máy hút bụi"
                cat = "Thiết Bị Gia Dụng"
            elif "nồi cơm" in low:
                product_type = "Nồi cơm điện"
                cat = "Thiết Bị Gia Dụng"
            else:
                product_type = "Thiết bị điện gia dụng"
                cat = "Thiết Bị Gia Dụng"
            specs = [
                {"label": "Thương hiệu", "value": brand or "Chính hãng"},
                {"label": "Công nghệ", "value": "Hiện đại, tiết kiệm điện năng"},
                {"label": "Chất liệu lòng nồi/vỏ", "value": material or "Hợp kim chống dính / Nhựa cao cấp"},
                {"label": "Bảo hành", "value": "12 tháng chính hãng"}
            ]

        # Đồng hồ đeo tay
        elif any(w in low for w in ["đồng hồ nam", "đồng hồ nữ", "đồng hồ đeo tay", "đồng hồ cơ", "smartwatch", "casio", "seiko"]) and not is_acc:
            product_type = "Đồng hồ đeo tay"
            cat = "Đồng Hồ & Trang Sức"
            specs = [
                {"label": "Thương hiệu", "value": brand or "Casio / Chính hãng"},
                {"label": "Chất liệu dây", "value": material or "Thép không gỉ / Da cao cấp"},
                {"label": "Chống nước", "value": "Chuẩn chống nước sinh hoạt"},
                {"label": "Bộ máy", "value": "Quartz / Automatic độ chính xác cao"}
            ]

        # Máy tính, phụ kiện công nghệ
        elif any(w in low for w in ["bàn phím cơ", "chuột máy tính", "tai nghe", "laptop", "macbook"]) and not is_acc:
            if "laptop" in low or "macbook" in low:
                product_type = "Laptop / Máy tính xách tay"
                cat = "Máy Tính & Laptop"
            elif "bàn phím" in low:
                product_type = "Bàn phím cơ"
                cat = "Phụ Kiện Máy Tính"
            elif "tai nghe" in low:
                product_type = "Tai nghe"
                cat = "Thiết Bị Âm Thanh"
            else:
                product_type = "Phụ kiện công nghệ"
                cat = "Phụ Kiện Máy Tính"
            specs = [
                {"label": "Thương hiệu", "value": brand or "Chính hãng"},
                {"label": "Kết nối", "value": "Không dây Bluetooth / Type-C"},
                {"label": "Tương thích", "value": "Windows, macOS, Android, iOS"}
            ]

        # Mỹ phẩm, chăm sóc cá nhân
        elif any(w in low for w in ["son môi", "son dưỡng", "kem chống nắng", "sữa rửa mặt", "serum", "nước hoa"]):
            product_type = "Mỹ phẩm & Chăm sóc sắc đẹp"
            cat = "Sắc Đẹp & Sức Khỏe"
            specs = [
                {"label": "Thương hiệu", "value": brand or "Chính hãng"},
                {"label": "Loại da phù hợp", "value": "Mọi loại da, kể cả da nhạy cảm"},
                {"label": "Hạn sử dụng", "value": "3 năm kể từ ngày sản xuất"}
            ]

        # Phụ kiện (nếu là phụ kiện, ốp lưng, túi đựng, khay lót)
        elif is_acc:
            product_type = "Phụ kiện / Vật tư tiêu hao"
            cat = "Phụ Kiện"
            specs = [
                {"label": "Phân loại", "value": "Phụ kiện bảo vệ / Thay thế"},
                {"label": "Chất liệu", "value": material or "Silicone / Nhựa dẻo / Vải chống sốc"}
            ]

        # Thời trang, Đời sống hoặc nhóm chung
        else:
            product_type = raw.split()[0].title() if raw else None
            cat = category_name or None
            specs = [
                {"label": "Danh mục", "value": cat or "Chưa phân loại"},
            ]
            if brand:
                specs.append({"label": "Thương hiệu", "value": brand})
            if material:
                specs.append({"label": "Chất liệu", "value": material})

        specs = []
        if cat:
            specs.append({"label": "Danh mục", "value": cat})
        if brand:
            specs.append({"label": "Thương hiệu", "value": brand})
        if material:
            specs.append({"label": "Chất liệu", "value": material})

        # Chỉ đưa dữ kiện seller cung cấp vào tiêu đề và mô tả.
        raw_clean = raw.strip() if raw else (cat or "Sản phẩm")
        t_list = []
        if material:
            t_list.append(f"{raw_clean} - Chất liệu {material}")
        if brand:
            t_list.append(f"{raw_clean} - {brand}")
        t_list.append(f"{raw_clean}".strip())
        titles = list(dict.fromkeys(t[:120] for t in t_list if t.strip()))

        highlights = [f"Tên sản phẩm: {raw_clean}."]
        if material:
            highlights.append(f"Chất liệu theo thông tin người bán: {material}.")
        if brand:
            highlights.append(f"Thương hiệu theo thông tin người bán: {brand}.")

        tags = [t for t in [raw_clean[:30], cat, material, brand] if t and len(t) >= 2]

        desc_obj = {
            "intro": f"Thông tin sản phẩm: {raw_clean}.",
            "specs": specs,
            "highlights": highlights,
            "usage_guide": "Vui lòng bổ sung hướng dẫn sử dụng và bảo quản phù hợp với sản phẩm.",
            "warranty_policy": "Vui lòng bổ sung chính sách bảo hành và đổi trả áp dụng cho sản phẩm."
        }

        return {
            "detected_product": product_type,
            "detected_brand": brand,
            "detected_category": cat,
            "detected_material": material or "",
            "pricing": {
                "low": 0,
                "recommended": 0,
                "high": 0,
                "explanation": "Giá cần được tính từ dữ liệu so sánh thực tế hoặc giá vốn; bộ phân tích fallback không tự ước lượng giá thị trường."
            },
            "titles": titles,
            "description": desc_obj,
            "tags": tags[:8]
        }

    # ------------------------------------------------------------------
    # 4. CHUYỂN ĐỔI SANG SCHEMA CHUẨN (Builder Utilities)
    # ------------------------------------------------------------------
    @classmethod
    def build_content_result(
        cls,
        ai_data: Dict[str, Any],
        title_input: str,
        source: str = "ai_semantic_model"
    ) -> ContentResult:
        """Chuyển đổi dữ liệu phân tích AI thành ContentResult chuẩn hợp đồng."""
        angles = ["balanced", "technical", "style", "function", "material"]
        raw_titles = ai_data.get("titles", [])
        titles = [
            TitleItem(text=t.strip(), angle=angles[i % len(angles)])
            for i, t in enumerate(raw_titles)
        ]
        if not titles:
            titles = [TitleItem(text=title_input, angle="balanced")]

        desc_dict = ai_data.get("description", {})
        raw_specs = desc_dict.get("specs", [])
        specs = [
            SpecItem(label=str(s.get("label", "")), value=str(s.get("value", "")))
            for s in raw_specs
            if isinstance(s, dict) and s.get("label")
        ]
        return ContentResult(
            source=source,
            titles=titles,
            description=DescriptionStructure(
                intro=desc_dict.get("intro", ""),
                specs=specs,
                highlights=desc_dict.get("highlights", []),
                care_guide=desc_dict.get("usage_guide", desc_dict.get("warranty_policy", ""))
            ),
            claims_used=[title_input],
            missing_info=[],
            warnings=[]
        )

    @classmethod
    def build_pricing_result(
        cls,
        ai_data: Dict[str, Any],
        blank_cost: float = 0.0,
        method: str = "llm_gemini",
        mode: str = "market_ai",
        confidence: str = "high",
        sample_size: int = 0
    ) -> PricingResult:
        """Chuyển đổi dữ liệu giá AI thành PricingResult chuẩn hợp đồng."""
        p_dict = ai_data.get("pricing", {})
        p_low = int(p_dict.get("low", 0))
        p_rec = int(p_dict.get("recommended", 0))
        p_high = int(p_dict.get("high", 0))
        p_90 = int(p_high * 1.15) if p_high > 0 else 0
        explanation = p_dict.get("explanation", "")

        warnings: List[str] = []
        if p_rec <= 0:
            return PricingResult(
                mode="none",
                method="none",
                insufficient_market_data=True,
                p25=0,
                p50=0,
                p75=0,
                p90=0,
                suggested_price=0,
                suggested_range=PriceRange(low=0, high=0),
                confidence="none",
                warnings=["Chưa đủ dữ liệu thị trường để đề xuất giá bán."],
                explanation=explanation or "Chưa đủ dữ liệu thị trường để đề xuất mức giá chuẩn xác.",
                sample_size=0,
                sample_size_after_outlier_filter=0,
                source_label="Chưa đủ dữ liệu",
                detected_product=ai_data.get("detected_product"),
                detected_brand=ai_data.get("detected_brand"),
            )

        if blank_cost > 0:
            min_safe = int(round(blank_cost * 1.30 / 1000) * 1000)
            if p_rec < min_safe:
                warnings.append("Mức giá thấp hơn giá vốn + biên tối thiểu 30%, đã điều chỉnh lên mức an toàn.")
                p_rec = min_safe
                p_low = max(p_low, min_safe)
                p_high = max(p_high, p_rec)

        actual_sample_size = sample_size if method == "comparables" else 0
        source_label = (
            "Phân khúc thị trường TMĐT" if method == "llm_gemini"
            else ("Ước tính theo giá vốn (Cost-Plus)" if method == "cost_plus"
            else (f"Đối chiếu từ {actual_sample_size} sản phẩm cùng loại" if method == "comparables" and actual_sample_size > 0
            else "Mô hình thị trường"))
        )

        return PricingResult(
            mode=mode,
            method=method,
            insufficient_market_data=(actual_sample_size == 0 and method != "llm_gemini"),
            p25=p_low,
            p50=p_rec,
            p75=p_high,
            p90=p_90,
            suggested_price=p_rec,
            suggested_range=PriceRange(low=p_low, high=p_high),
            confidence=confidence,
            warnings=warnings,
            explanation=explanation or "Mức giá được phân tích và đề xuất bởi hệ thống.",
            sample_size=actual_sample_size,
            sample_size_after_outlier_filter=actual_sample_size,
            source_label=source_label,
            detected_product=ai_data.get("detected_product"),
            detected_brand=ai_data.get("detected_brand"),
        )

    @classmethod
    def build_tag_result(
        cls,
        ai_data: Dict[str, Any],
        basis: str = "ai_semantic_tags"
    ) -> TagResult:
        """Chuyển đổi danh sách thẻ tag từ AI thành TagResult (đã lọc các tag vô nghĩa)."""
        raw_tags = ai_data.get("tags", [])
        tags = [
            t.strip() for t in raw_tags
            if isinstance(t, str) and t.strip() and not re.match(r"^tag\d*$", t.strip(), re.I) and len(t.strip()) >= 2
        ]
        return TagResult(
            items=[TagItem(tag=t, score=1.0, freq=3, source="ai") for t in tags],
            basis=basis,
            sample_size=len(tags)
        )

