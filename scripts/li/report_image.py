from scripts.li.report_parts import ci, f3


def _params(p):
    return ", ".join(f"{k}={v}" for k, v in p.items())


def _row(label, r):
    shifts = "; ".join(f"{k} {v}" for k, v in r["shifts"].items())
    return (f"| {label} | {r['cols']} | {_params(r['params'])} | {f3(r['auc'])} {ci(r['ci95'])} | {shifts} | "
            f"{r.get('p90_shift', '—')} | {r.get('n_distinct', '—')} |")


def section(rb):
    if not rb:
        return "_Chưa chạy `scripts/li/image_robust.py`._"
    head = ["| Cấu hình | Bộ cột | Tham số HGB | AUC validation [CI95] | Lệch trung vị (điểm phân vị) | p90 lệch lớn nhất | "
            "Số giá trị dự đoán khác nhau |", "|---|---|---|---|---|---|---|"]
    rows = [_row("li-1.1", rb["rows"][0])]
    for name in rb["colsets"]:
        part = [r for r in rb["rows"][1:] if r["cols"] == name]
        ok = [r for r in part if r["ci95"][0] > 0.5]
        if ok:
            rows.append(_row(f"ổn định nhất của `{name}` ({len(ok)}/{len(part)} cấu hình có CI > 0,5)",
                             min(ok, key=lambda r: (r["max_shift"], -r["auc"]))))
        else:
            rows.append(f"| `{name}` | {name} | — | 0/{len(part)} cấu hình có CI > 0,5 | — | — | — |")
    rows.append(_row("**được chọn**", rb["chosen"]))
    sets = "; ".join(f"`{k}`: {len(v)} cột" for k, v in rb["colsets"].items())
    grid = ", ".join(f"{k} ∈ {list(v)}" for k, v in rb["grid"].items())
    return "\n\n".join([
        f"Tập biến đổi dựng từ {rb['n_val']} ảnh validation tiki26 (không dùng test): sáng ±10%, JPEG q70; điểm phân vị "
        f"so với phân phối dự đoán validation cùng nhóm, đúng như khi phục vụ. Lưới: {grid}; learning_rate 0,05, không "
        f"dừng sớm. Bộ cột: {sets}. Quy tắc chọn: {rb['rule']}.", "\n".join(head + rows),
        f"Mục tiêu ≤ 5 điểm trên validation: {'đạt' if rb['meets_target'] else '**không đạt**'}. Lệch trung vị chỉ cho biết "
        "hơn nửa số ảnh giữ nguyên điểm; cột p90 cho thấy phần đuôi vẫn lệch lớn. Toàn bộ lưới nằm trong "
        "`data-li/features/image_robust.json` và `docs/listing_intel_results.json`. AUC ở bảng này tính trên feature "
        f"tính lại từ ảnh (lệch tối đa {rb['parity_max_abs']:.1e} so với bảng feature), nên có thể khác mục 5 (tính "
        "trên bảng feature) ở chữ số thứ ba. Lưới này và công thức ở phần sau được thiết kế trên feature tính thẳng từ "
        "ảnh thu nhỏ, chưa qua bước `as_trained` của runtime; số đo lại qua đường runtime ở cuối mục."])


def runtime_section(rt):
    if not rt:
        return "_Chưa chạy `scripts/li/image_runtime.py`._"
    head = ["| Cách chấm | Lệch trung vị | p90 lệch | AUC validation [CI95] |", "|---|---|---|---|"]
    rows = [("Công thức ảnh đang phục vụ", rt["formula"]["median_shift"], rt["formula"]["p90_shift"], rt["formula"]),
            ("Model ảnh học (không phục vụ)", rt["model"]["shifts"], {"lớn nhất": rt["model"]["p90_shift"]}, rt["model"])]
    body = [f"| {n} | " + "; ".join(f"{k} {v}" for k, v in med.items()) + " | "
            + "; ".join(f"{k} {v}" for k, v in p90.items()) + f" | {f3(r['auc'])} {ci(r['ci95'])} |"
            for n, med, p90, r in rows]
    par = rt["parity_formula_pct"]
    return "\n\n".join([
        f"Đo lại trên {rt['n_val']} ảnh validation theo đúng đường phục vụ: {rt['path']}. Chỉ báo cáo, không đổi "
        "thiết kế.", "\n".join(head + body),
        f"Ảnh gốc qua `as_trained` so với bảng feature: điểm công thức lệch trung vị {par['median']}, p90 {par['p90']} "
        f"điểm phân vị; feature lệch tối đa {rt['parity_feature_max_abs']}."])


def formula_section(fc):
    if not fc:
        return "_Chưa chạy `scripts/li/image_formula_check.py`._"
    head = ["| Ứng viên | Trọng số | Lệch trung vị | p90 lệch | AUC validation [CI95] |", "|---|---|---|---|---|"]
    weights = {"li-1.3": "công thức li-1.3"} | {n: ", ".join(f"{k} {v}" for k, v in w.items()) for n, w in fc["candidates"].items()}
    body = [f"| {'**' + n + '**' if n == fc['chosen'] else n} | {weights[n]} | "
            + "; ".join(f"{k} {v}" for k, v in r["median_shift"].items()) + " | "
            + "; ".join(f"{k} {v}" for k, v in r["p90_shift"].items()) + f" | {f3(r['auc'])} {ci(r['ci95'])} |"
            for n, r in fc["rows"].items()]
    return "\n\n".join([
        f"Thiết kế chỉ trên {fc['n_val']} ảnh validation tiki26 đã biến đổi (không dùng test). Quy tắc chọn: {fc['rule']}. "
        "Độ nét dùng `sharpness_rel` = log phương sai Laplacian − 2·log độ lệch chuẩn mức xám, nên không đổi khi cả ảnh "
        "tối đi; cờ `exposure_ok` theo đúng luật `too_dark`/`too_bright` của `vision.quality_issues`; cờ `contrast_ok` "
        "khi độ tương phản ≥ ngưỡng.", "\n".join(head + body),
        f"Được chọn: `{fc['chosen']}` (trọng số đang phục vụ khớp: {fc['served_weights_match']}). AUC validation của "
        "công thức chỉ để tham khảo: công thức là thực hành tốt (`practice`), không phải mô hình dự báo bán chạy."])
