from scripts.li.report_parts import AXIS_LABELS, SET_LABELS, ablation_table, ci, f3, metrics_table, pct, signed

FUSION = "Model gộp (fusion)"


def _yes(v):
    return "có" if v else "không"


def gate_lines(m):
    best, val = m["best_baseline"], m["best_baseline"]["val_choice"]
    return [
        f"Quy tắc gắn nhãn (spec §1.2): so với baseline mạnh nhất trên chính test tiki26 `{best['name']}` "
        f"(AUC {f3(best['auc'])}): chênh {signed(best['delta'])}, CI95 {ci(best['ci95'])} → "
        f"{'thắng có ý nghĩa' if best['significant'] else 'không thắng có ý nghĩa'}.",
        f"Tham khảo: baseline mạnh nhất trên validation là `{val['name']}` (AUC test {f3(val['auc'])}): chênh "
        f"{signed(val['delta'])}, CI95 {ci(val['ci95'])} → {'có ý nghĩa' if val['significant'] else 'không có ý nghĩa'}. "
        "So sánh này không dùng để gắn nhãn.",
    ]


def _gate_table(m):
    best = m["best_baseline"]
    rows = [("Mạnh nhất trên test tiki26 (spec §1.2)", best, "gắn nhãn chứng cứ"),
            ("Mạnh nhất trên validation tiki26", best["val_choice"], "tham khảo")]
    head = ["| Cách chọn baseline | Baseline | AUC baseline (test) | Chênh AUC | CI95 ghép cặp | Có ý nghĩa | Vai trò |",
            "|---|---|---|---|---|---|---|"]
    body = [f"| {a} | `{b['name']}` | {f3(b['auc'])} | {signed(b['delta'])} | {ci(b['ci95'])} | {_yes(b['significant'])} "
            f"| {c} |" for a, b, c in rows]
    extra = [f"- {SET_LABELS[k]}, cùng baseline `{best['name']}`: chênh {signed(v['delta'])}, CI95 {ci(v['ci95'])}"
             for k, v in best.get("secondary", {}).items()]
    return "\n".join(head + body) + ("\n\nTập phụ, chỉ để đối chiếu:\n\n" + "\n".join(extra) if extra else "")


def row_labels(m):
    out = {}
    for a, e in (m.get("axis_modes") or {}).items():
        state = "đang phục vụ" if e["mode"] == "model" else "không phục vụ"
        out[f"Chỉ trục {a}"] = f"Model trục {AXIS_LABELS[a]}: học có giám sát, {state}"
        out[f"Công thức trục {a}"] = f"Công thức trục {AXIS_LABELS[a]}: đang phục vụ, đo hậu kiểm"
    return out


def results_section(m):
    labels = row_labels(m)
    parts = ["Model gộp so với baseline trên test tiki26 (CI bootstrap ghép cặp theo seller):", _gate_table(m),
             modes_section(m)]
    for key, label in SET_LABELS.items():
        rows = m["tables"].get(key) or {}
        if any(rows.values()):
            parts += [f"### {label}", metrics_table({labels.get(n, n): v for n, v in rows.items()})]
    parts.append("Dòng \"Model trục …: học có giám sát, không phục vụ\" là model đã bị thay bằng công thức; điểm trục "
                 "người bán thấy đến từ dòng \"Công thức trục …: đang phục vụ\". Các dòng công thức được tính sau khi đã "
                 "chọn chế độ chấm, chỉ để mô tả, không dùng để quyết định.")
    return "\n\n".join(parts)


def selection_section(sel):
    if not sel:
        return "_Chưa chạy `scripts/li/select_features.py`._"
    head = ["| Biến thể | " + " | ".join(f"{SET_LABELS[s]}: AUC | Chênh so với base [CI95] | Brier | ECE" for s in sel["sets"])
            + " |", "|---" * (1 + 4 * len(sel["sets"])) + "|"]
    body = []
    for name, r in sel["variants"].items():
        cells = [f"{f3(r[s]['roc_auc'])} | {signed(r[s]['delta_vs_base'])} {ci(r[s]['delta_ci95'])} | "
                 f"{r[s]['brier']:.4f} | {r[s]['ece']:.4f}" for s in sel["sets"]]
        body.append(f"| {name} | " + " | ".join(cells) + " |")
    n = {s: next(iter(sel["variants"].values()))[s]["n"] for s in sel["sets"]}
    kept = ", ".join(f"`{k}`" for k in sel["kept"]) or "không giữ ứng viên nào"
    return "\n\n".join([
        "Hai ứng viên được thử trên validation, test không dùng: `text_lr` (xác suất TF-IDF + logistic theo nhóm, "
        "out-of-fold theo seller cho dòng train) và `title_pca_*` (PCA 16 chiều của vector tiêu đề, fit trên train).",
        f"Quy tắc định trước: {sel['rule']}. Số dòng: " + ", ".join(f"{SET_LABELS[s]} {v}" for s, v in n.items()) + ".",
        "\n".join(head + body), f"Kết quả: {kept}. Model dùng {len(sel['features'])} cột."])


def ablation_section(m):
    return "\n\n".join([
        ablation_table(m["ablation"], m["evidence"]),
        "Ablation, nhãn chứng cứ và phép so baseline đều tính trên cùng test tiki26. Quy tắc: trục là `measured` khi "
        "lift ≥ 0,005, CI95 ghép cặp không chứa 0 và model gộp thắng có ý nghĩa baseline mạnh nhất trên test. "
        "Trục tag là công thức minh bạch, không học có giám sát, nên luôn là `practice`."])


def modes_section(m):
    modes = m.get("axis_modes")
    if not modes:
        return ""
    val = lambda d, k: f"{f3(d[k]['auc'])} {ci(d[k]['ci95'])}" if k in (d or {}) else "—"
    head = ["| Trục | Validation tiki26: ROC-AUC model [CI95] | Validation gộp: ROC-AUC model [CI95] | Cách chấm | Lý do | "
            "ROC-AUC công thức đang phục vụ: validation tiki26 / test tiki26 (đo hậu kiểm) |", "|---|---|---|---|---|---|"]
    body = [f"| {AXIS_LABELS[a]} | {val(e['val'], 'val')} | {val(e['val'], 'val_all')} | "
            f"{'model học có giám sát' if e['mode'] == 'model' else '**công thức minh bạch**'} | {e.get('reason', '—')} | "
            + (f"{val(e.get('formula'), 'val')} / {val(e.get('formula'), 'test')}" if e.get("formula") else "—") + " |"
            for a, e in modes.items()]
    spec = m.get("formulas") or {}
    weights = "; ".join(f"{AXIS_LABELS[a]}: " + ", ".join(f"{k} {v}" for k, v in spec[a].items())
                        for a in modes if a in spec)
    return "\n\n".join([
        "### Chế độ chấm từng trục (quyết định trên validation)", f"Quy tắc: {m['axis_mode_rule']}.",
        "\n".join(head + body),
        "Trục dùng công thức được chấm bằng phân vị của điểm công thức so với listing Tiki cùng nhóm trong quần thể "
        "tham chiếu (cùng quần thể với phân vị của trục dùng model), luôn mang nhãn `practice`. Model gộp không đổi.",
        f"Trọng số công thức (`app/core/listing_intel/formulas.py`): {weights}. Ngưỡng: {spec.get('ranges')}, "
        f"dải độ dài tiêu đề {spec.get('title_band')}, lặp từ tối đa {spec.get('max_repeat')}, dải độ sáng "
        f"{spec.get('brightness_range')}. `resolution` là cạnh ngắn của ảnh sau khi thu về 256 px, tức thực chất đo tỉ "
        "lệ khung; ảnh Tiki tham chiếu đều vuông 256 × 256 nên phần này bằng 1 với mọi ảnh tham chiếu và chỉ hạ điểm "
        "ảnh không vuông.",
        "Công thức chữ chỉ dùng tiêu đề và chất liệu khai báo (listing Tiki tham chiếu không có mô tả), và trừ "
        f"{spec.get('missing_penalty')} cho mỗi thuộc tính bắt buộc còn thiếu theo nhóm: "
        + "; ".join(f"{a}: {', '.join(g)}" for a, g in (spec.get("required") or {}).items()) + "."])


def evidence_line(m):
    return ", ".join(f"{AXIS_LABELS[a]}: `{v}`" for a, v in m["evidence"].items())


def coverage_line(cov):
    return "; ".join(f"{s}: {pct(c.get('trend_matched'))} dòng khớp ≥ 1 từ khoá trend" for s, c in cov.items())
