def vn(x, nd: int = 3) -> str:
    return f"{x:.{nd}f}".replace(".", ",")


def pe(p: float) -> str:
    return f"{p:.2e}".replace(".", ",")


def ci(v: list) -> str:
    return f"[{vn(v[0])}; {vn(v[1])}]"


def table(t: dict, cp: dict) -> list[str]:
    rows = ["| Nguồn | Macro-F1 [CI 95%] | Top-1 [CI 95%] | Fused trừ nguồn, top-1 [CI 95%] | McNemar p | Holm p |",
            "|---|---|---|---|---|---|"]
    for k, v in t.items():
        c = cp.get(k)
        diff, p, holm = (f"{vn(c['delta_top1'])} {ci(c['delta_ci95'])}", pe(c["mcnemar_p"]), pe(c["holm_p"])) if c else ("-", "-", "-")
        rows.append(f"| {k} | {vn(v['macro_f1'])} {ci(v['macro_f1_ci95'])} | {vn(v['top1'])} {ci(v['top1_ci95'])} "
                    f"| {diff} | {p} | {holm} |")
    return rows


def card(m: dict) -> str:
    t, cp, rj = m["test"], m["compare"], m["reject"]["test"]
    n_types = len(m["trained_types"]) + len(m["untrained_types"])
    lines = [
        "# B1 · Loại hàng từ ảnh và chữ (v1)",
        "",
        f"- Việc làm: đoán loại hàng ({n_types} loại) từ vector ảnh và chữ SigLIP2 đã đóng băng.",
        f"- Dữ liệu: emb_tikifashion.npz, {sum(m['rows'].values())} mẫu (bỏ nhãn trung_nien_nu). "
        f"Chỉ thời trang có dữ liệu train ({len(m['trained_types'])} loại). Còn {len(m['untrained_types'])} loại chạy zero-shot.",
        f"- Chia: cụm nối khi cos ảnh > 0,95 hoặc cos chữ > 0,999 ({m['clusters']} cụm). "
        f"group_split 70/15/15, seed {m['seed']}. Train/val/test: {m['rows']['train']}/{m['rows']['val']}/{m['rows']['test']}.",
        f"- Mẫu test theo loại: {', '.join(f'{k} {v}' for k, v in m['test_count'].items())}. Loại dưới 10 mẫu làm macro-F1 nhiễu.",
        f"- Mô hình: LogisticRegression ảnh C={m['C']['img']}, chữ C={m['C']['txt']}; gộp log p_ảnh + {vn(m['w'], 2)}·log p_chữ; "
        f"trộn zero-shot {vn(m['zs_mix'], 1)} (nhiệt độ {m['temp']}).",
        f"- Từ chối: τ = {vn(m['tau'], 3)}, chọn trên val để độ đúng phần trả lời ≥ 0,95 "
        f"(val {vn(m['reject']['val']['acc_answered'])}). Trên test: từ chối {vn(100 * rj['rate'], 1)}%, "
        f"độ đúng phần trả lời {vn(rj['acc_answered'])}, macro-F1 phần trả lời {vn(rj['macro_f1_answered'])}.",
        "",
        *table(t, cp),
        "",
        f"- Trộn zero-shot không khác probe thuần có ý nghĩa thống kê (fused trừ probe, top-1 = {vn(cp['probe']['delta_top1'])}, "
        f"Holm p = {pe(cp['probe']['holm_p'])}). Đổi lại, loại chưa có dữ liệu có xác suất.",
        "- Giới hạn: dữ liệu là ảnh Tiki Fashion. Chưa đo trên tiki26 và VietCraft.",
        "- Giới hạn: ảnh ngoài thời trang chưa đo. Probe không có lớp ngoài thời trang, nên có thể gán nhãn thời trang với p ≥ τ.",
        f"- Giới hạn: loại zero-shot có p tối đa {vn(m['zs_mix'], 1)}, nên thường bị từ chối khi τ = {vn(m['tau'], 2)}.",
        "- Giới hạn: 12 loại zero-shot không có nhãn test, nên không đo được độ đúng.",
    ]
    return "\n".join(lines) + "\n"
