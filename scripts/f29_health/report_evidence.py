from app.core.f29.factors import KEYS, LABELS
from scripts.f29_health.candidates import EQUAL, LEARNED, LIFT_MIN
from scripts.f29_health.learn import FLOOR

MARKET_ROWS = (("Olist thử", "olist_test"), ("Tiki (đề thi)", "tiki_test"), ("Shopee (đề thi)", "shopee_test"))
TIE = ("Học và chia đều hoà nhau về thống kê; giữ trọng số học vì nó có căn cứ dữ liệu cho thứ tự ưu tiên, "
       "không phải vì dự đoán tốt hơn.")
BETTER = "Học khác chia đều có ý nghĩa thống kê ở ít nhất một bộ; xem khoảng ở mục 3."


def num(x, digits=2):
    return f"{x:.{digits}f}".replace(".", ",")


def grp(n):
    return f"{n:,}".replace(",", ".")


def per100(auc):
    return round(100 * auc)


def band(ci):
    return f"{per100(ci[0])}–{per100(ci[1])}"


def ci_text(ci):
    return f"[{num(ci[0], 3)}; {num(ci[1], 3)}]"


def span(r):
    return "cố định" if r[0] == r[1] else f"{r[0]}–{r[1]}%"


def tie_text(p):
    cis = [p["gate"]["per_market"][k]["vs_equal_ci"] for k in ("tiki_test", "shopee_test")]
    return TIE if all(lo <= 0 <= hi for lo, hi in cis) else BETTER


def tldr_lines(p):
    m, lift = p["metrics"], p["lift"]
    hit = {k: per100(m[k][LEARNED]["roc_auc"]) for _, k in MARKET_ROWS}
    return [
        "## Tóm tắt",
        f"1. Trọng số chỉ học từ Olist. Tiki train chỉ dùng để đặt mốc {p['targets']['image']} ảnh và để đối chiếu (mục 5); "
        "Tiki test và Shopee không dùng để học trọng số.",
        f"2. Điểm đúng {hit['olist_test']}/100 cặp trên Olist, {hit['tiki_test']}/100 trên Tiki, "
        f"{hit['shopee_test']}/100 trên Shopee (đoán bừa: 50).",
        "3. Bán chạy = nằm trong 25% đứng đầu của từng bộ (Olist: số bán trong 90 ngày sau mốc, cùng danh mục; "
        "Tiki: nằm trong 25% sản phẩm có số đã bán ÷ max(tuổi, 30 ngày) cao nhất cùng nhóm hàng; "
        "Shopee: số đánh giá ÷ max(tuổi, 30 ngày), cùng danh mục). "
        f"Nhóm 20% điểm cao bán chạy gấp {num(lift['olist_test'])} / {num(lift['tiki_test'])} / "
        f"{num(lift['shopee_test'])} lần nhóm 20% điểm thấp (Olist / Tiki / Shopee).",
        f"4. Cổng: {'ĐẠT' if p['gate']['passed'] else 'KHÔNG ĐẠT'}. Gấp ≥ {num(LIFT_MIN, 1)} lần ở cả 3 bộ, "
        f"và học không thua chia đều. {tie_text(p)}",
        "5. Điểm đo chất lượng tin đăng, không phải dự báo doanh số. Shopee không có doanh số thật, "
        "nên dùng số đánh giá thay thế (xem Giới hạn Shopee).",
    ]


def roles_lines(p):
    r, d, t = p["rows"], p["dates"], p["targets"]
    return [
        "## 1. Vai trò từng bộ dữ liệu",
        "",
        "| Bộ dữ liệu | Vai trò | Chi tiết |",
        "|---|---|---|",
        f"| Olist (Brazil) | Dạy: học trọng số | 4 mốc {', '.join(p['trained_on']['cutoffs'])}, "
        f"{grp(r['olist_train'])} dòng sản phẩm. Kiểm tra mốc {d['val']}, thử mốc {d['test']} |",
        f"| Tiki | Đặt mốc ảnh; thi | Mốc {t['image']} ảnh là trung vị số ảnh của sản phẩm bán chạy trên Tiki (tập train). "
        f"Đề thi: Tiki 2023, {grp(r['tiki_test'])} sản phẩm |",
        f"| Shopee (Đài Loan) | Thi; không dùng để học trọng số | {grp(r['shopee_test'])} sản phẩm. Xem Giới hạn Shopee |",
    ]


def markets_lines(p):
    m, g = p["metrics"], p["gate"]["per_market"]
    lines = [
        "## 3. Bảng 3 sàn",
        f"Đúng {per100(m['olist_test'][LEARNED]['roc_auc'])}/100 cặp nghĩa là: lấy 100 cặp, mỗi cặp gồm một sản phẩm "
        "bán chạy và một sản phẩm không bán chạy. Điểm xếp đúng sản phẩm bán chạy lên trên trong bấy nhiêu cặp. "
        "Đoán bừa được 50/100. Số trong ngoặc là khoảng 95%.",
        "Gấp N lần: tỉ lệ bán chạy của 20% sản phẩm điểm cao chia cho 20% điểm thấp.",
        "Chia đều: mọi yếu tố được chấm trong bộ đó có cùng trọng số, không dùng máy học. "
        "Olist có 4 yếu tố (mỗi cái 25%), Tiki và Shopee có 3 (mỗi cái 33%).",
        "",
        "| Bộ thi | Đúng (trên 100 cặp) | Chia đều | Gấp (lần) |",
        "|---|---|---|---|",
    ]
    for label, k in MARKET_ROWS:
        a = m[k]
        lines.append(f"| {label} | {per100(a[LEARNED]['roc_auc'])} ({band(a[LEARNED]['auc_ci95'])}) "
                     f"| {per100(a[EQUAL]['roc_auc'])} | {num(g[k]['lift'])} |")
    tiki, shop = g["tiki_test"]["vs_equal_ci"], g["shopee_test"]["vs_equal_ci"]
    lines += [
        "",
        f"Học trừ chia đều (khoảng 95% của chênh lệch): Tiki {ci_text(tiki)}, Shopee {ci_text(shop)}. "
        "Khoảng chứa 0 nghĩa là hai cách ngang nhau. Cổng chỉ cần khoảng không âm hoàn toàn, "
        "tức là học không thua chia đều.",
        tie_text(p),
    ]
    return lines


def _review_note(p):
    c = p["coefficients"]["review"]
    if p["weights"]["review"] != FLOOR or c > 0:
        return []
    neg = num(c, 3).replace("-", "−")
    return ["", f"Hệ số học được của đánh giá là âm ({neg}) nên không được thưởng thêm; "
            f"yếu tố này giữ mức sàn {FLOOR}%, tức đánh giá tốt vẫn cộng tối đa {FLOOR} điểm."]


def material_lines(p):
    r = p["material_rate"]
    return [
        "## 6. Chất liệu (đo theo tên và mô tả, vì Tiki không có ô Chất liệu)",
        f"Trên Tiki (tập train), {num(r['share'], 1)}% sản phẩm có nêu chất liệu. "
        f"Trong nhóm nêu chất liệu, {num(r['top25_with'], 1)}% thuộc top 25% bán chạy; "
        f"nhóm không nêu là {num(r['top25_without'], 1)}%.",
        "Dữ liệu Tiki không cho thấy nêu chất liệu giúp bán chạy; chất liệu là tiêu chí thông tin bắt buộc, "
        "trọng số chính sách 10%.",
    ]


def ranges_lines(p):
    w, rg = p["weights"], p["ranges"]
    return [
        "## 4. Khoảng dao động trọng số",
        "Máy học lại 200 lần, mỗi lần lấy mẫu lại theo sản phẩm. Khoảng là phần 95% số lần trọng số rơi vào.",
        "",
        "| Yếu tố | Trọng số | Khoảng 95% |",
        "|---|---|---|",
        *[f"| {LABELS[k]} | {weight_text(p, k)} | {span(rg[k])} |" for k in KEYS],
        *_review_note(p),
    ]


def weight_text(p, k):
    w = p["weights"][k]
    return f"{w}% (mức sàn)" if k == "review" and w == FLOOR else f"{w}%"


def tiki_lines(p):
    t, o = p["tiki_check"]["tiki"], p["tiki_check"]["olist"]
    return [
        "## 5. Đối chiếu Tiki",
        "Cùng một cách tính trên hai bộ: học lại chỉ với ảnh và giá trên tập train, rồi xem máy phân bổ "
        "bao nhiêu % cho mỗi yếu tố.",
        "",
        "| Bộ | Ảnh | Giá |",
        "|---|---|---|",
        f"| Tiki | {t['image']}% | {t['price']}% |",
        f"| Olist | {o['image']}% | {o['price']}% |",
    ]
