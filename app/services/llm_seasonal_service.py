from pathlib import Path
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv

from app.services import llm

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
if ENV_FILE.exists():
    load_dotenv(ENV_FILE)


class LLMSeasonalService:
    """Tầng suy luận và sinh ý tưởng sản phẩm từ dữ liệu Data-Mining."""

    @classmethod
    def generate_recommendations(
        cls,
        keyword: str,
        category_slug: Optional[str],
        mined: Dict[str, Any],
        use_llm: bool = True,
    ) -> Dict[str, Any]:
        """Tạo gợi ý sản phẩm kết hợp giữa LLM và số liệu sàn thật."""
        # 1. LLM dùng chung (OpenAI chính, hết hạn mức/lỗi thì Gemini); không có khoá hoặc lỗi thì tổng hợp từ số liệu sàn
        if use_llm:
            res = llm.generate_json([{"text": cls._build_prompt(keyword, mined)}], timeout_s=15, max_output_tokens=4096,
                                    accept=lambda d: bool(d.get("ready_to_ship_ideas")))
            if res:
                return res

        # 2. Fallback: Bộ tổng hợp thông minh trực tiếp từ dữ liệu Data-Mining sàn thật
        res = cls._synthesize_from_mined_data(keyword, mined)
        res["ai_model"] = "VietCraft Market Mining v1.0"
        return res

    @classmethod
    def _build_prompt(cls, keyword: str, mined: Dict[str, Any]) -> str:
        """Prompt gửi LLM (OpenAI hoặc Gemini, qua app.services.llm)."""
        return (
            f"Bạn là chuyên gia phân tích thị hiếu và nguồn hàng TMĐT tại Việt Nam.\n"
            f"DỮ LIỆU KHAI PHÁ THỰC TẾ TỪ SÀN VIETCRAFT:\n"
            f"- Dịp lễ / Cao điểm: '{keyword}'\n"
            f"- Nhóm hàng bứt phá nhu cầu: '{mined.get('cluster_name')}'\n"
            f"- Dải giá chốt đơn phổ biến trên sàn: {mined.get('market_price_range')}\n"
            f"NGUYÊN TẮC BẮT BUỘC:\n"
            f"1. Dùng 100% TIẾNG VIỆT tự nhiên thuần túy, TUYỆT ĐỐI KHÔNG chêm tiếng Anh (không dùng các từ như 'perceived value', 'hook', 'vibe', 'cyberpunk', v.v.).\n"
            f"2. Gợi ý PHẢI ĐÚNG với chủ đề mùa '{keyword}':\n"
            f"   - Nếu là Giáng sinh (Noel): Chỉ gợi ý áo ấm, đồ tiệc, họa tiết cây thông, tuần lộc, bông tuyết, quà tặng mùa đông. TUYỆT ĐỐI KHÔNG gợi ý họa tiết Tết (như Mã Đáo Thành Công, câu đối, hoa đào, hoa mai, thần tài) vào mùa Noel.\n"
            f"   - Nếu là Tết: Mới gợi ý áo dài cách tân, họa tiết may mắn, câu đối, hoa mai hoa đào.\n"
            f"3. KHÔNG tự đưa ra con số (%, giá, lợi nhuận, số lượng) nếu con số đó không có trong dữ liệu ở trên.\n\n"
            f"YÊU CẦU: Hãy phân tích chuyên sâu xu hướng thị hiếu năm nay và trả về JSON thuần túy (không markdown) với cấu trúc chi tiết, thuyết phục người bán:\n"
            f"{{\n"
            f'  "ready_to_ship_ideas": [\n'
            f'    {{\n'
            f'      "title": "Tên sản phẩm thương mại cụ thể nên nhập",\n'
            f'      "category": "{mined.get("cluster_name")}",\n'
            f'      "market_price_range": "{mined.get("market_price_range")}",\n'
            f'      "why_it_sells": "Động cơ và tâm lý người tiêu dùng sẵn sàng chi tiền dịp này",\n'
            f'      "upsell_bundle_tip": "Gợi ý đóng gói combo / quà tặng kèm để tăng giá trị đơn",\n'
            f'      "sourcing_tip": "Lời khuyên nhập sỉ, kiểm định chất lượng vải/bao bì",\n'
            f'      "target_buyer": "Độ tuổi, giới tính và bối cảnh mua sắm"\n'
            f'    }}\n'
            f'  ],\n'
            f'  "pod_blanks": [\n'
            f'    {{\n'
            f'      "blank_type": "tshirt_unisex|mug_11oz|tote|canvas_stretched",\n'
            f'      "title": "Tên sản phẩm in hoàn thiện",\n'
            f'      "category": "Thời trang|Gia dụng|Phụ kiện",\n'
            f'      "suggested_theme": "Ý tưởng thiết kế hình/chữ theo mốt năm nay",\n'
            f'      "design_hook": "Câu slogan ngắn hoặc phong cách minh họa chạm cảm xúc",\n'
            f'      "color_palette": "Gam màu phôi chủ đạo (ví dụ: Đỏ đô, Trắng kem, Xanh rêu)",\n'
            f'      "target_audience": "Nhóm khách hàng mục tiêu"\n'
            f'    }}\n'
            f'  ]\n'
            f"}}\n"
            f"Mỗi danh sách trả về 3-4 mục cụ thể, giàu tính thực chiến và thuyết phục."
        )

    @classmethod
    def _synthesize_from_mined_data(cls, keyword: str, mined: Dict[str, Any]) -> Dict[str, Any]:
        """Bộ tổng hợp thông minh trực tiếp từ dữ liệu Data-Mining thực tế khi không có LLM API Key."""
        cluster_name = mined.get("cluster_name", "Sản phẩm xu hướng")
        price_range = mined.get("market_price_range")
        samples = mined.get("sample_listings", [])
        cat_key = mined.get("category_key", "thoi-trang")

        ready_ideas = []

        # 1. Sinh các ý tưởng hàng thường từ chính các listing bán chạy được đào từ MongoDB
        if samples:
            for s in samples[:3]:
                title = s.get("title", "")
                p = s.get("price")
                p_str = f"{int(p * 0.9):,}đ - {int(p * 1.25):,}đ".replace(",", ".") if p else price_range
                ready_ideas.append({
                    "title": title,
                    "category": cluster_name,
                    "market_price_range": p_str,
                    "why_it_sells": f"Mặt hàng có người mua trên sàn trong nhóm '{cluster_name}', phù hợp nhu cầu dịp {keyword}.",
                    "expected_profit_margin": None,
                    "upsell_bundle_tip": "Tặng kèm phụ kiện nhỏ hoặc đóng set 2 món để nâng giá trị đơn.",
                    "sourcing_tip": "Đối chiếu giá nhập với dải giá bán trên sàn trước khi nhập số lượng lớn.",
                    "target_buyer": f"Người mua sắm dịp {keyword} trong nhóm hàng {cluster_name}.",
                    "is_estimate": True,
                })

        # Bổ sung ý tưởng fallback cho đủ 4 gợi ý khi không có sample từ DB
        FALLBACK_SLOTS = [
            {
                "title": f"Mặt hàng {cluster_name} phiên bản nâng cấp mùa {keyword}",
                "why_it_sells": f"Tâm lý người mua thích sự mới mẻ, độc bản và tính ứng dụng cao trong mùa {keyword}.",
                "upsell_bundle_tip": "Gợi ý mua làm quà tặng người thân hoặc đồng nghiệp với hộp quà cao cấp.",
                "sourcing_tip": f"Tập trung vào các thuộc tính hot: {', '.join(mined.get('top_attributes', [])[:3]) or 'tiện lợi, bao bì sang trọng'}.",
                "target_buyer": "Nhân viên văn phòng, học sinh sinh viên tìm kiếm trang phục và quà tặng ý nghĩa.",
            },
            {
                "title": f"Set combo {cluster_name} đóng hộp quà tặng dịp {keyword}",
                "why_it_sells": f"Sản phẩm đóng gói sẵn tiện cho người mua làm quà dịp {keyword}.",
                "upsell_bundle_tip": "Đóng set vài món cùng nhóm hàng, kèm thiệp in tên người nhận để tăng giá trị cảm nhận.",
                "sourcing_tip": "Nhập sỉ phôi hộp kraft hoặc hộp cứng có cửa sổ trong, in logo shop để tăng nhận diện thương hiệu.",
                "target_buyer": "Người mua quà cho bạn bè, đồng nghiệp, đối tác dịp lễ.",
            },
            {
                "title": f"{cluster_name} phong cách giới hạn (Limited Edition) chủ đề {keyword}",
                "why_it_sells": f"Sản phẩm giới hạn tạo cảm giác khan hiếm, thúc đẩy quyết định mua nhanh trước khi hết mùa {keyword}.",
                "upsell_bundle_tip": "Dán tem 'Limited', đánh số thứ tự từng sản phẩm và kèm card cảm ơn viết tay để tăng giá trị cảm nhận.",
                "sourcing_tip": "Đặt số lượng nhỏ lần đầu để thử thị trường; tăng đơn nếu bán chạy trong tuần đầu.",
                "target_buyer": "Khách hàng thích sưu tầm, chuộng phong cách độc đáo không đại trà.",
            },
            {
                "title": f"{cluster_name} phiên bản cá nhân hóa theo tên / thông điệp riêng dịp {keyword}",
                "why_it_sells": f"Sản phẩm in tên hoặc câu chúc riêng tạo cảm xúc cá nhân hóa, hợp làm quà dịp {keyword}.",
                "upsell_bundle_tip": "Cho khách tự nhập tên / câu chúc khi đặt hàng; thêm tùy chọn thiệp in kèm để nâng giá trị đơn.",
                "sourcing_tip": "Kết hợp máy in nhiệt hoặc khắc laser tại xưởng POD; in theo đơn, không cần tồn kho.",
                "target_buyer": "Người tặng quà cho người thân, bạn thân, người yêu.",
            },
        ]
        for slot in FALLBACK_SLOTS:
            if len(ready_ideas) >= 4:
                break
            ready_ideas.append({
                "title": slot["title"],
                "category": cluster_name,
                "market_price_range": price_range,
                "why_it_sells": slot["why_it_sells"],
                "expected_profit_margin": None,
                "upsell_bundle_tip": slot["upsell_bundle_tip"],
                "sourcing_tip": slot["sourcing_tip"],
                "target_buyer": slot["target_buyer"],
                "is_estimate": True,
            })

        # 2. Sinh gợi ý phôi POD phù hợp với ngành hàng
        pod_blanks = []
        if cat_key == "thoi-trang":
            pod_blanks = [
                {
                    "blank_type": "tshirt_unisex",
                    "title": f"Áo thun phong cách mùa {keyword}",
                    "category": "Thời trang",
                    "suggested_theme": f"Thiết kế chủ đề {keyword} kết hợp Typography tối giản hoặc hình minh họa phong cách trẻ trung.",
                    "design_hook": f"Thông điệp đón {keyword} tươi vui, nét vẽ minh họa Doodle độc quyền.",
                    "color_palette": "Trắng kem (Sand), Đen basic, Đỏ đô (Burgundy), Xanh lá thông",
                    "target_audience": "Gen Z và cặp đôi trẻ yêu thích thời trang năng động"
                },
                {
                    "blank_type": "tote",
                    "title": f"Túi Canvas chủ đề {keyword}",
                    "category": "Phụ kiện",
                    "suggested_theme": f"Họa tiết biểu tượng của dịp {keyword} trên nền vải mộc tự nhiên.",
                    "design_hook": f"Hình ảnh biểu trưng mùa {keyword} phong cách vẽ nét tay mộc mạc.",
                    "color_palette": "Beige mộc tự nhiên, Đen canvas cao cấp",
                    "target_audience": "Nữ sinh viên và dân công sở dùng đi làm, đi chơi"
                }
            ]
        elif cat_key == "gia-dung":
            pod_blanks = [
                {
                    "blank_type": "mug_11oz",
                    "title": f"Cốc sứ men mờ in thông điệp {keyword}",
                    "category": "Gia dụng & Đồ uống",
                    "suggested_theme": f"In lời chúc ý nghĩa, hoa văn đặc trưng của mùa {keyword} (công nghệ in 3D wrap).",
                    "design_hook": f"Lời chúc may mắn và bình an mùa {keyword} thiết kế font chữ nghệ thuật.",
                    "color_palette": "Sứ trắng bóng, Cốc quai màu viền đen/đỏ",
                    "target_audience": "Người mua quà tặng đồng nghiệp, bạn bè và người yêu"
                }
            ]
        elif cat_key == "trang-tri":
            pod_blanks = [
                {
                    "blank_type": "canvas_stretched",
                    "title": f"Tranh Canvas nghệ thuật mùa {keyword}",
                    "category": "Trang trí nhà cửa",
                    "suggested_theme": f"Tranh decor không gian ấm áp, nghệ thuật đương đại chủ đề {keyword}.",
                    "design_hook": f"Khung cảnh lễ hội và niềm vui sum vầy phong cách tranh sơn dầu hiện đại.",
                    "color_palette": "Tông màu ấm, vàng kim, đỏ may mắn hoặc tông lạnh tuyết trắng",
                    "target_audience": "Chủ căn hộ, quán cà phê và văn phòng cần trang trí dịp lễ"
                }
            ]
        else:
            pod_blanks = [
                {
                    "blank_type": "tote",
                    "title": f"Túi vải quà tặng mùa {keyword}",
                    "category": "Phụ kiện",
                    "suggested_theme": f"Thiết kế mang dấu ấn mùa {keyword}.",
                    "design_hook": f"Hình ảnh biểu tượng nhẹ nhàng, thanh lịch.",
                    "color_palette": "Vải mộc tự nhiên",
                    "target_audience": "Người tiêu dùng mua sắm cá nhân hoặc quà tặng"
                }
            ]

        return {
            "ready_to_ship_ideas": ready_ideas,
            "pod_blanks": pod_blanks,
            "mined_grounding": {
                "cluster_name": cluster_name,
                "median_price": mined.get("median_price"),
                "market_price_range": price_range,
                "top_attributes": mined.get("top_attributes", [])
            }
        }
