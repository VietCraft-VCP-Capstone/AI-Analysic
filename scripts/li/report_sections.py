from scripts.li.report_parts import pct, shift_table


BATCH_INVARIANT = 0.9999


def _ok(v):
    return "—" if v is None else ("đạt" if v else "**không đạt**")


def sanity_line(r):
    checks = {k: v["pass"] for k, v in r["sanity"].items()} | {"image": (r["image_sanity"] or {}).get("pass")}
    names = {"shuffled_labels": "xáo trộn nhãn", "seller_overlap": "trùng seller", "banned_features": "cột cấm",
             "deterministic": "tất định", "image": "bất biến ảnh"}
    bad = [names.get(k, k) for k, v in checks.items() if v is False]
    p90 = (r["image_sanity"] or {}).get("p90_shift_pct")
    tail = f" (bất biến ảnh xét theo trung vị; p90 lệch lớn nhất {max(p90.values())} điểm phân vị)" if p90 else ""
    return ("đạt tất cả" if not bad else "không đạt: " + ", ".join(bad)) + tail


def caveats(r):
    d, cov = r["data"], r.get("coverage", {})
    g23, g26 = set(d.get("tiki23", {}).get("groups", [])), set(d.get("tiki26", {}).get("groups", []))
    lines = ["\nLưu ý về dữ liệu (đo trên bảng feature):",
             f"- Nhóm danh mục: tiki23 {sorted(g23)}, tiki26 {sorted(g26)}"
             + (" — hai nguồn không có nhóm chung, nên cột `group` cũng nhận diện nguồn; vì vậy báo cáo kèm AUC "
                "trong nhóm." if not g23 & g26 else ".")]
    for src, c in cov.items():
        lines.append(f"- {src}: `n_images` thiếu {pct(c['n_images_nan'])}, mô tả rỗng {pct(c['desc_empty'])}, "
                     f"có vector ảnh {pct(c['has_image'])}.")
    return "\n".join(lines)


def shift(sh):
    if not sh:
        return "_Không chạy được (thiếu dữ liệu)._"
    shared = set(sh["groups_fit"]) & set(sh["groups_test"])
    dropped = sorted({c for v in sh.values() if isinstance(v, dict) for c in v.get("dropped", [])})
    return "\n\n".join([shift_table(sh), f"Nhóm học: {', '.join(sh['groups_fit'])}; nhóm test: "
                        f"{', '.join(sh['groups_test'])}. Feature: chỉ chữ và meta (`TEXT_COLS + META_COLS`); cột toàn NaN "
                        f"ở tập học bị bỏ: {', '.join(f'`{c}`' for c in dropped) or 'không có'}."
                        + ("" if shared else " Hai nguồn không chung nhóm nên đây là lệch cả thời gian lẫn danh mục.")])


def _image_rows(im):
    if not im:
        return ["| Bất biến ảnh | không chạy (thiếu model ONNX) | — |"]
    shifts = "; ".join(f"{k}: {v}" for k, v in im["median_shift_pct"].items())
    p90 = "; ".join(f"{k}: {v}" for k, v in im["p90_shift_pct"].items())
    dup = "; ".join(f"{k}: {v}" for k, v in im["dhash_median_hamming"].items())
    served = im.get("served_mode", "model")
    alt = [f"| Bất biến ảnh, cách chấm không phục vụ ({m}, tham khảo) | trung vị lệch "
           + "; ".join(f"{k}: {v}" for k, v in b["median_shift_pct"].items()) + "; p90 "
           + "; ".join(f"{k}: {v}" for k, v in b["p90_shift_pct"].items()) + " | — |"
           for m, b in (im.get("by_mode") or {}).items() if m != served]
    return [f"| Bất biến ảnh, trục đang phục vụ ({served}; {im['n']} ảnh test, ảnh đi qua `image_load.as_trained` "
            f"như lúc phục vụ, ngưỡng ≤ {im['max_shift']} điểm phân vị) | trung vị lệch {shifts}; p90 {p90}; ảnh gốc "
            f"qua `as_trained` so với bảng feature lệch trung vị {im['parity_median_abs_pct']} | {_ok(im['pass'])} |", *alt,
            f"| Phát hiện ảnh trùng (dHash) | Hamming trung vị bản biến đổi: {dup}; giữa 2 ảnh khác nhau: "
            f"{im['dhash_median_hamming_other']} | — |"]


def image_diag(dg, served="model"):
    if not dg:
        return ""
    who = "model trục ảnh học" + ("" if served == "model" else " (không phục vụ; trục ảnh đang dùng công thức)")
    rows = [f"- {k}: cos vector ảnh gốc–biến đổi {v['cos_embedding']}; lệch trung vị khi chỉ đổi số đo kỹ thuật "
            f"{v['shift_only_quality']}, chỉ đổi vector {v['shift_only_embedding']}, đổi cả hai {v['shift_both']} điểm"
            for k, v in dg["variants"].items()]
    cs = dg["cos_single_vs_batch"]
    batch = "không phụ thuộc lô" if cs["min"] >= BATCH_INVARIANT else "phụ thuộc các ảnh khác trong cùng lô"
    return "\n".join([
        f"\nChẩn đoán bất biến ảnh với {who}, {dg['n']} ảnh, không qua `as_trained`:",
        f"- Cùng một ảnh, gọi riêng so với gọi chung một lần {dg['n']} ảnh: cos trung vị {cs['median']}, thấp nhất "
        f"{cs['min']}, tức vector {batch}; so với vector trong bảng feature: cos trung vị {dg['cos_single_vs_table']}.",
        *rows])


def sanity(r):
    s = r["sanity"]
    sh, so, bf, de = s["shuffled_labels"], s["seller_overlap"], s["banned_features"], s["deterministic"]
    within = "; ".join(f"{src}: " + ", ".join(f"{k}={v}" for k, v in d.items()) for src, d in so["within_source"].items())
    rows = ["| Kiểm tra | Kết quả | Đạt |", "|---|---|---|",
            f"| Xáo trộn nhãn train ({len(sh['seeds'])} seed) | AUC trung bình test tiki26 {sh['auc_mean']['test']}, "
            f"test gộp {sh['auc_mean']['test_all']}; từng lần tiki26 {sh['auc_runs']['test']}, gộp "
            f"{sh['auc_runs']['test_all']}; AUC trong nhóm trung bình tiki26 {sh['within_group_auc_mean']['test']}, gộp "
            f"{sh['within_group_auc_mean']['test_all']}; khoảng {sh['range']} "
            f"| {_ok(sh['pass'])} |",
            f"| Không seller nào ở 2 tập | {within}; dòng val/test có tên seller trùng với train nguồn kia: "
            f"{so['cross_rows_eval']} | {_ok(so['pass'])} |",
            f"| Không cột cấm trong feature | kiểm {bf['checked']} cột, lọt: {bf['found'] or 'không'}; cột của model khớp "
            f"meta: {bf['model_matches_meta']} | {_ok(bf['pass'])} |",
            f"| Tất định | học lại 2 lần giống hệt: {de['refit_identical']}; giống bundle: {de['bundle_identical']} "
            f"| {_ok(de['pass'])} |", *_image_rows(r["image_sanity"])]
    rt = r.get("retrieval")
    text = (f"Retrieval ảnh–caption trên {rt['n']} cặp `tikifashion`: top-1 ảnh→chữ {pct(rt['top1_img_to_txt'])}, "
            f"chữ→ảnh {pct(rt['top1_txt_to_img'])}, recall@5 {pct(rt['recall5_img_to_txt'])}, ngẫu nhiên "
            f"{pct(rt['chance_top1'])} (gấp {rt['ratio_vs_chance']} lần); cos cặp đúng {rt['mean_cos_pair']}, cặp sai "
            f"{rt['mean_cos_other']}.") if rt else "Retrieval: không chạy (thiếu `emb_tikifashion.npz`)."
    served = (r.get("image_sanity") or {}).get("served_mode", "model")
    return "\n".join(rows) + "\n" + image_diag(r.get("image_diag"), served) + "\n\n" + text
