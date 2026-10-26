import json
from pathlib import Path

from scripts.f29_health.report_evidence import per100
from scripts.f29_price.train import markdown

PRICE_JSON = Path(__file__).resolve().parents[2] / "app" / "core" / "f29" / "price_model.json"


def _lines(metrics: dict) -> list[str]:
    return [
        markdown(metrics),
        "",
        "Dữ liệu: Tiki 2023 và Tiki 2026, chia theo người bán (cột split có sẵn). "
        "Học trên tập train, kiểm tra trên tập test của từng năm.",
        "Thuật toán: TF-IDF ký tự (2–4 ký tự) trên chuỗi 'nhóm + tên sản phẩm', cộng Ridge (alpha 1,0). "
        "Mô hình dự đoán log(giá). Khoảng gợi ý là giá dự đoán nhân exp của phân vị 25% và 75% phần dư trên tập val.",
        "",
        "### Giới hạn mô hình giá",
        "- Học từ hàng đại trà trên Tiki nên hàng thủ công có thể bị coi là đắt.",
        f"- Khoảng 25–75% chỉ chứa {per100(metrics['tiki26_test']['in_range'])}% giá thật ở Tiki 2026, "
        "nên khoảng chưa hiệu chỉnh tốt khi đổi năm.",
    ]


def price_lines(path: Path = PRICE_JSON) -> list[str]:
    try:
        return _lines(json.loads(path.read_text("utf-8"))["metrics"])
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return []
