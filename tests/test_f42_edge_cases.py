import pytest
from app.services.f42.schemas import SuggestionRequest
from app.services.f42.orchestrator import F42Orchestrator
from app.services.f42.ai_engine import MarketAIAdvisor
from app.services.f42.comparable_pricing import ComparableIndex, _ACCESSORY_MARKERS


class TestF42EdgeCases:
    """Kiểm thử toàn diện cho các tình huống biên F42 Smart Suggestion."""

    def test_empty_title_no_cost(self):
        """Tiêu đề trống, không có giá vốn: phải trả về không đủ dữ liệu, giá = 0, không mẫu ảo."""
        req = SuggestionRequest(
            title="",
            blank_cost=0.0
        )
        # Ép db_live_override=False để test thuần logic nội bộ không phụ thuộc DB
        res = F42Orchestrator.execute(req, db_live_override=False)

        assert res.pricing.suggested_price == 0
        assert res.pricing.sample_size == 0
        assert res.pricing.method in ("none", "llm_gemini")
        if res.pricing.method == "none":
            assert res.pricing.insufficient_market_data is True
            assert "chưa đủ dữ liệu" in res.pricing.explanation.lower() or "không có căn cứ" in res.pricing.explanation.lower()
        # Giá compat trên FE cũng phải bằng 0 và markup bằng 0
        assert res.pricing_insight["recommended_price"] == 0
        assert res.pricing_insight["recommended_markup"] == 0

    def test_nonsense_title_no_cost(self):
        """Tên lạ vô nghĩa không nhận diện được và không có giá vốn: không tự bịa giá mặc định 199k."""
        req = SuggestionRequest(
            title="asdkjasd129301293",
            blank_cost=0.0
        )
        res = F42Orchestrator.execute(req, db_live_override=False)

        # Nếu không có LLM trả lời, kết quả phải là không đủ dữ liệu, giá không được là 199.000đ
        if not res.ai_engine_status.get("is_ai_live"):
            assert res.pricing.suggested_price == 0
            assert res.pricing_insight["recommended_price"] == 0
            assert res.pricing.sample_size == 0

    def test_cost_plus_when_no_market_data(self):
        """Sản phẩm mới chưa có dữ liệu thị trường nhưng có giá vốn: tính Cost-Plus, ghi rõ nguồn."""
        req = SuggestionRequest(
            title="Sản phẩm gốm mộc điêu khắc cá nhân thủ công 999",
            blank_cost=150000.0
        )
        res = F42Orchestrator.execute(req, db_live_override=False)

        # Giá phải lớn hơn giá vốn
        assert res.pricing.suggested_price >= 150000
        assert res.pricing_insight["recommended_price"] >= 150000
        assert res.pricing_insight["recommended_markup"] > 0
        # Mẫu thị trường phải là 0 vì không có mẫu đối chiếu
        if res.pricing.method == "cost_plus":
            assert res.pricing.sample_size == 0
            assert "cost-plus" in res.pricing.source_label.lower() or "giá vốn" in res.pricing.source_label.lower()

    def test_cost_higher_than_market_warning(self):
        """Giá vốn cao hơn giá thị trường: hệ thống phải nâng giá an toàn và cảnh báo."""
        from app.services.f42.pricing_engine import _apply_cost_floor
        warnings = []
        p25, p50, p75 = _apply_cost_floor(50000, 80000, 100000, blank_cost=120000, warnings=warnings)
        assert p50 >= 120000 * 1.30  # Floor cost + 30% margin
        assert any("giá vốn" in w.lower() for w in warnings)

    def test_accessory_vs_main_product_isolation(self):
        """Phụ kiện (ốp lưng, dây đeo...) phải được cách ly khỏi thiết bị chính."""
        # Kiểm tra danh sách marker phụ kiện
        assert "op lung" in _ACCESSORY_MARKERS
        assert "day deo" in _ACCESSORY_MARKERS
        assert "kinh cuong luc" in _ACCESSORY_MARKERS

        idx = ComparableIndex.get()
        if idx is not None:
            # Tìm kiếm máy điện thoại iPhone không được chứa ốp lưng
            comps_phone = idx.search("dien thoai iphone", top_k=10)
            for c in comps_phone:
                prep = c.title.lower()
                assert "op lung" not in prep
                assert "cuong luc" not in prep

    def test_no_fake_claims_in_fallback(self):
        """Chế độ fallback ngữ nghĩa không tự ý thêm 'chính hãng', 'bảo hành' vô căn cứ."""
        sem = MarketAIAdvisor.semantic_fallback_analysis(
            title="Áo thun cotton trơn",
            category_name="Thời trang",
            material="Cotton",
            blank_cost=50000.0
        )
        content = MarketAIAdvisor.build_content_result(sem, title_input="Áo thun cotton trơn")
        for t in content.titles:
            text = t.text.lower()
            assert "chính hãng" not in text
            assert "bảo hành uy tín" not in text
            assert "an toàn tuyệt đối" not in text
        description = str(content.description.model_dump()).lower()
        assert "12 tháng chính hãng" not in description
        assert "mọi loại da" not in description
        assert "100% hình ảnh thực tế" not in description

    def test_known_category_without_comparables_returns_no_market_price(self, monkeypatch):
        """Nhận diện được ngành hàng không có nghĩa là có dữ liệu để báo giá thị trường."""
        monkeypatch.setattr(MarketAIAdvisor, "is_gemini_available", classmethod(lambda cls: False))
        monkeypatch.setattr(ComparableIndex, "get", classmethod(lambda cls: None))
        res = F42Orchestrator.execute(
            SuggestionRequest(title="iPhone 15 Pro Max 256GB"), db_live_override=False
        )
        assert res.pricing.suggested_price == 0
        assert res.pricing.method == "none"
        assert res.pricing.insufficient_market_data is True
        assert res.pricing.sample_size == 0
        assert res.pricing.confidence == "none"

    def test_known_category_without_comparables_uses_cost_plus(self, monkeypatch):
        """Khi thiếu mẫu thị trường nhưng có giá vốn, chỉ giá vốn mới được dùng để ước tính."""
        monkeypatch.setattr(MarketAIAdvisor, "is_gemini_available", classmethod(lambda cls: False))
        monkeypatch.setattr(ComparableIndex, "get", classmethod(lambda cls: None))
        res = F42Orchestrator.execute(
            SuggestionRequest(title="iPhone 15 Pro Max 256GB", blank_cost=10000000),
            db_live_override=False,
        )
        assert res.pricing.method == "cost_plus"
        assert res.pricing.suggested_price >= 10000000
        assert res.pricing.sample_size == 0
        assert res.pricing.confidence == "low"

    def test_no_fake_trending_percentages(self):
        """Tag tương thích không được bịa tỷ lệ phần trăm tăng trưởng ảo như +50%."""
        req = SuggestionRequest(
            title="Túi cói thổ cẩm",
            blank_cost=80000.0
        )
        res = F42Orchestrator.execute(req, db_live_override=False)
        for item in res.trending_keywords:
            growth = item.get("growth", "")
            # growth không được bắt đầu bằng dấu + hoặc chứa %
            assert not growth.startswith("+")
            assert "%" not in growth
            assert item["is_hot"] is False

    def test_ai_engine_status_transparency(self):
        """Response phải có thông tin minh bạch trạng thái AI (ai_engine_status)."""
        req = SuggestionRequest(
            title="Bình hoa gốm sứ Bát Tràng men hoả biến",
            blank_cost=100000.0
        )
        res = F42Orchestrator.execute(req, db_live_override=False)

        assert "ai_engine_status" in res.model_dump()
        status = res.ai_engine_status
        assert "is_ai_live" in status
        assert "engine_label" in status
        assert "pricing_method" in status
        assert "source_label" in status
        if not status["is_ai_live"]:
            assert status["notice"] != ""  # Báo rõ AI tạo sinh đang gián đoạn
