from scripts.f29.eval_kit import md_table
from scripts.f29.results_base import num


SOURCE = {"tiki": "học từ dữ liệu bán Tiki", "synthetic": "học từ bộ mô phỏng của bản đăng ký"}
LABEL = {"image": "Ảnh", "description": "Mô tả", "tags": "Tag", "review": "Đánh giá", "price": "Giá"}
R3_FRAME = "| Cách chấm | r | CI 95% |\n|---|---|---|"


def _ci(c) -> str:
    return f"[{num(c[0])}; {num(c[1])}]"


def _weights(w: dict, source: dict) -> str:
    rows = [{"Yếu tố": LABEL[k], "Trọng số": num(w[k], 1), "Nguồn": SOURCE[source[k]]} for k in LABEL]
    return md_table(rows, ["Yếu tố", "Trọng số", "Nguồn"])


def _sim(block: dict) -> str:
    rows = [{"Cách chấm": k, "r": num(v.get("r", v.get("diff"))), "CI 95%": _ci(v["ci95"])} for k, v in block.items()]
    return md_table(rows, ["Cách chấm", "r", "CI 95%"])


def _tiki(block: dict) -> str:
    rows = [{"Cách chấm": k, "AUC": num(v.get("roc_auc", v.get("diff"))), "CI 95%": _ci(v.get("auc_ci95", v.get("ci95"))),
             "AUC trong nhóm": num(v.get("within_cat_auc"))} for k, v in block.items()]
    return md_table(rows, ["Cách chấm", "AUC", "CI 95%", "AUC trong nhóm"])


def _e2e(e: dict | None) -> str:
    if not e:
        return "- Quy trình chạy thật trên VietCraft: chưa chạy (`python -m scripts.f29.register.e2e`)."
    c, h = e["r_cvr"], e["r_cart"]
    return (f"- Quy trình chạy thật trên VietCraft ({e['n']} tin có ≥ 30 lượt xem, {e['note']}): "
            f"r với đơn/xem: chính thức {num(c['chính thức'])}, đặt tay {num(c['đặt tay'])}; "
            f"r với bỏ giỏ/xem: chính thức {num(h['chính thức'])}, đặt tay {num(h['đặt tay'])}. "
            f"Độ tin cậy: {', '.join(f'{k} {v}' for k, v in e['confidence'].items())}.")


def r3_body(m: dict, e2e: dict | None, source: dict) -> str:
    g = m["gates"]
    lines = [
        f"- Cổng R3 (r ≥ 0,65 trên 500 tin mô phỏng): {'đạt' if g['R3 r ≥ 0,65'] else 'không đạt'}. "
        "Trọng số đặt tay cũng đạt mức này, nên R3 chỉ là cổng tuân thủ, không phải bằng chứng AI.",
        f"- Cổng AI hơn luật (Tiki test, cận dưới CI > 0): "
        f"{'đạt' if g['AI hơn đặt tay trên Tiki (cận dưới > 0)'] else 'không đạt'}.",
        "- Giới hạn: mô tả trong dữ liệu Tiki bị cắt ở khoảng 200 ký tự, nên trọng số Mô tả học trên Tiki "
        "đo số từ của đoạn đầu mô tả, không phải độ dài thật như lúc chạy.",
        "- Giá mạnh nhất trên dữ liệu bán thật Tiki nhưng gần như vô dụng trong bộ mô phỏng, "
        "nên trọng số học từ dữ liệu thật làm r mô phỏng thấp hơn trọng số học trên mô phỏng.",
        _e2e(e2e),
    ]
    return "\n\n".join([
        "Trọng số chính thức (`health_weights.json`, quy tắc ghép ở PROTOCOL mục 8):", _weights(m["weights"]["chính thức"], source),
        "Mô phỏng, tập test 500 tin (Pearson r với tỉ lệ chuyển đổi):", _sim(m["test"]["mô phỏng"]),
        "Tiki, tập test (AUC với nhãn bán chạy top 25%):", _tiki(m["test"]["tiki"]),
        "\n".join(lines),
    ])


AI_COLS = ["Check", "Yếu tố (điểm)", "Ai quyết", "Chế độ", "Tác động khi live"]
DESC_EFFECT = "Vào danh sách việc cần làm, không đổi điểm"


def _rows(modes: dict, w: dict) -> list[dict]:
    d, i = f"Mô tả ({w.get('Mô tả', '–')})", f"Ảnh ({w.get('Ảnh', '–')})"
    rows = [
        ("description_category:top3", d, "B1: model ảnh + chữ", "live", DESC_EFFECT),
        ("description_material:conflict", d, "Luật từ điển chất liệu", "live", DESC_EFFECT),
        ("description_material:missing", d, "B2 model gợi ý chất liệu", "live", "Chỉ gợi ý, không trừ"),
        ("description_type:*", d, "B3 bản 1: model ảnh + chữ + loại", modes["b3_mismatch"], DESC_EFFECT),
        ("description_attribute:*", d, "B3 bản 2: model thuộc tính ảnh", modes["b3_attr"], DESC_EFFECT),
        ("image_quality:*", i, "C1: model chất lượng ảnh", modes["c1"],
         "Ảnh bị cờ không tính là ảnh đạt"),
        ("cờ độ nét, sáng (quality_issues)", i, "Luật ngưỡng cố định", "live",
         "Ảnh có cờ không tính là đạt"),
        ("ảnh nhỏ hơn 500 px (low_resolution)", i, "Luật ngưỡng cố định", "live",
         "Ảnh có cờ không tính là đạt"),
        ("duplicate_same_shop:*", i, "Luật pHash + ngưỡng SigLIP (hiệu chỉnh)", "live",
         "Ảnh trùng cùng shop không tính là đạt"),
        ("duplicate_external:*", "Ảnh trùng", "Luật (host ảnh)", "live", "Chỉ cảnh báo, không đổi điểm"),
        ("giá, tag, đánh giá", f"Giá {w.get('Giá', '–')}, Tag {w.get('Tag', '–')}, Đánh giá {w.get('Đánh giá', '–')}",
         "Đo bằng luật và thống kê, trọng số do AI học", "live", "Thứ hạng % so với tin cùng loại"),
    ]
    return [dict(zip(AI_COLS, r)) for r in rows]


def ai_body(modes: dict, weights: dict) -> str:
    parts = ", ".join(f"{k} {v}" for k, v in weights.items())
    lines = [
        f"- Điểm = tổng có trọng số của 5 yếu tố; mỗi yếu tố là thứ hạng % so với tin cùng loại. Trọng số do AI học: {parts} (mục R3).",
        "- AI đo trực tiếp yếu tố Ảnh: ảnh trùng cùng shop (pHash + SigLIP) không tính là ảnh đạt.",
        "- Check mô tả và kiểm file in không đổi điểm: mức live vào đầu danh sách việc cần làm, mức hint chỉ hiện gợi ý.",
        "- Check shadow chỉ ghi lại để đo, không đổi điểm và không hiện cho người bán.",
    ]
    return "\n\n".join([md_table(_rows(modes, weights), AI_COLS), "\n".join(lines)])

