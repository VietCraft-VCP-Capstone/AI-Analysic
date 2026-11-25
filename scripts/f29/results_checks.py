from scripts.f29.eval_kit import md_table
from scripts.f29.results_models import srcc_median
from scripts.f29.results_base import frame, gap, num, pct, pval


ATTR_COLS = ["Tỉ lệ lệch", "PR-AUC trộn (B3b)", "Baseline tốt nhất", "PR-AUC baseline",
             "B3b trừ baseline [CI 95%]", "Đạt (CI > 0)"]
ATTR_FRAME = frame(ATTR_COLS, ["3%", "5%"])
ATTR_BASE = {"cosine": "Cosine SigLIP (ảnh so với chữ)", "b3_v1": "B3 bản 1 (cờ loại hàng)"}
GROUP_COLS = ["Thuộc tính", "Số mẫu test", "Macro-F1 probe", "Macro-F1 zero-shot", "McNemar p"]
VC_COLS = ["Đo trên VietCraft", "Số sản phẩm", "Precision", "Recall", "Baseline cosine (precision)"]
PRECISION_GATE = 0.6


def _row(k: str, p: dict) -> dict:
    best = p["best_baseline"]
    b, base = p["pr_auc"]["blend"], p["pr_auc"][best]
    return {"Tỉ lệ lệch": f"{float(k) * 100:g}% ({p['n_pos']} lệch / {p['n_neg']} sạch)",
            "PR-AUC trộn (B3b)": num(b), "Baseline tốt nhất": ATTR_BASE[best], "PR-AUC baseline": num(base),
            "B3b trừ baseline [CI 95%]": gap(b - base, p["delta_ci95"]),
            "Đạt (CI > 0)": "có" if p["delta_ci95"][0] > 0 else "không"}


def _group_row(name: str, r: dict) -> dict:
    return {"Thuộc tính": name, "Số mẫu test": str(r["n"]), "Macro-F1 probe": num(r["macro_f1"]),
            "Macro-F1 zero-shot": num(r["macro_f1_zero_shot"]), "McNemar p": pval(r["mcnemar_p_vs_zero_shot"])}


def _vc_row(v: dict) -> dict:
    prec, rec, base = v["precision"], v["recall"], v["baselines"]["cosine"]["precision"]
    return {"Đo trên VietCraft": "B3b (cờ thuộc tính)", "Số sản phẩm": f"{v['n']} ({v['n_pos']} lệch)",
            "Precision": f"{num(prec['rate'])} ({prec['hits']}/{prec['n']})",
            "Recall": f"{num(rec['rate'])} ({rec['hits']}/{rec['n']})",
            "Baseline cosine (precision)": f"{num(base['rate'])} ({base['hits']}/{base['n']})"}


def _gates(m: dict, vc: dict) -> list[str]:
    tiki = all(p["delta_ci95"][0] > 0 for p in m["prevalence"].values())
    prec = vc["precision"]["rate"]
    vc_ok = prec is not None and prec >= PRECISION_GATE
    return [
        f"- Cổng live (Tiki): {'đạt' if tiki else 'không đạt'}. PR-AUC trộn phải hơn baseline tốt nhất "
        "và khoảng tin cậy không chứa 0 ở cả 3% và 5%.",
        f"- Cổng live (VietCraft): {'đạt' if vc_ok else 'không đạt'}. Precision {pct(prec)}, cần ≥ 60%.",
    ]


def _fa_line(m: dict) -> str:
    worst = max(m["prevalence_false_alarm"].values())
    verdict = "đạt" if worst <= m["alpha"] else "vượt α"
    return f"- Báo nhầm trên tin sạch test: cao nhất {pct(worst)} so với α {pct(m['alpha'])}: {verdict}."


def attr_body(m: dict, t: dict) -> str:
    vc = t["attr"]
    rows = [_row(k, p) for k, p in m["prevalence"].items()]
    groups = [_group_row(g, r) for g, r in m["per_attribute"].items() if "macro_f1" in r]
    lines = [
        *_gates(m, vc),
        f"- Chế độ: {m['mode']}. Quy tắc: {m['mode_rule']}.",
        _fa_line(m),
        f"- Trên VietCraft, cờ đúng {vc['tp']}, báo nhầm {vc['fp']}, bỏ sót {vc['fn']}. "
        "Nhãn do AI gắn, người dùng chưa kiểm.",
    ]
    return "\n\n".join([md_table(rows, ATTR_COLS), md_table(groups, GROUP_COLS),
                        md_table([_vc_row(vc)], VC_COLS), "\n".join(lines)])


KINDS = {"jpeg": "Nén JPEG", "resize": "Đổi kích thước", "crop": "Cắt giữa 80%", "flip": "Lật ngang",
         "rotate": "Xoay", "bright": "Đổi độ sáng", "text": "Thêm chữ", "border": "Thêm viền"}
I_COLS = ["Kiểu biến đổi", "Bắt ở mức cảnh báo", "Bắt ở mức info", "Baseline chỉ vector (cosine)"]
I_FRAME = frame(I_COLS, list(KINDS.values()))


def i_body(m: dict) -> str:
    rows = [{I_COLS[0]: KINDS[k], I_COLS[1]: pct(v["warn_recall"], 0), I_COLS[2]: pct(v["info_recall"], 0),
             I_COLS[3]: pct(v["recall_cos_only"], 0)} for k, v in m["per_kind_B"].items()]
    lo, hi = m["fpr_warn_wilson95_B"]
    k = round(m["fpr_warn_B"] * m["n_B_negatives"])
    lines = [
        f"- Đo trên {m['n_B_copies']} bản sao tự sinh từ ảnh VietCraft và {m['n_B_negatives']} cặp khác nhau khó. "
        "Ngưỡng chọn trên nhóm A, báo cáo trên nhóm B.",
        f"- Báo nhầm: {pct(m['fpr_warn_B'], 2)} ({k} trên {m['n_B_negatives']} cặp), "
        f"khoảng Wilson [{pct(lo, 2)}; {pct(hi, 2)}]. Điểm ước lượng đạt ≤ 1%, cận trên vượt 1%.",
        "- Cổng PROTOCOL 2/2 cặp dùng chung ảnh trong shop: đã kiểm 1 cặp bằng smoke ngày 21/11, "
        "cặp áo Chợ Bến Thành / áo trơn (Áo Thun Oversize Unisex In Hình Chợ Bến Thành, 6ad423e8…, "
        "và Áo Thun Trơn Cotton 100%…, 6ad329c6…; cùng shop, cùng một ảnh, ra duplicate_same_shop mức cảnh báo). "
        "Các cặp còn lại chưa kiểm lại trong bản này.",
        "- Cổng PROTOCOL 21/21 ảnh lấy từ link sàn khác: chưa đo. Bộ VietCraft hiện có 14 ảnh link sàn.",
        "- Thời gian mỗi ảnh chưa đo.",
    ]
    return "\n".join([md_table(rows, I_COLS), "", *lines])


TR_COLS = ["Mục", "Số mẫu", "F29", "Baseline", "Ghi chú"]
FLAGS = {"description_type:image_text_mismatch": "Cờ app: mô tả sai loại hàng (B3)",
         "description_type:image_text_or_category": "Cờ app: ảnh hoặc danh mục lệch (B3)",
         "material_conflict": "Cờ app: chất liệu mâu thuẫn",
         "material_missing": "Cờ app: thiếu chất liệu"}
TR_FRAME = frame(TR_COLS, ["B1 · loại hàng", "B2 · chất liệu", *FLAGS.values(), "B3b · thuộc tính", "C1 · ảnh",
                           "C2 · ảnh (bản 2)"])


def _flag_row(label, d):
    pr = f"precision {num(d['precision']['rate'])}; recall {num(d['recall']['rate'])}"
    note = f"{d['n_pos']} lỗi thật: {d['tp']} đúng, {d['fp']} báo nhầm, {d['fn']} bỏ sót"
    return {"Mục": label, "Số mẫu": f"{d['n']} tin", "F29": pr, "Baseline": "–", "Ghi chú": note}


def _c1_row(c):
    if c.get("status") != "ok":
        return {"Mục": "C1 · ảnh", "Số mẫu": "–", "F29": "chờ model C1", "Baseline": "–", "Ghi chú": "chưa có số"}
    return {"Mục": "C1 · ảnh", "Số mẫu": f"{c['n']} ảnh", "F29": f"AUC {num(c['auc_quality'])}",
            "Baseline": f"cờ cũ: AUC {num(c['auc_baseline'])}", "Ghi chú": f"{c['n_bad']} ảnh không đạt theo nhãn AI"}


def _attr_row(a):
    prec, rec, base = a["precision"], a["recall"], a["baselines"]["cosine"]["precision"]
    return {"Mục": "B3b · thuộc tính", "Số mẫu": f"{a['n']} sản phẩm",
            "F29": f"precision {num(prec['rate'])}; recall {num(rec['rate'])}",
            "Baseline": f"cosine: precision {num(base['rate'])}",
            "Ghi chú": f"{a['n_pos']} sản phẩm lệch theo nhãn AI; cờ đúng {a['tp']}, báo nhầm {a['fp']}, bỏ sót {a['fn']}"}


def _c2_row(c):
    if "v2" not in c:
        return {"Mục": "C2 · ảnh (bản 2)", "Số mẫu": "–", "F29": "chờ model C2", "Baseline": "–", "Ghi chú": "chưa có số"}
    return {"Mục": "C2 · ảnh (bản 2)", "Số mẫu": f"{c['n']} ảnh", "F29": f"AUC {num(c['v2']['auc'])}",
            "Baseline": f"cờ cũ: AUC {num(c['flag']['auc'])}", "Ghi chú": f"{c['n_bad']} ảnh không đạt theo nhãn AI"}


def transfer_body(t: dict) -> str:
    b1, b2 = t["b1"], t["b2"]
    o = b1["out_of_trained"]
    rows = [
        {"Mục": "B1 · loại hàng", "Số mẫu": f"{b1['n']} sản phẩm",
         "F29": f"top-1 {num(b1['top1']['rate'])}; top-3 {num(b1['top3']['rate'])}", "Baseline": "–",
         "Ghi chú": f"từ chối {pct(b1['reject_rate']['rate'])}; {o['n']} sản phẩm thuộc loại chưa train, "
                    f"bị từ chối {pct(o['reject_rate']['rate'])}"},
        {"Mục": "B2 · chất liệu", "Số mẫu": f"{b2['n']} sản phẩm",
         "F29": f"top-1 {num(b2['model']['top1']['rate'])}; top-3 {num(b2['model']['top3']['rate'])}",
         "Baseline": f"luật đã sửa: top-1 {num(b2['baseline_text_vi']['top1']['rate'])}; "
                     f"top-3 {num(b2['baseline_text_vi']['top3']['rate'])}",
         "Ghi chú": "model thua luật" if b2["model"]["top1"]["rate"] < b2["baseline_text_vi"]["top1"]["rate"]
         else "model hơn luật"},
    ]
    flags = {k: v for k, v in t["b3"].items() if "precision" in v}
    rows += [_flag_row(label, flags[k]) for k, label in FLAGS.items() if k in flags]
    rows += [_attr_row(t["attr"]), _c1_row(t["c1"]), _c2_row(t["c1v2"])]
    pos = [d["n_pos"] for d in flags.values()]
    lines = [
        f"- Trên {t['n_products']} sản phẩm và {t['n_images']} ảnh VietCraft đang bán. "
        "Nhãn do AI gắn, chưa được người dùng kiểm.",
        f"- B3b dùng bộ nhãn thuộc tính mới ({t['attr']['n']} sản phẩm); B1, B2, B3 và C1 dùng bộ cũ.",
        f"- Số lỗi thật rất ít ({min(pos)} đến {max(pos)} mỗi cờ), nên đây là chỉ dấu, không phải kết luận.",
        "- Tỉ lệ đồng ý giữa nhãn AI và người kiểm: chưa có. Người dùng chưa kiểm 25 sản phẩm và 20 ảnh.",
        "- Các cờ là cờ mô tả đang chạy trong app (check_listing). Cờ loại hàng (B3) đang ở chế độ shadow, "
        "nên không hiện cho người bán.",
    ]
    return "\n".join([md_table(rows, TR_COLS), "", *lines])


def _c1_bullets(c: dict | None, t: dict) -> list[str]:
    if c is None:
        return ["- **Chất lượng ảnh (C1) chưa có số đo**: metrics.json chưa có."]
    srcc, c1 = srcc_median(c["test"]), t["c1"]
    ok = srcc >= 0.85
    cmp = "hơn" if c1["auc_quality"] > c1["auc_baseline"] else "thua"
    verdict = "qua" if ok else "không qua"
    action = "→ đã thay bằng bản 2 (xem C2)" if not ok else "→ cần xem lại trước khi bật"
    r = c["ablation"]["resize"]
    rel = "cao hơn" if r["srcc"] > srcc else "thấp hơn"
    return [
        f"- **C1 {verdict} cổng**: SRCC {num(srcc)} {'≥' if ok else '<'} 0,85 (KonIQ). "
        f"Trên ảnh VietCraft AUC {num(c1['auc_quality'])}, {cmp} cờ lỗi cũ {num(c1['auc_baseline'])} "
        f"(chỉ {c1['n_bad']} ảnh xấu, nhãn AI) {action}.",
        f"- **Trên test, vector SigLIP ảnh thu nhỏ đạt SRCC {num(r['srcc'])} ± {num(r['srcc_std'])}**, "
        f"{rel} cấu hình thủ công được chọn trên val ({num(srcc)}). Không đổi cấu hình theo số test.",
    ]


def _attr_bullets(a: dict | None, t: dict) -> list[str]:
    if a is None:
        return ["- **B3b (thuộc tính ảnh) chưa có số đo**: metrics.json chưa có."]
    vc = t["attr"]
    tiki = all(p["delta_ci95"][0] > 0 for p in a["prevalence"].values())
    prec = vc["precision"]
    return [
        f"- **B3b ở chế độ {a['mode']}**: cổng Tiki {'đạt' if tiki else 'không đạt'} (CI của PR-AUC trộn − "
        f"cosine chứa 0). VietCraft precision {num(prec['rate'])} ({prec['hits']}/{prec['n']}), "
        f"{'đạt' if (prec['rate'] or 0) >= PRECISION_GATE else 'dưới'} mốc 0,6; bỏ sót {vc['fn']} "
        f"trên {vc['n_pos']} sản phẩm lệch.",
    ]


def _c2_bullets(c2: dict | None) -> list[str]:
    if c2 is None or "vietcraft" not in c2:
        return ["- **C2 (ảnh bản 2) chưa có số đo**: chưa có metrics.json của model."]
    vc = c2["vietcraft"]
    if "delta_v2_flag" not in vc:
        return [f"- **C2 không đánh giá được trên VietCraft**: {vc.get('status', 'thiếu dữ liệu')}."]
    d, lo = vc["delta_v2_flag"], vc["delta_v2_flag"]["ci95"][0]
    edge = " sát nút" if 0 < lo < 0.01 else ""
    out = [
        f"- **C2 {'qua' if lo > 0 else 'không qua'} cổng{edge}, chế độ {c2['mode']}**: AUC {num(vc['v2']['auc'])} "
        f"so với cờ cũ {num(vc['flag']['auc'])}, chênh {gap(d['diff'], d['ci95'])}; cận dưới chỉ {num(lo)}. "
        f"Chỉ {vc['n_bad']} ảnh xấu, khoảng tin cậy rộng.",
        f"- **C2 kém bản 1 trên KonIQ thật**: SRCC {num(c2['konig']['srcc'])} so với {num(c2['konig_v1_srcc'])}. "
        f"Trên VietCraft, v2 − v1 là {gap(vc['delta_v2_v1']['diff'], vc['delta_v2_v1']['ci95'])}, khoảng tin cậy "
        "chứa 0, nên không khác biệt có ý nghĩa. Bản 1 dùng trọng số KonIQ, chỉ cho demo học thuật, nên bản 2 được chọn.",
        f"- **Ngưỡng {c2['threshold']} trên Tiki test báo nhầm {pct(c2['test_threshold']['fpr'])} ảnh gốc** "
        "không hỏng, và bắt được "
        f"{pct(c2['test_threshold']['recall'])} ảnh hỏng nhân tạo.",
    ]
    wm = vc["by_reason"].get("watermark", {})
    if "v2" in wm:
        out.append(f"- **Mức tăng trên VietCraft chủ yếu từ ảnh có watermark**: AUC {num(wm['v2']['auc'])} "
                   f"trên {wm['n_bad']} ảnh. Ảnh không phải sản phẩm và chữ đè không tốt "
                   f"({num(vc['by_reason']['not_product']['v2']['auc'])} và "
                   f"{num(vc['by_reason']['text_overlay']['v2']['auc'])}).")
    return out


def neg_body(b1: dict, b3: dict, i: dict, t: dict, c: dict | None = None, a: dict | None = None,
             c2: dict | None = None) -> str:
    v, fa = t["b2"], b3["false_alarm"]["block"]
    low = b3["prevalence"]["0.01"]["delta_ci95"][0]
    flag, flag2 = t["b3"]["description_type:image_text_mismatch"], t["b3"]["description_type:image_text_or_category"]
    probe, o, rej = b1["compare"]["probe"], t["b1"]["out_of_trained"], b1["reject"]["test"]
    lines = [
        f"- **B2 thua luật trên VietCraft**: top-1 {num(v['model']['top1']['rate'])} so với "
        f"{num(v['baseline_text_vi']['top1']['rate'])} (luật đã sửa). Luật là nguồn chính; B2 chỉ gợi ý khi thiếu.",
        f"- **B3 ở chế độ {b3['mode']}**: tỉ lệ lỗi 1% không đạt (cận dưới CI {num(low)}). "
        f"Báo nhầm ở mức chặn {pct(fa['rate'], 2)} vượt α {pct(fa['alpha'])}.",
        f"- **B1 chỉ từ chối {pct(o['reject_rate']['rate'])} hàng thuộc loại chưa train** "
        f"({o['reject_rate']['hits']} trên {o['reject_rate']['n']}; ví dụ tranh, laptop, điện thoại). "
        "Phần còn lại bị gán một loại thời trang.",
        f"- **Từ chối chưa đạt mục tiêu**: trên test, đúng {pct(rej['acc_answered'])} khi trả lời, "
        "dưới mục tiêu 95% đặt trên val.",
        "- **Zero-shot không cải thiện hàng đã train**: trộn zero-shot không khác model học thuần "
        f"(top-1 chênh {gap(probe['delta_top1'], probe['delta_ci95'])}, Holm p {pval(probe['holm_p'])}).",
        "- **B1 từng rò rỉ chữ** (cùng tên sản phẩm nằm ở cả tập train lẫn test): số cũ 0,897 không dùng. "
        f"Sau khi đổi cách chia và train lại, macro-F1 là {num(b1['test']['fused']['macro_f1'])}.",
        "- **Nhãn VietCraft do AI gắn**, người dùng chưa kiểm: mọi số chuyển sàn chỉ là chỉ dấu.",
        "- **Con số 0,486 cũ đo nhầm nhãn**: nhãn là 'bán chạy top 25%', không phải 'chất lượng ảnh'. "
        "Số đó không nói gì về ảnh.",
        f"- **Ảnh trùng**: cận trên báo nhầm {pct(i['fpr_warn_wilson95_B'][1], 2)} vượt 1%, "
        "nên chưa chứng minh được. Theo thẻ model, pHash không còn tin cậy khi cắt quá 10% mỗi cạnh.",
        f"- **Cờ mô tả loại hàng trên VietCraft kém**: {flag['tp']} đúng / {flag['fp']} báo nhầm / "
        f"{flag['fn']} bỏ sót (lỗi thật {flag['n_pos']}). Tính cả lệch danh mục: "
        f"{flag2['tp']} / {flag2['fp']} / {flag2['fn']}. Vì vậy B3 để shadow.",
        *_c1_bullets(c, t),
        *_attr_bullets(a, t),
        *_c2_bullets(c2),
        "- **Cổng chưa đo xong**: B2 đã đo với luật đã sửa và đạt trên bài A, nhưng thua trên VietCraft. "
        "I: mới kiểm 1 cặp dùng chung ảnh, PROTOCOL cần 2/2; 21/21 ảnh link sàn chưa đo lại.",
        "- **Chưa đo** (PROTOCOL mục 3): ECE của B2 và B3, bản gõ sai 5% của B2, B3 theo loại lệch ①–④, "
        "ablation C1 'bỏ thủ công' và 'bỏ vector', thời gian mỗi ảnh của I.",
    ]
    return "\n".join(lines)
