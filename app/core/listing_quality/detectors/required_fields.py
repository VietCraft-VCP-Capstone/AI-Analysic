import math
from typing import Any, Dict, List
from bson.decimal128 import Decimal128
from ..schemas import Issue, Recommendation

class RequiredFieldsDetector:
    code = "required_fields"

    def _parse_price(self, val: Any) -> float:
        if val is None:
            return 0.0
        if isinstance(val, Decimal128):
            try:
                v = float(val.to_decimal())
                return 0.0 if math.isnan(v) or math.isinf(v) else v
            except Exception:
                return 0.0
        try:
            v = float(val)
            return 0.0 if math.isnan(v) or math.isinf(v) else v
        except (ValueError, TypeError):
            return 0.0

    def evaluate(self, listing: Dict[str, Any], context: Dict[str, Any]) -> List[Issue]:
        issues: List[Issue] = []

        title = listing.get("title")
        if title is None:
            issues.append(Issue(
                id="req_title_missing",
                code="TITLE_MISSING",
                detector=self.code,
                severity="high",
                field="title",
                status="open",
                confidence=1.0,
                evidence={"observed": None, "expected": "Tiêu đề sản phẩm không được để trống"},
                message="Sản phẩm chưa có tiêu đề.",
                recommendation=Recommendation(
                    action="ADD_TITLE",
                    message="Bổ sung tiêu đề mô tả ngắn gọn và rõ ràng cho sản phẩm.",
                    field_link="title",
                    verification="Kiểm tra lại trường tiêu đề có ít nhất 10 ký tự."
                )
            ))
        elif not str(title).strip():
            issues.append(Issue(
                id="req_title_empty",
                code="TITLE_EMPTY",
                detector=self.code,
                severity="high",
                field="title",
                status="open",
                confidence=1.0,
                evidence={"observed": str(title), "expected": "Tiêu đề không chỉ chứa khoảng trắng"},
                message="Tiêu đề sản phẩm đang bị trống.",
                recommendation=Recommendation(
                    action="SET_TITLE",
                    message="Nhập tên sản phẩm chứa từ khoá chính để khách hàng dễ tìm kiếm.",
                    field_link="title",
                    verification="Kiểm tra lại trường tiêu đề có nội dung hợp lệ."
                )
            ))
        elif len(str(title).strip()) < 10:
            issues.append(Issue(
                id="req_title_too_short",
                code="TITLE_TOO_SHORT",
                detector=self.code,
                severity="medium",
                field="title",
                status="open",
                confidence=1.0,
                evidence={"observed_length": len(str(title).strip()), "expected_min_length": 10},
                message="Tiêu đề quá ngắn, chưa đủ thông tin nhận diện sản phẩm.",
                recommendation=Recommendation(
                    action="EXPAND_TITLE",
                    message="Mở rộng tiêu đề bằng cách thêm loại sản phẩm, chất liệu hoặc đặc điểm nổi bật.",
                    field_link="title",
                    verification="Kiểm tra lại độ dài tiêu đề từ 10 ký tự trở lên."
                )
            ))

        desc = listing.get("description")
        if desc is None:
            issues.append(Issue(
                id="req_desc_missing",
                code="DESCRIPTION_MISSING",
                detector=self.code,
                severity="high",
                field="description",
                status="open",
                confidence=1.0,
                evidence={"observed": None, "expected": "Mô tả sản phẩm không được để trống"},
                message="Sản phẩm chưa có mô tả chi tiết.",
                recommendation=Recommendation(
                    action="ADD_DESCRIPTION",
                    message="Viết mô tả chi tiết bao gồm thông số, công dụng và điểm đặc biệt của sản phẩm.",
                    field_link="description",
                    verification="Kiểm tra trường mô tả có nội dung chi tiết."
                )
            ))
        elif not str(desc).strip():
            issues.append(Issue(
                id="req_desc_empty",
                code="DESCRIPTION_EMPTY",
                detector=self.code,
                severity="high",
                field="description",
                status="open",
                confidence=1.0,
                evidence={"observed": str(desc), "expected": "Mô tả không chỉ chứa khoảng trắng"},
                message="Mô tả sản phẩm đang bị trống.",
                recommendation=Recommendation(
                    action="SET_DESCRIPTION",
                    message="Bổ sung mô tả giúp khách hiểu rõ quy cách và chất lượng sản phẩm.",
                    field_link="description",
                    verification="Kiểm tra trường mô tả đã lưu nội dung."
                )
            ))
        elif len(str(desc).strip()) < 20:
            issues.append(Issue(
                id="req_desc_too_short",
                code="DESCRIPTION_TOO_SHORT",
                detector=self.code,
                severity="medium",
                field="description",
                status="open",
                confidence=1.0,
                evidence={"observed_length": len(str(desc).strip()), "expected_min_length": 20},
                message="Mô tả quá ngắn, thiếu thông tin thuyết phục người mua.",
                recommendation=Recommendation(
                    action="EXPAND_DESCRIPTION",
                    message="Mở rộng mô tả với thông tin chất liệu, kích cỡ, bảo quản và hướng dẫn sử dụng.",
                    field_link="description",
                    verification="Kiểm tra độ dài mô tả tối thiểu 20 ký tự."
                )
            ))

        images = listing.get("images")
        if not images or not isinstance(images, list) or len(images) == 0:
            issues.append(Issue(
                id="req_images_missing",
                code="IMAGES_MISSING",
                detector=self.code,
                severity="high",
                field="images",
                status="open",
                confidence=1.0,
                evidence={"observed_count": 0, "expected_min_count": 1},
                message="Sản phẩm chưa có ảnh đại diện nào.",
                recommendation=Recommendation(
                    action="ADD_IMAGES",
                    message="Tải lên ít nhất 1 ảnh rõ nét của sản phẩm.",
                    field_link="images",
                    verification="Kiểm tra sản phẩm có ít nhất 1 ảnh đại diện hợp lệ."
                )
            ))
        elif len(images) < 2:
            issues.append(Issue(
                id="req_images_few",
                code="IMAGES_INSUFFICIENT",
                detector=self.code,
                severity="low",
                field="images",
                status="open",
                confidence=1.0,
                evidence={"observed_count": len(images), "expected_min_count": 2},
                message="Sản phẩm chỉ có 1 ảnh, người mua thường muốn xem nhiều góc chụp hơn.",
                recommendation=Recommendation(
                    action="ADD_MORE_IMAGES",
                    message="Thêm ảnh chụp chi tiết góc cận cảnh hoặc ảnh thực tế khi sử dụng.",
                    field_link="images",
                    verification="Kiểm tra số lượng ảnh đạt từ 2 ảnh trở lên."
                )
            ))

        cats = listing.get("categories") or listing.get("category_ids")
        if not cats or (isinstance(cats, list) and len(cats) == 0):
            issues.append(Issue(
                id="req_category_missing",
                code="CATEGORY_MISSING",
                detector=self.code,
                severity="high",
                field="categories",
                status="open",
                confidence=1.0,
                evidence={"observed": None, "expected": "Phải chọn danh mục ngành hàng"},
                message="Sản phẩm chưa được gán vào danh mục ngành hàng.",
                recommendation=Recommendation(
                    action="SELECT_CATEGORY",
                    message="Chọn đúng danh mục tương ứng để khách hàng dễ dàng tìm kiếm.",
                    field_link="categories",
                    verification="Kiểm tra sản phẩm đã chọn ít nhất một danh mục."
                )
            ))

        variants = context.get("variants", [])
        variant_prices = [self._parse_price(v.get("retail_price")) for v in variants if v.get("is_active", True)]
        direct_price = self._parse_price(listing.get("original_price") or listing.get("min_price"))

        if not variant_prices and direct_price <= 0:
            issues.append(Issue(
                id="req_price_missing",
                code="PRICE_MISSING",
                detector=self.code,
                severity="high",
                field="price",
                status="open",
                confidence=1.0,
                evidence={"direct_price": direct_price, "active_variant_prices": variant_prices},
                message="Sản phẩm chưa có giá bán hoặc giá bằng 0.",
                recommendation=Recommendation(
                    action="SET_PRICE",
                    message="Thiết lập giá bán niêm yết hoặc giá biến thể hợp lệ lớn hơn 0.",
                    field_link="pricing",
                    verification="Kiểm tra giá bán sản phẩm lớn hơn 0 đồng."
                )
            ))

        tags = listing.get("tags") or listing.get("tag_ids")
        if not tags or (isinstance(tags, list) and len(tags) == 0):
            issues.append(Issue(
                id="req_tags_missing",
                code="TAGS_MISSING",
                detector=self.code,
                severity="low",
                field="tags",
                status="open",
                confidence=1.0,
                evidence={"observed_count": 0, "expected_min_count": 1},
                message="Sản phẩm chưa có thẻ từ khoá (tag) tìm kiếm.",
                recommendation=Recommendation(
                    action="ADD_TAGS",
                    message="Thêm các thẻ từ khoá mô tả sản phẩm để tối ưu SEO tìm kiếm.",
                    field_link="tags",
                    verification="Kiểm tra danh sách tags có ít nhất một thẻ từ khoá."
                )
            ))

        return issues
