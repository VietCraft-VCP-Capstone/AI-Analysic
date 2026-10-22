from pathlib import Path

from app.core.f29.factors import KEYS, LABELS
from scripts.f29_health.candidates import BOOST, LEARNED, RECENCY
from scripts.f29_health.learn import FLOOR


def _n(x):
    return f"{x:.3f}".replace(".", ",")


def _ci(ci):
    return f"[{_n(ci[0])}; {_n(ci[1])}]"


def _tied(ci):
    return ci[0] <= 0 <= ci[1]


def _verdict(ci):
    if ci[0] > 0:
        return "học tốt hơn, có ý nghĩa"
    if ci[1] < 0:
        return "học kém hơn, có ý nghĩa"
    return "khoảng chứa 0, chưa đủ chứng cứ là khác nhau"


def _cell(metrics, name):
    m = metrics.get(name)
    return "—" if m is None else f"{_n(m['roc_auc'])} {_ci(m['auc_ci95'])}"


def _method(p):
    w, c, t, r, d = p["weights"], p["coefficients"], p["targets"], p["rows"], p["dates"]
    rev = p["review"]
    return [
        "# Điểm sức khoẻ sản phẩm v2 (health-2.0)",
        "",
        f"Tạo lúc {p['created_at']}. Trọng số lưu ở `app/core/f29/health_weights.json`.",
        "",
        "## 1. Dữ liệu dùng",
        f"- Học: Olist (sàn ở Brazil), 4 mốc {', '.join(p['trained_on']['cutoffs'])}, {r['olist_train']} dòng sản phẩm.",
        f"- Kiểm tra: Olist mốc {d['val']}, {r['olist_val']} dòng. Olist mốc {d['test']}, {r['olist_test']} dòng.",
        f"- Đề thi cuối: Tiki 2023 (tập test), {r['tiki_test']} sản phẩm. Model chưa thấy đề này khi học.",
        "- Nhãn cần đoán: sản phẩm có nằm trong top 25% bán chạy của cùng nhóm hàng trong 90 ngày sau mốc.",
        "- Olist không có tag, Tiki không có đánh giá, nên mỗi bên chấm ít yếu tố hơn.",
        "",
        "## 2. Công thức 5 yếu tố",
        "Mỗi yếu tố cho điểm con từ 0 đến 100. Điểm sức khoẻ = tổng của (trọng số % × điểm con ÷ 100).",
        "",
        f"- Số ảnh: số ảnh ÷ {t['image']}, tối đa 100.",
        f"- Độ dài mô tả: số ký tự ÷ {t['description']}, tối đa 100.",
        f"- Số tag đã duyệt: số tag ÷ {t['tags']}, tối đa 100.",
        f"- Tỉ lệ đánh giá tốt: (số đánh giá từ 4 sao + {rev['m']} × {_n(rev['p0'])}) ÷ (số đánh giá + {rev['m']}) × 100. "
        f"Không có đánh giá thì 0. {_n(rev['p0'])} là tỉ lệ đánh giá từ 4 sao của cả sàn, học từ Olist.",
        "- Cạnh tranh giá: giá ÷ giá tham chiếu. Giá tham chiếu là trung vị giá cùng danh mục (không tính chính nó, cần ≥ 8 sản phẩm khác), "
        "rồi đến cùng nhóm, rồi đến trung vị Tiki theo nhóm. Giá ≤ 1 lần được 100, giá ≥ 2 lần được 0, ở giữa giảm dần.",
        "",
        "## 3. Trọng số và hệ số gốc",
        "| Yếu tố | Trọng số (%) | Hệ số học từ Olist |",
        "|---|---|---|",
        *[f"| {LABELS[k]} | {w[k]} | {_n(c[k]) if k in c else 'cố định (chính sách)'} |" for k in KEYS],
        "",
        "Hệ số càng lớn, yếu tố đó càng gắn với việc bán chạy trong dữ liệu Olist, nên được nhiều điểm hơn.",
    ]


def _results(p):
    m, g = p["metrics"], p["gate"]
    names = list(dict.fromkeys(n for split in m.values() for n in split))
    lines = [
        "## 4. Bảng AUC (đo khả năng xếp hàng bán chạy lên trước)",
        "AUC: 0,5 là đoán bừa, 1,0 là xếp đúng hết. Khoảng trong ngoặc vuông là khoảng tin cậy 95%.",
        "",
        "| Phương án | Olist kiểm tra | Olist thử | Tiki (đề thi) |",
        "|---|---|---|---|",
        *[f"| {n} | {_cell(m['olist_val'], n)} | {_cell(m['olist_test'], n)} | {_cell(m['tiki_test'], n)} |" for n in names],
        "",
        "## 5. Kết quả cổng đạt",
        f"- Học trừ chia đều, trên Tiki: khoảng {_ci(g['vs_equal_ci'])}, {_verdict(g['vs_equal_ci'])}.",
        f"- Học trừ health-1.0, trên Tiki: khoảng {_ci(g['vs_v1_ci'])}, {_verdict(g['vs_v1_ci'])}.",
        f"- Kết quả: {'ĐẠT' if g['passed'] else 'KHÔNG ĐẠT'}. Cổng là kiểm định không thua: đạt khi cận trên của cả hai khoảng ≥ 0.",
    ]
    if _tied(g["vs_equal_ci"]):
        lines.append("- Học và chia đều ngang nhau về thống kê. Giữ trọng số học được vì nó đến từ dữ liệu và cho thứ tự yếu tố "
                     "có cơ sở, không phải vì dự đoán tốt hơn chia đều.")
    else:
        lines.append("- Học và chia đều khác nhau có ý nghĩa thống kê, xem khoảng ở trên.")
    return lines


def _limits(p):
    m, w, c, r = p["metrics"], p["weights"], p["coefficients"], p["rows"]
    o_learned = m["olist_test"][LEARNED]["roc_auc"]
    t_learned = m["tiki_test"][LEARNED]["roc_auc"]
    t_desc = m["tiki_test"]["Chỉ độ dài mô tả"]["roc_auc"]
    desc_note = ("riêng độ dài mô tả nhỉnh hơn toàn bộ điểm tổng hợp" if t_desc > t_learned
                 else "riêng độ dài mô tả không nhỉnh hơn điểm tổng hợp")
    review_note = f"{w['review']}% (mức sàn)" if w["review"] == FLOOR else f"{w['review']}%"
    return [
        "## 6. Giới hạn",
        f"- Yếu tố nội dung và giá dự đoán yếu: AUC của điểm học được trên Olist thử là {_n(o_learned)}. "
        "Đây là điểm chất lượng tin đăng, không phải dự báo doanh số.",
        f"- Lịch sử bán mạnh hơn: 'Đơn gần nhất' đạt AUC {_n(m['olist_test'][RECENCY]['roc_auc'])} trên Olist thử. "
        "Chỉ để so sánh, không dùng để chấm điểm.",
        f"- Trên Tiki, điểm học được đạt AUC {_n(t_learned)}, còn chỉ độ dài mô tả đạt {_n(t_desc)}: {desc_note}.",
        "- Tập học Olist chỉ gồm sản phẩm có bán trong 180 ngày trước mốc. Sản phẩm không bán không có trong tập học, "
        "còn production chấm mọi tin đăng.",
        "- Giá Olist là trung vị giá bán thực tế (giá trong đơn) của 180 ngày trước mốc, không phải giá niêm yết. "
        "Production dùng trung vị giá niêm yết của các biến thể đang bật.",
        "- Khi học, giá tham chiếu chỉ có tầng danh mục rồi đến cả mốc (Olist không có nhóm và tầng Tiki như production). "
        "Điểm giá khi áp lên VietCraft có thể lệch vì khác biệt này.",
        f"- HistGB trên Olist (học trên tập Olist train, 4 điểm con) đạt AUC {_n(m['olist_test'][BOOST]['roc_auc'])} trên Olist thử, "
        f"so với {_n(o_learned)} của trọng số học được. Phương án này chỉ để tham chiếu.",
        f"- HistGB trên Tiki học trên tập Tiki train ({r['tiki_train']} dòng), với 3 điểm con ảnh, mô tả, giá, nhãn top25, "
        "tham số models.boosting (tốc độ học 0,05, tối đa 500 vòng, random_state 42). Trọng số học được chưa thấy dữ liệu Tiki, "
        f"nên AUC {_n(m['tiki_test'][BOOST]['roc_auc'])} của HistGB trên Tiki và {_n(t_learned)} của trọng số không cùng điều kiện.",
        "- Mô tả Tiki bị cắt khoảng 200 ký tự, nên yếu tố mô tả trên Tiki bị giới hạn. Mốc 570 lấy từ Olist.",
        f"- Trọng số giá lớn ({w['price']}%). Giá được đo bằng tỉ lệ so với giá tham chiếu, nên không phụ thuộc đơn vị tiền tệ.",
        f"- Yếu tố đánh giá nhận {review_note}, hệ số học từ Olist {_n(c['review'])}.",
        "- Cổng đạt là tiêu chuẩn tối thiểu. Trước khi dùng cho sản phẩm thật, cần kiểm tra thêm trên dữ liệu VietCraft.",
    ]


def _lines(p):
    return _method(p) + [""] + _results(p) + [""] + _limits(p)


def write(path, payload):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(_lines(payload)) + "\n", encoding="utf-8")
