import json
import math
from pathlib import Path

from scripts.f29.eval_kit import md_table


def load(path: Path) -> dict | None:
    return json.loads(path.read_text("utf-8")) if path.exists() else None


def num(v, nd: int = 3) -> str:
    return "–" if v is None else f"{v:.{nd}f}".replace(".", ",")


def pct(v, nd: int = 1) -> str:
    return "–" if v is None else num(100 * v, nd) + "%"


def ci(v, rng) -> str:
    return f"{num(v)} [{num(rng[0])}; {num(rng[1])}]"


def gap(v, rng) -> str:
    return f"{'+' if v >= 0 else ''}{num(v)} [{num(rng[0])}; {num(rng[1])}]"


def pval(p) -> str:
    return "< 0,001" if p < 0.001 else num(p)


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    p, den = k / n, 1 + z * z / n
    mid = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return mid - half, mid + half


def frame(cols: list[str], labels: list[str]) -> str:
    return md_table([{cols[0]: lab, **{c: "–" for c in cols[1:]}} for lab in labels], cols)


GLOSSARY = [
    ("macro-F1", "điểm trung bình đều cho mọi loại hàng, từ 0 đến 1 (1 là đúng hết). "
                 "Loại ít mẫu được tính ngang loại đông mẫu."),
    ("top-1 / top-3", "top-1 là đoán đúng ngay lần đầu; top-3 là đáp án đúng nằm trong 3 gợi ý đầu."),
    ("PR-AUC", "điểm xếp tin có lỗi lên trước tin sạch; 1 là hoàn hảo. "
               "Đoán bừa thì bằng tỉ lệ lỗi trong tập."),
    ("precision / recall", "precision: trong các tin bị báo, bao nhiêu tin thật sự có lỗi. "
                           "recall: trong các tin có lỗi, bao nhiêu tin bị báo."),
    ("khoảng tin cậy bootstrap (CI 95%)", "khoảng số đo có thể dao động nếu làm lại với mẫu khác, "
                                          "tính bằng cách bốc lại dữ liệu 1.000 lần. "
                                          "Khoảng chứa 0 nghĩa là chưa chắc chắn."),
    ("Wilson 95%", "khoảng tin cậy cho một tỉ lệ khi số mẫu ít, ví dụ 14 trên 744."),
    ("conformal", "cách đặt ngưỡng để tỉ lệ báo nhầm trên tin sạch không vượt mức α đã hứa, ví dụ 2%."),
    ("shadow", "chế độ theo dõi: model chạy và ghi kết quả để đo, nhưng chưa hiện cho người bán."),
    ("hint", "chế độ gợi ý: model rớt cổng live, kết quả hiện cho người bán kèm nhãn 'AI gợi ý, chưa kiểm chứng', "
             "không đổi điểm."),
]
K_COLS = ["Model", "Cách chia", "Số mẫu test", "Lần mở tập test (PROTOCOL 7)"]
K_ROWS = [
    {"Model": "B1 · tập cũ (cụm chỉ theo ảnh)", "Cách chia": "Cụm theo ảnh, 70/15/15", "Số mẫu test": "–",
     "Lần mở tập test (PROTOCOL 7)": "1 lần chạy + 2 lần reviewer đếm trùng; không hợp lệ, đã bỏ"},
    {"Model": "B1 · tập mới (cụm ảnh ∪ chữ)", "Cách chia": "Cụm ảnh hoặc chữ giống nhau, 70/15/15",
     "Số mẫu test": "744", "Lần mở tập test (PROTOCOL 7)": "1 lần (train lại sau khi sửa rò rỉ)"},
    {"Model": "B2 · chất liệu", "Cách chia": "Theo người bán, 70/15/15", "Số mẫu test": "804",
     "Lần mở tập test (PROTOCOL 7)": "2 lần (01:33, 05:50)"},
    {"Model": "B3 · mâu thuẫn", "Cách chia": "Theo cụm, 70/15/15; mẫu lệch sinh với seed 1",
     "Số mẫu test": "744 tin sạch; 8, 23, 39 tin lệch",
     "Lần mở tập test (PROTOCOL 7)": "3 lần (01:34, 01:38, 05:46); số ghi là lần 3"},
    {"Model": "I · ảnh trùng", "Cách chia": "Không train; chọn ngưỡng trên nhóm A (100 ảnh gốc), "
                                             "báo trên nhóm B (100 ảnh gốc)",
     "Số mẫu test": "800 bản sao; 339 cặp khó", "Lần mở tập test (PROTOCOL 7)": "Không dùng tập test"},
    {"Model": "C1 · chất lượng ảnh", "Cách chia": "Ngẫu nhiên seed 0, cùng cỡ 7.058 / 1.000 / 2.015 "
                                                  "(OSF không kèm file chia chính thức)",
     "Số mẫu test": "2.015 (KonIQ)", "Lần mở tập test (PROTOCOL 7)": "Mở khi train xong; chưa có số"},
]
K_LINES = [
    "- Chia theo nhóm (shop, hoặc cụm ảnh và chữ giống nhau), không chia ngẫu nhiên từng dòng. "
    "Nếu không, model thấy trước những tin gần giống đáp án.",
    "- Ngưỡng báo (conformal): chọn sao cho tỉ lệ báo nhầm trên tin sạch không quá α "
    "(cảnh báo 2%, chặn 0,5%).",
    "- So hai model trên cùng mẫu bằng McNemar; khi so nhiều cặp, hiệu chỉnh Holm. "
    "CI 95% bằng bootstrap theo nhóm, 1.000 lần.",
    "- Số lần mở tập test (bảng dưới) theo PROTOCOL mục 7. I không dùng tập test.",
]
A_COLS = ["Trường hợp", "Nguồn", "F29", "Công thức cũ (chỉ kiểm có ảnh)"]
A_ROWS = [
    {"Trường hợp": "Mặt sau áo in, 59,9 DPI", "Nguồn": "Sản phẩm thật (2 ca); test_print_check.py và smoke",
     "F29": "Chặn", "Công thức cũ (chỉ kiểm có ảnh)": "Không có bước kiểm DPI"},
    {"Trường hợp": "Mặt sau áo in, 47,9 DPI", "Nguồn": "Sản phẩm thật (2 ca); test_print_check.py và smoke",
     "F29": "Chặn", "Công thức cũ (chỉ kiểm có ảnh)": "Không có bước kiểm DPI"},
    {"Trường hợp": "Thiết kế có nền đặc", "Nguồn": "Test tự động (test_print_check.py)",
     "F29": "Cảnh báo", "Công thức cũ (chỉ kiểm có ảnh)": "Không có bước kiểm nền"},
    {"Trường hợp": "Thiết kế tràn 25% ra ngoài vùng in", "Nguồn": "Test tự động (test_print_check.py)",
     "F29": "Cảnh báo", "Công thức cũ (chỉ kiểm có ảnh)": "Không có bước kiểm vùng in"},
]
A_LINES = [
    "- DPI là số điểm ảnh trên mỗi inch khi in. Dưới 120 DPI thì F29 chặn, vì hình in ra dễ vỡ. "
    "Đây là luật tính toán, không phải model học máy, nên không có khoảng tin cậy.",
    "- Công thức cũ chỉ kiểm có ảnh hay không, nên không có bước kiểm DPI, nền hay vùng in.",
    "- Chỉ 2 ca in thật: chưa đủ để nói tỉ lệ bắt lỗi chung. "
    "Ca nền và tràn là ca tự sinh, biết trước đáp án.",
]


def glossary() -> str:
    return md_table([{"Thuật ngữ": t, "Nghĩa": d} for t, d in GLOSSARY], ["Thuật ngữ", "Nghĩa"])


def k_body() -> str:
    return "\n".join([*K_LINES, "", md_table(K_ROWS, K_COLS)])


def a_body() -> str:
    return "\n".join([md_table(A_ROWS, A_COLS), "", *A_LINES])
