from typing import Any, Dict, List, Optional

from app.services.f42.schemas import (
    ContentResult,
    DescriptionStructure,
    SpecItem,
    TitleItem,
)
from app.services.f42.vi_text import normalize_nfc


def _pad_title_to_length(title: str, min_len: int = 40, max_len: int = 120) -> str:
    """Đảm bảo tiêu đề nằm trong khoảng 40 đến 120 ký tự mà không bị cắt cụt từ."""
    t = normalize_nfc(title).strip()
    if len(t) < min_len:
        t = f"{t} - Thiết kế chuẩn mực chất lượng tinh tế"
    if len(t) > max_len:
        t = t[:max_len].rsplit(" ", 1)[0]
    return t


def generate_fallback_content(
    user_title: str,
    category_name: str,
    material: str = "",
    extra_attributes: str = "",
    tier_label: str = ""
) -> ContentResult:
    clean_title = normalize_nfc(user_title or "Sản phẩm thủ công mỹ nghệ").strip()
    clean_cat = normalize_nfc(category_name or "Mỹ nghệ & Đời sống").strip()
    clean_mat = normalize_nfc(material).strip()
    
    mat_part = f" chất liệu {clean_mat}" if clean_mat else ""
    
    t1 = f"{clean_title}{mat_part} - Phong cách trang nhã hiện đại"
    t2 = f"{clean_title} ({clean_mat}) - Gia công tỉ mỉ độ bền cao" if clean_mat else f"{clean_title} - Kiểu dáng thanh lịch tiện dụng hàng ngày"
    t3 = f"{clean_title} cao cấp - Phù hợp sử dụng tiện ích và trang trí"
    t4 = f"{clean_title} tinh tế - Điểm nhấn ấn tượng cho không gian sống"
    t5 = f"{clean_title} tiêu chuẩn - Hoàn thiện sắc nét xuất xứ rõ ràng"

    titles = [
        TitleItem(text=_pad_title_to_length(t1), angle="balanced"),
        TitleItem(text=_pad_title_to_length(t2), angle="material"),
        TitleItem(text=_pad_title_to_length(t3), angle="function"),
        TitleItem(text=_pad_title_to_length(t4), angle="style"),
        TitleItem(text=_pad_title_to_length(t5), angle="technical"),
    ]

    intro = (
        f"{clean_title} thuộc nhóm {clean_cat}, được thiết kế với phong cách hài hòa, "
        f"chú trọng vào tính ứng dụng và độ hoàn thiện chi tiết. "
        f"Sản phẩm là lựa chọn phù hợp cho nhu cầu sử dụng thực tế cũng như quà tặng ý nghĩa."
    )

    specs: List[SpecItem] = [
        SpecItem(label="Danh mục", value=clean_cat),
        SpecItem(label="Tên sản phẩm", value=clean_title)
    ]
    if clean_mat:
        specs.append(SpecItem(label="Chất liệu", value=clean_mat))
    if tier_label:
        specs.append(SpecItem(label="Phân loại", value=tier_label))
    if extra_attributes:
        specs.append(SpecItem(label="Thuộc tính", value=extra_attributes))

    highlights = [
        f"Thiết kế chuẩn mực phù hợp nhu cầu sử dụng trong danh mục {clean_cat}.",
        "Đường nét hoàn thiện tỉ mỉ, bề mặt chỉn chu và đồng đều.",
        "Dễ dàng kết hợp bài trí trong nhiều không gian sinh hoạt và làm việc."
    ]
    if clean_mat:
        highlights.append(f"Gia công từ {clean_mat}, giữ được độ bền và tính thẩm mỹ tự nhiên.")

    missing_info: List[str] = []
    if not clean_mat:
        missing_info.append("chất liệu cụ thể")
    if not extra_attributes:
        missing_info.append("kích thước và thông số chi tiết")

    care_guide: Optional[str] = None
    if clean_mat:
        care_guide = f"Bảo quản sản phẩm nơi khô ráo, thoáng mát. Tránh va đập mạnh và vệ sinh bằng khăn mềm nhẹ nhàng."
    else:
        missing_info.append("care_guide (chưa khai báo chất liệu)")

    claims_used: List[str] = [clean_title]
    if clean_mat:
        claims_used.append(clean_mat)

    return ContentResult(
        source="fallback",
        titles=titles,
        description=DescriptionStructure(
            intro=intro,
            specs=specs,
            highlights=highlights,
            care_guide=care_guide
        ),
        claims_used=claims_used,
        missing_info=missing_info,
        warnings=[],
        disclaimer="Nội dung được tạo theo mẫu cấu trúc cơ bản vì AI sinh nội dung nâng cao đang không khả dụng."
    )
