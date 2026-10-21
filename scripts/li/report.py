import re
from pathlib import Path

from scripts.li import report_history as RH
from scripts.li import report_image as RI
from scripts.li import report_live as L
from scripts.li import report_model as RM
from scripts.li import report_sections as S
from scripts.li import report_trend as T
from scripts.li.report_parts import ci, data_table, f3, metrics_table, missing_table

MANUAL = {
    "reads": "_Chưa điền: danh sách các lần đọc test._",
    "calib": "_Chưa điền: kết quả chấm tay mẫu khớp vector trong `trend_calib_sample.csv`._",
    "changes": "_Chưa điền: thay đổi so với phiên bản trước._",
    "vietcraft": "_Chưa điền. Task 12 chạy scorer trên Mongo local `vietcraft-test` và điền: độ phủ từng trục, "
                 "phân phối điểm, PSI giữa feature Tiki và VietCraft, 5 ví dụ có ảnh._",
    "weakness": "_Chưa điền. Task 12 viết: mỗi điểm yếu → trục hoặc endpoint bị ảnh hưởng → cách sửa → trạng thái "
                "(đã sửa và đo lại, hoặc giới hạn chấp nhận). Điểm xuất phát là các lưu ý ở mục 3 và 9._",
}


def _block(name, body):
    return f"<!-- manual:{name} -->\n{body}\n<!-- /manual:{name} -->"


def kept(text, name):
    m = re.search(rf"<!-- manual:{name} -->\n(.*?)\n<!-- /manual:{name} -->", text or "", re.S)
    return m.group(1) if m else MANUAL[name]


def summary(r):
    m, t = r["model"], r["model"]["metrics"]["test"]
    sel = r.get("selection") or {}
    lines = [
        f"- Test tiki26 (tập chính): model gộp ROC-AUC {f3(t['roc_auc'])}, CI95 {ci(t['auc_ci95'])}, AUC trong nhóm "
        f"{f3(t['within_cat_auc'])}, {t['n']} dòng, {t['n_sellers']} cụm seller. Đây là AUC của model gộp thô trên dòng "
        "Tiki (cũng là số trên thẻ model ở giao diện). Điểm phục vụ còn thêm bước che và điền feature và sàn không ảnh "
        "(mục 3); trên dòng tiki26, sàn đổi điểm ở {val} dòng validation và {test} dòng test.".format(
            **L.floor_share(r.get("impute_check"))),
        *(f"- {line}" for line in RM.gate_lines(m)),
        f"- Nhãn chứng cứ cho lời khuyên: {RM.evidence_line(m)}.",
        "- Cách chấm trục (quyết định trên validation): " + ", ".join(
            f"{a} {e['mode']}" for a, e in (m.get("axis_modes") or {}).items()) + ".",
        "- Chọn feature trên validation: " + (f"giữ {', '.join(f'`{k}`' for k in sel['kept'])}." if sel.get("kept")
                                              else "không giữ ứng viên nào."),
        f"- Trend: {T.criterion4_line(r['trend']['backtest'])}",
        f"- Khớp từ khoá trend: {RM.coverage_line(r.get('coverage', {}))}.",
        f"- Sanity: {S.sanity_line(r)}.",
    ]
    if not m.get("beats_best_baseline"):
        lines.append("- Vì model gộp không thắng có ý nghĩa baseline mạnh nhất trên test, mọi trục mang nhãn "
                     "`practice`; scorer không gắn nhãn \"đã đo\".")
    return "\n".join(lines)


def data_section(d):
    fashion, rev = d.get("tikifashion") or {}, d.get("tikireviews") or {}
    reviews = ", ".join(f"{g}: {n}" for g, n in rev.get("reviews_by_group", {}).items())
    return "\n\n".join([
        data_table(d), "Tỉ lệ dòng thiếu hẳn cả nhóm cột của một trục:", missing_table(d),
        f"- `tikifashion`: {fashion.get('clean_rows')} ảnh mẫu, đã nhúng: {fashion.get('embedded')}.\n"
        f"- `tikireviews_monthly`: nhóm {', '.join(rev.get('groups', []))}; số review {reviews}.",
    ])


def _hgb_lines(m):
    params = m.get("axis_params") or {}
    plain = ["fusion"] + [a for a in m.get("axis_features", {}) if a not in params]
    lines = [f"- {', '.join(f'`{a}`' for a in plain)}: `HistGradientBoostingClassifier(learning_rate=0.05, "
             "max_iter=400, random_state=42)`, cột `group` dạng category, không dò siêu tham số; `early_stopping` "
             "mặc định (`auto`: bật khi tập học > 10.000 dòng, giữ ngẫu nhiên 10% train để dừng sớm)."]
    lines += [f"- `{a}`: " + ", ".join(f"`{k}={v}`" for k, v in p.items()) + " (learning_rate 0,05), chọn trên "
              "validation từ lưới cấu hình ở mục 9." for a, p in params.items()]
    return lines + ["- Số vòng thực tế: " + ", ".join(f"{k} {v}" for k, v in m.get("n_iter", {}).items()) + "."]


VAL_USES = ("Validation được dùng cho 5 việc, không dùng test: (1) chọn feature bổ sung (mục 4); (2) quyết định trục "
            "dùng model hay công thức (mục 5); (3) chọn cấu hình model trục ảnh trên lưới (mục 9); (4) thiết kế trọng "
            "số và khoảng của công thức ảnh (mục 9); (5) dựng phân phối tham chiếu để đổi điểm thành phân vị. Cùng "
            "một tập validation tiki26 đóng cả 5 vai, nên các số validation ở mục 4, 5 và 9 lạc quan hơn một tập chưa "
            "xem; test dùng để báo cáo.")


def method_section(r):
    m, past = r["model"], [h["model_version"] for h in r.get("history") or []]
    t = m.get("train_data") or {}
    rows = ", ".join(f"{s}: {v['rows']} dòng (top25 {v['top25_rate']:.3f})" for s, v in t.get("by_source", {}).items())
    seen = (f"- Công bố: test tiki26 đã được chấm và báo cáo cho {', '.join(f'`{v}`' for v in past)} với cùng phép "
            f"chia; danh sách đầy đủ các lần đọc test ở khối dưới.") if past else "- Test chỉ được chấm một lần."
    return "\n".join([
        *L.served_lines(r),
        *_hgb_lines(m),
        f"- Học trên `split == train` của cả hai nguồn ({rows}). {t.get('split', '')}.",
        f"- {VAL_USES}",
        seen,
        "- Hai cách chọn baseline được báo cáo: mạnh nhất trên test (spec §1.2, dùng để gắn nhãn) và mạnh nhất trên "
        "validation (tham khảo). Baseline có chữ \"+ nhóm\" học cùng cột `group`.",
        "- CI95: bootstrap 200 lần, lấy mẫu lại theo cụm seller; chênh AUC dùng bootstrap ghép cặp trên cùng mẫu.",
        "- Spearman và NDCG@10 tính trong từng (nguồn, nhóm) với mục tiêu `sold` (tiki26) hoặc "
        "`sold / max(tuổi, 30)` (tiki23), rồi lấy trung bình. \"Top 20% trúng\" là kỳ vọng khi phá hoà ngẫu nhiên "
        "đều, nên không phụ thuộc thứ tự dòng.",
        f"- Khớp từ khoá trend: ngưỡng vector `trend_match_cos` = {m['thresholds'].get('trend_match_cos')} "
        "(`None` nghĩa là chỉ khớp chữ đã bỏ dấu); hiệu chỉnh ở mục 8.",
        f"- Feature ({len(m['features'])} cột): {', '.join(f'`{c}`' for c in m['features'])}.",
    ])


def render(r, previous=None):
    m = r["model"]
    head = (f"# Báo cáo Listing Intelligence (F29 v2)\n\nSinh tự động bởi `scripts/li/evaluate.py` ngày {r['generated']}, "
            f"model `{m['model_version']}`, scikit-learn {m['sklearn']}. Mọi số liệu ở phần sinh tự động lấy nguyên từ "
            "`docs/listing_intel_results.json`. Các khối \"viết tay\" (giữa hai dấu `manual`) được giữ nguyên khi chạy "
            "lại; số trong đó lấy từ file kết quả hoặc từ audit được nêu tên.")
    sections = [
        head, "## 1. Tóm tắt", summary(r), "## 2. Dữ liệu", data_section(r["data"]),
        "## 3. Phương pháp", method_section(r) + "\n\n" + _block("reads", kept(previous, "reads")) + "\n" + S.caveats(r),
        "## 4. Chọn feature trên validation", RM.selection_section(r.get("selection")),
        "## 5. Kết quả trên test", RM.results_section(m), "## 6. Ablation từng trục", RM.ablation_section(m),
        "## 7. Test lệch thời gian (tiki23 → tiki26)", S.shift(r["shift"]),
        "## 8. Trend và mùa vụ", T.trend(r["trend"], r.get("trend_calib")) + "\n\n" + _block("calib", kept(previous, "calib")),
        "## 9. Sanity check", S.sanity(r) + "\n\n### Độ bền trục ảnh, chọn trên validation\n\n"
        + RI.section(r.get("image_robust")) + "\n\n### Công thức ảnh đang phục vụ, thiết kế trên validation\n\n"
        + RI.formula_section(r.get("image_formula")) + "\n\n### Đo lại qua đường phục vụ (`as_trained`)\n\n"
        + RI.runtime_section(r.get("image_runtime")) + "\n\n" + L.impute(r.get("impute_check"), m.get("image_impute_rule")),
        "## 10. Thay đổi so với phiên bản trước", RH.section(r) + "\n\n" + _block("changes", kept(previous, "changes")),
        "## 11. Dữ liệu VietCraft (Mongo local)", L.vietcraft(r.get("vietcraft")) + "\n\n"
        + _block("vietcraft", kept(previous, "vietcraft")),
        "## 12. Điểm yếu và ảnh hưởng", _block("weakness", kept(previous, "weakness")),
    ]
    return "\n\n".join(sections) + "\n"


def write(r, path: Path):
    previous = path.read_text("utf-8") if path.exists() else None
    path.write_text(render(r, previous), "utf-8")


def print_summary(m):
    print(metrics_table({k: v for k, v in m.get("tables", {}).get("test", {}).items()}))
    for line in RM.gate_lines(m):
        print(line)
    for a, e in m["ablation"].items():
        print(f"ablation {a}: lift={e['lift']} ci95={e['ci95']} n={e['n']} -> {m['evidence'].get(a)}")
