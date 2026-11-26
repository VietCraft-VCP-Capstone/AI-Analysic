NAMES = {"probe": "probe", "zero_shot": "zero-shot", "blend": "trộn"}


def _val_line(m: str, t: dict) -> str:
    return f"  - {NAMES[m]}: PR-AUC val 3% {t['0.03']}, 5% {t['0.05']}, trung bình {t['mean']}"


def _prev_line(p: str, r: dict) -> str:
    pa, lo, hi = r["pr_auc"], *r["delta_ci95"]
    return (f"  - lệch {float(p) * 100:g}% ({r['n_pos']} lệch / {r['n_neg']} sạch): PR-AUC trộn {pa['blend']}; "
            f"ứng viên khác: probe {pa['probe']}, zero-shot {pa['zero_shot']}; cosine {pa['cosine']}, "
            f"B3 v1 {pa['b3_v1']}; chênh lệch với {r['best_baseline']} CI95 [{lo}, {hi}]")


def _attr_line(g: str, r: dict) -> list[str]:
    if "macro_f1" not in r:
        return [f"  - {g}: không có mẫu test"]
    head = (f"  - {g} (n test={r['n']}): macro-F1 probe {r['macro_f1']} vs zero-shot {r['macro_f1_zero_shot']}, "
            f"McNemar p={r['mcnemar_p_vs_zero_shot']}")
    rows = "; ".join(f"{float(p) * 100:g}%: {x['n_pos']} lệch, trộn {x['pr_auc']['blend']} vs cosine "
                     f"{x['pr_auc']['cosine']}" for p, x in r["prevalence"].items())
    return [head, f"      {rows}"]


def card(m: dict) -> str:
    fit, sel = m["fit"], m["selection"]
    fitted = [g for g, r in fit.items() if "C" in r]
    skipped = [f"{g} ({r['skip']})" for g, r in fit.items() if "skip" in r]
    fa = next(iter(m["prevalence_false_alarm"].values()))
    lines = [
        "# B3 bản 2 · AI kiểm thuộc tính ảnh so với mô tả (v1)",
        "",
        "- Việc làm: ảnh không khớp thuộc tính người bán ghi (ví dụ tên ghi 'trơn' nhưng ảnh là 'in hình').",
        f"- Dữ liệu: {m['rows']['total']} ảnh có vector (tiki26 + TikiFashion); tiki23 không có vector ảnh. "
        f"Train/val/test {m['rows']['train']}/{m['rows']['val']}/{m['rows']['test']}, chia theo người bán "
        f"và cụm ảnh/chữ gần trùng, seed {m['seeds']['split']}.",
        f"- Nhóm train: {', '.join(fitted)}. Bỏ: {'; '.join(skipped) or 'không'}.",
        "- Nhãn yếu từ tiêu đề. Một nhóm chỉ có nhãn khi đúng một giá trị được nhắc.",
        "- Ba phương pháp: probe = LogisticRegression (C theo macro-F1 val), zero-shot = SigLIP với prompt VI+EN, "
        "trộn = trung bình probe và zero-shot. Xác suất gốc, không isotonic.",
        f"- Phương pháp cố định: {NAMES[sel['chosen']]} (chọn trên val ở fix round 1, không chọn lại). "
        "Bảng val dưới đây tính lại theo cặp hiện tại, chỉ để tham khảo:",
        *[_val_line(k, t) for k, t in sel["val_pr_auc_current_pairs"].items()],
        "- Cặp tráo: cùng loại (B1), khác đúng một thuộc tính đang xét, hai giá trị trái ngược, "
        "không xung đột ở nhóm khác. Tối đa 3 cặp mỗi neo.",
        f"- Lệch trên test (seed {m['seeds']['pairs']}):",
        *[_prev_line(p, r) for p, r in m["prevalence"].items()],
        "- Theo từng thuộc tính (điểm chỉ dùng nhóm đó; không bật riêng ở runtime):",
        *[line for g, r in m["per_attribute"].items() for line in _attr_line(g, r)],
        f"- Ngưỡng conformal α={m['alpha']} trên val sạch của {NAMES[sel['chosen']]} → {m['t_warn']:.4f} "
        f"(n={m['n_cal']}). Báo nhầm trên test sạch: {fa * 100:.1f}%{' (vượt α)' if fa > m['alpha'] else ''}.",
        f"- Chế độ: {m['mode']}. Quy tắc: {m['mode_rule']}.",
        "- Chỉ cảnh báo, không chặn. Điểm = max over nhóm (P(giá trị đối lập) − P(giá trị người bán ghi)).",
        "- Giới hạn: tiki23 chưa có vector ảnh; nhóm set bị bỏ vì chỉ có nhãn một chiều; số mẫu lệch test còn ít.",
    ]
    return "\n".join(lines) + "\n"
