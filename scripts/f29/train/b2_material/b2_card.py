def _row(name: str, s: dict) -> str:
    return f"{name} {s['model']['macro_f1']} / {s['model']['top3']}"


def _gate(g: dict) -> str:
    lo, hi = g["delta_ci95"]
    verdict = "đạt" if g["ci_pass"] else "không đạt"
    return (f"- Cổng (bài A): mô hình − {g['best_baseline']} có CI95 [{lo}; {hi}] → {verdict} theo khoảng tin cậy. "
            "Cổng PROTOCOL còn thiếu baseline regex đã sửa (chưa dựng), nên cổng đầy đủ chưa kiểm được.")


def card(m: dict) -> str:
    A, B, uA, uB = m["test"]["A"], m["test"]["B"], m["test_unaccented"]["A"], m["test_unaccented"]["B"]
    rows = m["rows"]
    lines = [
        "# B2 · Đoán chất liệu từ tên và mô tả (v1)",
        "",
        f"- Việc làm: đoán 1 trong {len(m['classes'])} lớp chất liệu từ tên và mô tả (đã bỏ dòng Chất liệu).",
        f"- Dữ liệu: tiki23, {sum(rows.values())} tin có nhãn; chia theo người bán 70/15/15, seed 0.",
        f"- Số mẫu: train {rows['train']}, val {rows['val']}, test {rows['test']}.",
        f"- Mô hình: TF-IDF ký tự (2–5) + TF-IDF từ (1–2) → LogisticRegression C={m['C']} → hiệu chỉnh isotonic.",
        "- Kết quả test (macro-F1 / top-3):",
        f"  - Bài A (còn chữ chất liệu): {_row('mô hình', A)}; cách hiện tại {A['baseline_current']['macro_f1']}; "
        f"text_vi {A['baseline_text_vi']['macro_f1']}; lớp phổ biến nhất ({m['majority']}) {A['baseline_majority']['macro_f1']}",
        f"  - Bài B (đã xoá mọi từ chất liệu): {_row('mô hình', B)}; cách hiện tại {B['baseline_current']['macro_f1']}; "
        f"text_vi {B['baseline_text_vi']['macro_f1']}; lớp phổ biến nhất {B['baseline_majority']['macro_f1']}",
        f"  - Bản bỏ dấu (cùng mô hình): bài A {uA['model']['macro_f1']}, bài B {uB['model']['macro_f1']}",
        _gate(m["gate_A"]),
        "- Giới hạn: jean gộp vào khac. Dữ liệu là Tiki Fashion và tiki23, không phải sản phẩm VietCraft.",
        "- Giới hạn: mô hình chỉ học trên chữ có dấu; bản bỏ dấu là đo độ bền, không phải huấn luyện.",
    ]
    return "\n".join(lines) + "\n"
