from pathlib import Path

from app.core.f29.factors import KEYS, LABELS
from scripts.f29_health.candidates import BOOST, LEARNED, RECENCY
from scripts.f29_health.report_evidence import (
    markets_lines, material_lines, num, per100, ranges_lines, roles_lines, tiki_lines, tldr_lines,
)
from scripts.f29_health.report_price import price_lines

CASE = "## Case study VietCraft"


def _method(p):
    w, c, t = p["weights"], p["coefficients"], p["targets"]
    rev = p["review"]
    return [
        "## 2. Công thức 6 yếu tố",
        "Mỗi yếu tố cho điểm con từ 0 đến 100. Điểm sức khoẻ = tổng của (trọng số % × điểm con ÷ 100).",
        "",
        f"- Số ảnh: số ảnh ÷ {t['image']}, tối đa 100. Số {t['image']} là trung vị số ảnh của sản phẩm bán chạy trên Tiki.",
        f"- Độ dài mô tả: số ký tự ÷ {t['description']}, tối đa 100. Số {t['description']} là trung vị (làm tròn đến 10) của sản phẩm bán chạy trên Olist.",
        f"- Số tag đã duyệt: số tag ÷ {t['tags']}, tối đa 100.",
        "- Chất liệu: có ô Chất liệu hoặc tên/mô tả nêu một từ chất liệu thì 100, không thì 0. Theo chính sách, không học từ dữ liệu.",
        f"- Tỉ lệ đánh giá tốt: (số đánh giá từ 4 sao + {rev['m']} × {num(rev['p0'], 3)}) ÷ (số đánh giá + {rev['m']}) × 100. "
        "Không có đánh giá thì 0. Khi chạy thật, p0 là tỉ lệ đánh giá 4–5 sao của chính VietCraft (chỉ đơn thật) tại lúc chấm; "
        f"{num(rev['p0'], 3)} là giá trị học từ Olist, chỉ để lưu vết.",
        "- Cạnh tranh giá: giá ÷ giá tham chiếu. Giá tham chiếu lấy theo thứ tự: trung vị giá cùng danh mục trên VietCraft "
        "→ cùng nhóm hàng trên VietCraft (mỗi bậc cần ≥ 8 sản phẩm khác, không tính chính sản phẩm và không tính các sản phẩm khác của cùng shop) "
        "→ giá giữa do mô hình gợi ý giá đoán từ tên sản phẩm → trung vị Tiki theo nhóm. "
        "Lúc học trên Olist chỉ loại chính sản phẩm (Olist không có nhóm như VietCraft). "
        "Giá ≤ 1 lần được 100, giá ≥ 2 lần được 0, ở giữa giảm dần.",
        "",
        "| Yếu tố | Trọng số (%) | Hệ số học từ Olist |",
        "|---|---|---|",
        *[f"| {LABELS[k]} | {w[k]} | {num(c[k], 3) if k in c else 'cố định (chính sách)'} |" for k in KEYS],
        "",
        "Hệ số càng lớn, yếu tố đó càng gắn với việc bán chạy trong dữ liệu Olist, nên được nhiều điểm hơn.",
    ]


def _limits(p):
    m, w = p["metrics"], p["weights"]
    t_learned = per100(m["tiki_test"][LEARNED]["roc_auc"])
    t_desc = per100(m["tiki_test"]["Chỉ độ dài mô tả"]["roc_auc"])
    desc_note = ("riêng độ dài mô tả nhỉnh hơn toàn bộ điểm tổng hợp" if t_desc > t_learned
                 else "riêng độ dài mô tả không nhỉnh hơn điểm tổng hợp")
    return [
        "## 8. Giới hạn",
        f"- Điểm đo chất lượng tin đăng, không dự báo doanh số. "
        f"Trên Olist thử, điểm học được đúng {per100(m['olist_test'][LEARNED]['roc_auc'])}/100 cặp.",
        f"- Lịch sử bán mạnh hơn: 'Đơn gần nhất' đúng {per100(m['olist_test'][RECENCY]['roc_auc'])}/100 cặp trên Olist thử. "
        "Chỉ để so sánh, không dùng để chấm điểm.",
        f"- Trên Tiki, điểm học được đúng {t_learned}/100 cặp, còn riêng độ dài mô tả {t_desc}/100: {desc_note}. "
        "Mô tả Tiki bị cắt khoảng 200 ký tự, nên yếu tố mô tả bị giới hạn trên Tiki.",
        "- Tập học Olist chỉ gồm sản phẩm có bán trong 180 ngày trước mốc. Giá Olist là giá bán thực tế, không phải giá niêm yết.",
        "- Khi học, giá tham chiếu chỉ tính theo danh mục, rồi theo cả mốc thời gian (Olist không có nhóm nhỏ như trên VietCraft). "
        "Điểm giá trên VietCraft có thể lệch vì khác biệt này.",
        f"- HistGB (mô hình máy học phức tạp hơn, chỉ để so sánh): đúng {per100(m['olist_test'][BOOST]['roc_auc'])}/100 cặp trên Olist thử "
        f"và {per100(m['tiki_test'][BOOST]['roc_auc'])}/100 trên Tiki. Trọng số học được: "
        f"{per100(m['olist_test'][LEARNED]['roc_auc'])}/100 và {t_learned}/100.",
        f"- Giá có trọng số lớn nhất ({w['price']}%). Giá đo bằng tỉ lệ với giá tham chiếu, nên không phụ thuộc đơn vị tiền tệ.",
        "- Cổng đạt là tiêu chuẩn tối thiểu. Trước khi dùng cho sản phẩm thật, cần kiểm tra thêm trên dữ liệu VietCraft.",
        "",
        "### Giới hạn Shopee",
        "- Nhãn 'bán chạy' trên Shopee dùng số đánh giá thay cho doanh số, vì Shopee không công bố (định nghĩa ở Tóm tắt).",
        "- Bỏ các sản phẩm Shopee không có mã danh mục (không xếp hạng được trong danh mục): 1.025 trên 30.000 dòng.",
        "- Dữ liệu là thị trường Đài Loan, không phải Việt Nam.",
        "- Nguồn: Rebrowser, giấy phép CC-BY-NC. Chỉ dùng để thi, không dùng để học trọng số.",
    ]


def _text(p):
    head = ["# Điểm sức khoẻ sản phẩm v2 (health-2.2)",
            f"Tạo lúc {p['created_at']}. Trọng số lưu ở `app/core/f29/health_weights.json`."]
    parts = [head, tldr_lines(p), roles_lines(p), _method(p), markets_lines(p), ranges_lines(p),
             tiki_lines(p), material_lines(p), price_lines(), _limits(p)]
    return "\n\n".join("\n".join(part) for part in parts if part) + "\n"


def _case_study(path):
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8")
    start = text.find(CASE)
    if start < 0:
        return ""
    stop = text.find("\n## ", start + 1)
    return text[start:stop if stop >= 0 else len(text)].strip()


def write(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    case = _case_study(path)
    path.write_text(_text(payload) + (f"\n{case}\n" if case else ""), encoding="utf-8")
