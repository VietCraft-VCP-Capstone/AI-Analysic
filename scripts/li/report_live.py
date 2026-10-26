from scripts.li.report_parts import AXIS_LABELS, pct


def _n(v):
    return "—" if v is None else f"{v:.1f}"


def floor_share(ic):
    ic = ic or {}
    return {k: pct((ic.get(k) or {}).get("chosen")) for k in ("val", "test")}


def served_lines(r):
    f = floor_share(r.get("impute_check"))
    return [
        "- Điểm tổng phục vụ người bán không đúng là hàm có AUC ở mục 1 và 5. Runtime (`fusion.served`, "
        "`fusion.base_score`) làm thêm 4 bước:\n"
        "  - (a) che (đặt NaN) các feature có `feature_availability` < 0,01 trong nhóm;\n"
        "  - (b) đặt các feature trong `feature_constants` về hằng số lúc học;\n"
        "  - (c) khi listing không có ảnh, điền feature ảnh bằng `image_impute`;\n"
        "  - (d) lấy sàn: điểm = max(model(listing), model(listing bỏ ảnh)). Sau đó điểm mới nhân `h(d)`.",
        "- Mọi AUC trong báo cáo, kể cả AUC trên thẻ model ở giao diện, là của model gộp thô trên dòng Tiki, với "
        "feature như trong bảng, chưa qua các bước (a) đến (d).",
        f"- Trên dòng tiki26 có ảnh, sàn (d) đổi điểm ở {f['val']} dòng validation và {f['test']} dòng test. Số này "
        "lấy từ phép tính `impute_check` đã có (mục 9), không phải một lần đọc test mới.",
        "- Các bước (a) đến (c) nhắm vào feature mà dòng Tiki lúc học không có, hoặc chỉ có một giá trị. Ảnh hưởng của "
        "chúng lên AUC trên dòng Tiki chưa được đo riêng.",
        "- Ghi điểm và embedding lên DB production đang **tắt theo quyết định của người dùng** (B1): runtime chỉ ghi vào "
        "Mongo local. Vì vậy trên production, trang danh sách tính lại mỗi lần xem và không lưu điểm.",
    ]


def impute(ic, rule):
    if not ic:
        return ""
    rows = [f"| {k} | {v['n']} | {pct(v['q10'])} | {pct(v['chosen'])} |" for k, v in ic.items()]
    return "\n\n".join([
        f"### Điền feature cho listing không ảnh\n\nQuy tắc đang dùng (`meta.image_impute`): {rule}. So với cách điền "
        "q10 từng feature, tỉ lệ dòng tiki26 có ảnh mà bản bỏ ảnh rồi điền lại lại được model gộp chấm cao hơn bản có ảnh:",
        "\n".join(["| Tập | Số dòng | Điền q10 từng feature | Điền bằng ảnh train làm điểm thấp nhất (đang dùng) |",
                   "|---|---|---|---|", *rows]),
        "Cách điền được chọn theo số validation; vector điền chỉ chọn trên train. Dòng test chỉ để mô tả."])


def _add_images(a):
    if not a or not a.get("n"):
        return ""
    return (f"- Lời khuyên \"thêm ảnh\" ở {a['n']} listing chưa có ảnh: {a['positive']} có impact > 0, trung vị "
            f"+{a['median']} điểm (từ {a['min']} đến {a['max']}). Đây là ước tính khi thay feature ảnh bằng trung vị "
            "listing top25 cùng nhóm, không phải cam kết.\n")


def vietcraft(vc):
    if not vc:
        return "_Chưa chạy `scripts/li/vietcraft_check.py`._"
    s, by = vc["score"], vc["score_median_by_image"]
    cover = ", ".join(f"{AXIS_LABELS[a]} {pct(v)}" for a, v in vc["axis_coverage"].items())
    shift = [f"- Nhóm `{g}` ({d['n']} sản phẩm, {d['n_image']} có ảnh): {d['psi_over_0_25']}/{d['psi_features']} "
             "feature có PSI > 0,25. Lệch lớn nhất (PSI; trung vị Tiki train → VietCraft): " + "; ".join(
                 f"`{c}` {v['psi']} ({v['tiki_median']} → {v['vietcraft_median']})" for c, v in d["top"].items()) + "."
             for g, d in vc["shift"].items()]
    head = ["| Sản phẩm | Nhóm | Điểm tổng | " + " | ".join(AXIS_LABELS[a] for a in vc["axis_coverage"]) + " |",
            "|---" * (3 + len(vc["axis_coverage"])) + "|"]
    body = [f"| {e['title'].strip()} | {e['group']} | {_n(e['score'])} | "
            + " | ".join(_n(e[f"ax_{a}"]) for a in vc["axis_coverage"]) + " |" for e in vc["examples"]]
    return "\n\n".join([
        f"Đo ngày {vc['date']} trên Mongo local `{vc['database']}`: {vc['n']} sản phẩm của {vc['n_shops']} shop, "
        f"{vc['n_image']} có ảnh tải được. Nhóm: " + ", ".join(f"{g} {n}" for g, n in vc["groups"].items()) + ". Chạy "
        "`intel.analyze` không ghi gì (`persist=False`, `store_embeddings=False`).",
        f"- Độ phủ trục (có điểm): {cover}.\n- Điểm tổng: nhỏ nhất {s['min']}, tứ phân vị {s['25%']} / {s['50%']} / "
        f"{s['75%']}, lớn nhất {s['max']}. Trung vị có ảnh {by['có ảnh']}, không ảnh {by['không ảnh']}.\n"
        + _add_images(vc.get("no_image_advice")) +
        "- PSI: 10 bin theo phân vị Tiki train cùng nhóm, chỉ trên giá trị không thiếu, chỉ cho nhóm có ≥ 5 sản phẩm.",
        *shift, "5 sản phẩm có ảnh điểm tổng cao nhất:", "\n".join(head + body)])
