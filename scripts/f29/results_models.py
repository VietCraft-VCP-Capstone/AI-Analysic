import ast

from scripts.f29.eval_kit import md_table
from scripts.f29.results_base import ci, frame, gap, num, pct, pval, wilson


B1_COLS = ["Cách làm", "Macro-F1 [CI 95%]", "Top-1 [CI 95%]", "Top-3", "F29 trừ cách làm (top-1)"]
B1_KEYS = [("img", "Chỉ ảnh"), ("txt", "Chỉ chữ"), ("probe", "Chỉ phần học, chưa trộn zero-shot"),
           ("zeroshot", "Zero-shot, không train"), ("tfidf", "TF-IDF chữ (baseline tốt nhất)")]
B1_FRAME = frame(B1_COLS, ["F29 gộp ảnh và chữ", *(name for _, name in B1_KEYS)])
B2_COLS = ["Cách làm", "Bài A macro-F1", "Bài A top-3", "Bài B macro-F1", "Bài B top-3"]
B2_FRAME = frame(B2_COLS, ["F29 model (TF-IDF + logistic)", "Regex hiện tại (22 từ khoá)",
                           "Luật đã sửa: text_vi.find_materials", "Chất liệu phổ biến nhất (da_that)",
                           "F29 model, bản bỏ dấu"])
B3_COLS = ["Tỉ lệ lỗi", "PR-AUC B3", "Baseline tốt nhất", "PR-AUC baseline", "B3 trừ baseline [CI 95%]",
           "Đạt (CI > 0)"]
PR_COLS = ["Tỉ lệ lỗi", "Precision ở 5% gắn cờ", "Recall ở 5% gắn cờ"]
FA_COLS = ["Mức", "α (báo nhầm cho phép)", "Ngưỡng điểm", "Báo nhầm đo được", "Khoảng Wilson 95%", "Đạt"]
B3_BASE = {"cosine": "Cosine SigLIP (ảnh so với chữ)", "b1_untrained": "B1 chưa train", "checklist": "Bảng kiểm"}
B3_FRAME = frame(B3_COLS, ["1%", "3%", "5%"])


def _b1_row(name, r, last):
    return {"Cách làm": name, "Macro-F1 [CI 95%]": ci(r["macro_f1"], r["macro_f1_ci95"]),
            "Top-1 [CI 95%]": ci(r["top1"], r["top1_ci95"]), "Top-3": num(r["top3"]),
            "F29 trừ cách làm (top-1)": last}


def b1_body(m: dict) -> str:
    t, c, rej = m["test"], m["compare"], m["reject"]
    rows = [_b1_row("F29 gộp ảnh và chữ", t["fused"], "–")]
    rows += [_b1_row(name, t[k], gap(c[k]["delta_top1"], c[k]["delta_ci95"])) for k, name in B1_KEYS]
    ok = all(c[k]["delta_ci95"][0] > 0 for k in ("img", "txt", "tfidf"))
    lines = [
        f"- Đọc: đoán đúng loại hàng ngay lần đầu {pct(t['fused']['top1'])} (top-1). "
        f"Top-3: {pct(t['fused']['top3'])}.",
        f"- Cổng: {'đạt' if ok else 'không đạt'}. Gộp hơn chỉ ảnh, chỉ chữ và TF-IDF, khoảng tin cậy không chứa 0.",
        f"- Trộn zero-shot không cải thiện hàng đã train (Holm p {pval(c['probe']['holm_p'])}).",
        f"- Từ chối: {pct(rej['test']['rate'])} mẫu test. Khi trả lời, đúng {pct(rej['test']['acc_answered'])} "
        f"(mục tiêu 95%, chọn trên val; trên val là {pct(rej['val']['acc_answered'])}).",
        "- Loại chưa train (tranh, laptop, điện thoại) không có nhãn test, nên chỉ có tỉ lệ từ chối.",
    ]
    return "\n".join([md_table(rows, B1_COLS), "", *lines])


def _b2_row(name, a, b):
    return {"Cách làm": name, "Bài A macro-F1": num(a["macro_f1"]), "Bài A top-3": num(a.get("top3")),
            "Bài B macro-F1": num(b["macro_f1"]), "Bài B top-3": num(b.get("top3"))}


def b2_body(m: dict) -> str:
    a, b, u, g = m["test"]["A"], m["test"]["B"], m["test_unaccented"], m["gate_A"]
    rows = [
        _b2_row("F29 model (TF-IDF + logistic)", a["model"], b["model"]),
        _b2_row("Regex hiện tại (22 từ khoá)", a["baseline_current"], b["baseline_current"]),
        _b2_row("Luật đã sửa: text_vi.find_materials", a["baseline_text_vi"], b["baseline_text_vi"]),
        _b2_row("Chất liệu phổ biến nhất (da_that)", a["baseline_majority"], b["baseline_majority"]),
        _b2_row("F29 model, bản bỏ dấu", u["A"]["model"], u["B"]["model"]),
    ]
    d = a["model"]["macro_f1"] - a["baseline_text_vi"]["macro_f1"]
    ok = d >= 0.10 and g["delta_ci95"][0] > 0
    lines = [
        "- Bài A còn chữ chất liệu. Bài B đã xoá mọi chữ chất liệu, khó hơn.",
        f"- Cổng PROTOCOL (hơn luật đã sửa, tức text_vi.find_materials, ≥ 10 điểm và CI không chứa 0): "
        f"{'đạt' if ok else 'không đạt'}. Chênh {gap(d, g['delta_ci95'])} điểm trên bài A.",
        "- Trên 102 sản phẩm VietCraft, model thua luật (xem Kết quả âm).",
        f"- Bỏ dấu làm điểm tụt từ {num(a['model']['macro_f1'])} xuống {num(u['A']['model']['macro_f1'])}: "
        "model học trên chữ có dấu.",
    ]
    return "\n".join([md_table(rows, B2_COLS), "", *lines])


def _lab(k: str, p: dict) -> str:
    return f"{float(k) * 100:g}% ({p['n_pos']} lỗi / {p['n_neg']} sạch)"


def _b3_row(k, p):
    best = p["best_baseline"]
    b, base = p["b3"]["pr_auc"], p["baselines"][best]["pr_auc"]
    return {"Tỉ lệ lỗi": _lab(k, p), "PR-AUC B3": num(b), "Baseline tốt nhất": B3_BASE[best],
            "PR-AUC baseline": num(base), "B3 trừ baseline [CI 95%]": gap(b - base, p["delta_ci95"]),
            "Đạt (CI > 0)": "có" if p["delta_ci95"][0] > 0 else "không"}


def _pr_row(k, p):
    return {"Tỉ lệ lỗi": _lab(k, p), "Precision ở 5% gắn cờ": num(p["b3"]["precision_at_5"]),
            "Recall ở 5% gắn cờ": num(p["b3"]["recall_at_5"])}


def _verdict(rate, alpha, hi) -> str:
    if rate > alpha:
        return "không đạt"
    return "đạt" if hi <= alpha else "đạt theo điểm ước lượng; cận trên vượt mục tiêu"


def _fa_row(name, d):
    k = round(d["rate"] * d["n_clean"])
    lo, hi = wilson(k, d["n_clean"])
    return {"Mức": name, "α (báo nhầm cho phép)": pct(d["alpha"]), "Ngưỡng điểm": num(d["threshold"]),
            "Báo nhầm đo được": f"{pct(d['rate'], 2)} ({k}/{d['n_clean']})",
            "Khoảng Wilson 95%": f"[{pct(lo, 2)}; {pct(hi, 2)}]", "Đạt": _verdict(d["rate"], d["alpha"], hi)}


def b3_body(m: dict) -> str:
    fa, blk = m["false_alarm"], m["false_alarm"]["block"]
    verdict = "chưa đạt" if blk["rate"] > blk["alpha"] else "đạt"
    lines = [
        "- B3 đoán tin có ảnh, chữ hoặc loại hàng lệch nhau. Số đo dùng lỗi mô phỏng (tráo ảnh, đổi loại), "
        "vì chưa đủ lỗi thật.",
        "- Ở 3% và 5% B3 hơn baseline rõ. Ở 1% khoảng tin cậy chạm 0, nên chưa chứng minh được.",
        f"- Báo nhầm mức chặn {pct(blk['rate'], 2)} so với α {pct(blk['alpha'])}: {verdict}. "
        "Muốn kiểm mức 0,5% cần ít nhất 2.000 tin sạch.",
        f"- Chế độ: {m['mode']} (theo dõi: ghi lại để đo, chưa hiện cho người bán). Quy tắc: {m['mode_rule']}.",
        "- Ngưỡng chọn trên val, không chỉnh trên test.",
    ]
    tables = [
        md_table([_b3_row(k, p) for k, p in m["prevalence"].items()], B3_COLS),
        md_table([_pr_row(k, p) for k, p in m["prevalence"].items()], PR_COLS),
        md_table([_fa_row("Cảnh báo (warn)", fa["warn"]), _fa_row("Chặn (block)", blk)], FA_COLS),
    ]
    return "\n\n".join([*tables, "\n".join(lines)])


C_COLS = ["Cách làm", "SRCC", "PLCC", "KRCC"]
C_LABELS = ["C1 · MLP (cấu hình chọn trên val)", "Ngưỡng cố định hiện tại (cờ lỗi cũ)",
            "Laplacian (độ nét)", "BRISQUE / NIQE (chưa đo)", "SigLIP2 zero-shot, ảnh thu nhỏ",
            "SigLIP2 zero-shot, vùng cắt gốc"]
C_FRAME = frame(C_COLS, C_LABELS)
C_NOTE = "Trọng số KonIQ chỉ cho demo học thuật; bản thương mại phải train lại."
C_PENDING = "Đang chờ số: model C1 chưa train xong"
KEYS = [("SRCC", "srcc"), ("PLCC", "plcc"), ("KRCC", "krcc")]
ABL = [("crop", "Ablation: MLP chỉ vector SigLIP2, vùng cắt gốc"),
       ("resize", "Ablation: MLP chỉ vector SigLIP2, ảnh thu nhỏ")]
VAL_NAMES = {"hand": "thủ công", "vector": "vector SigLIP2", "both": "cả hai"}


def srcc_median(test: dict) -> float:
    return (test.get("summary", {}).get("srcc") or {}).get("median") or test["srcc"]


def _c1(test: dict, k: str) -> str:
    s = test.get("summary", {}).get(k) or {}
    if s.get("median") is not None:
        return f"{num(s['median'])} [{num(s['p2_5'])}; {num(s['p97_5'])}]"
    return f"{num(test.get(k))} ± {num(test.get(k + '_std'))}"


def _abl(a: dict, k: str) -> str:
    return f"{num(a[k])} ± {num(a[k + '_std'])}"


def _chosen(m: dict) -> str:
    n = len(m["hand_cols"])
    what = {"hand": f"{n} đặc trưng thủ công", "vector": "vector SigLIP2 (vùng cắt 224 px)",
            "both": f"vector SigLIP2 và {n} đặc trưng thủ công"}[m["features"]]
    return f"C1 · MLP trên {what} (cấu hình thắng trên val)"


def _gate(test: dict) -> str:
    med = srcc_median(test)
    return f"Cổng: SRCC trên KonIQ test {num(med)} (ngưỡng 0,85): {'đạt' if med >= 0.85 else 'không đạt'}."


def _mode_line(m: dict) -> str:
    if m.get("mode") is None:
        return "- Bản 1 đã được thay bằng bản 2 (xem C2). Chế độ bản 1: chưa ghi trong metrics.json, mặc định shadow."
    return f"- Chế độ trong app: {m['mode']} (đọc từ metrics.json)."


def _val_line(m: dict) -> str:
    best = {}
    for key, v in m["val_srcc"].items():
        kind = ast.literal_eval(key)[0]
        best[kind] = max(best.get(kind, -1), v["median"] or -1)
    return "- Chọn trên val (SRCC trung vị): " + ", ".join(f"{VAL_NAMES[k]} {num(best[k])}" for k in VAL_NAMES) + "."


def _abl_line(m: dict) -> str:
    med, r = srcc_median(m["test"]), m["ablation"]["resize"]["srcc"]
    return (f"- Ablation dùng cùng siêu tham số với cấu hình thủ công, không chọn lại trên val. "
            f"Trên test, ảnh thu nhỏ đạt SRCC {num(r)}, cấu hình thủ công {num(med)}. "
            "Không đổi cấu hình theo số test (PROTOCOL mục 0).")


def c_body(m: dict) -> str:
    t, b = m["test"], m["baselines"]
    rows = [{C_COLS[0]: _chosen(m), **{col: _c1(t, k) for col, k in KEYS}}]
    rows += [{C_COLS[0]: lbl, **{col: _abl(m["ablation"][name], k) for col, k in KEYS}} for name, lbl in ABL]
    bases = [b.get("issues"), b.get("laplacian"), None, b.get("zeroshot_resize"), b.get("zeroshot_crop")]
    rows += [{C_COLS[0]: name, **{col: num((r or {}).get(k)) for col, k in KEYS}}
             for name, r in zip(C_LABELS[1:], bases)]
    lines = [
        _gate(t),
        _mode_line(m),
        _val_line(m),
        _abl_line(m),
        "- SRCC và PLCC đo mức đồng thuận giữa điểm model và điểm người chấm "
        "(1 là khớp hoàn toàn, 0 là không liên quan).",
        "- Số của C1 là trung vị qua 10 seed, kèm khoảng 2,5–97,5%. "
        "Nếu chưa có khoảng, dùng trung bình ± độ lệch chuẩn.",
        "- Chia KonIQ: ngẫu nhiên seed 0, cùng cỡ 7.058 / 1.000 / 2.015, vì OSF không kèm file chia chính thức.",
        f"- {C_NOTE}",
    ]
    return "\n".join([md_table(rows, C_COLS), "", *lines])


C2_COLS = ["Đo trên", "Số mẫu", "C2 (bản 2)", "Cờ cũ", "C1 bản 1", "Ghi chú"]
C2_FRAME = frame(C2_COLS, ["Tiki giữ riêng (SRCC)", "VietCraft (AUC)", "KonIQ kiểm phụ (SRCC)"])
REASON_COLS = ["Lý do", "Số ảnh xấu", "AUC C2", "AUC cờ cũ", "AUC C1 bản 1"]
MIN_BAD = 10


def _tiki(m: dict) -> dict:
    s, tt = m["test"]["summary"]["srcc"], m["test_threshold"]
    return {"Đo trên": "Tiki giữ riêng (SRCC, chia theo ảnh gốc)", "Số mẫu": f"{m['images']} ảnh gốc",
            "C2 (bản 2)": f"{num(s['median'])} [{num(s['p2_5'])}; {num(s['p97_5'])}]",
            "Cờ cũ": "–", "C1 bản 1": "–",
            "Ghi chú": f"ngưỡng {m['threshold']}: bắt {pct(tt['recall'])} ảnh xấu, báo nhầm {pct(tt['fpr'])} ảnh tốt"}


def _vc(vc: dict) -> dict:
    return {"Đo trên": "VietCraft (AUC, ảnh đạt là lớp dương)",
            "Số mẫu": f"{vc['n']} ảnh, {vc['n_products']} sản phẩm",
            "C2 (bản 2)": ci(vc["v2"]["auc"], vc["v2"]["ci95"]),
            "Cờ cũ": ci(vc["flag"]["auc"], vc["flag"]["ci95"]),
            "C1 bản 1": ci(vc["v1"]["auc"], vc["v1"]["ci95"]),
            "Ghi chú": f"{vc['n_bad']} ảnh không đạt theo nhãn AI"}


def _konig(m: dict) -> dict:
    return {"Đo trên": "KonIQ kiểm phụ (SRCC)", "Số mẫu": "tập test KonIQ",
            "C2 (bản 2)": num(m["konig"]["srcc"]), "Cờ cũ": "–", "C1 bản 1": num(m["konig_v1_srcc"]),
            "Ghi chú": f"C2 thấp hơn bản 1 {num(m['konig_v1_srcc'] - m['konig']['srcc'])} điểm SRCC: "
                       "model nghiêng về ảnh hỏng nhân tạo"}


def _reason_row(r: str, d: dict) -> dict:
    if "v2" not in d:
        return {"Lý do": r, "Số ảnh xấu": str(d["n_bad"]), "AUC C2": "ít mẫu", "AUC cờ cũ": "–", "AUC C1 bản 1": "–"}
    return {"Lý do": r, "Số ảnh xấu": str(d["n_bad"]), "AUC C2": num(d["v2"]["auc"]),
            "AUC cờ cũ": num(d["flag"]["auc"]), "AUC C1 bản 1": num(d["v1"]["auc"])}


def _c2_gate(vc: dict) -> str:
    d = vc["delta_v2_flag"]
    lo = d["ci95"][0]
    verdict = "đạt" if lo > 0 else "không đạt"
    edge = f", sát nút (cận dưới {num(lo, 3)})" if 0 < lo < 0.01 else ""
    return (f"- Cổng (PLAN mục 2): AUC C2 − cờ cũ = {gap(d['diff'], d['ci95'])}, khoảng tin cậy không chứa 0: "
            f"{verdict}{edge}.")


def c2_body(m: dict) -> str:
    vc = m["vietcraft"]
    rows = [_tiki(m), _vc(vc), _konig(m)]
    reasons = [_reason_row(r, d) for r, d in vc["by_reason"].items()]
    at = vc["at_threshold"]
    lines = [
        _c2_gate(vc),
        f"- Ở ngưỡng {at['threshold']:g}: {at['hits']}/{at['flagged']} ảnh bị cờ là ảnh xấu (cổng cần ≥ 60%); "
        f"cờ oan {pct(at['fpr'])} ảnh tốt, bắt {pct(at['recall'])} ảnh xấu.",
        f"- Chế độ trong app: {m['mode']}. Lý do: {m['mode_reason']}.",
        f"- Bật live cần ít nhất {MIN_BAD} ảnh xấu trên VietCraft. Lý do có ít hơn thì ghi 'ít mẫu'.",
    ]
    return "\n\n".join([md_table(rows, C2_COLS), md_table(reasons, REASON_COLS), "\n".join(lines)])
