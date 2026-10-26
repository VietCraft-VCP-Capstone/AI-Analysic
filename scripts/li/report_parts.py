SET_LABELS = {
    "test": "Test tiki26 (tập chính)",
    "val": "Validation tiki26",
    "test_tiki23": "Test tiki23",
    "test_all": "Test gộp 2 nguồn",
    "val_all": "Validation gộp 2 nguồn",
}
AXIS_LABELS = {"image": "Ảnh", "text": "Từ khoá (chữ)", "tags": "Tag", "market": "Thị hiếu và cạnh tranh",
               "trend": "Trend và mùa vụ"}


def f3(v):
    return "—" if v is None else f"{v:.3f}"


def ci(c):
    return "—" if not c else f"[{c[0]:.3f}; {c[1]:.3f}]"


def signed(v):
    return "—" if v is None else f"{v:+.4f}"


def pct(v):
    return "—" if v is None else f"{v:.1%}"


def metrics_table(rows):
    head = ["| Phương pháp | ROC-AUC | CI95 (bootstrap theo seller) | PR-AUC | AUC trong nhóm | Spearman | "
            "NDCG@10 | Top 20% trúng | n dòng (cụm seller) |", "|---|---|---|---|---|---|---|---|---|"]
    body = [f"| {n} | {f3(m['roc_auc'])} | {ci(m['auc_ci95'])} | {f3(m['pr_auc'])} | {f3(m['within_cat_auc'])} "
            f"| {f3(m['spearman'])} | {f3(m['ndcg10'])} | {pct(m['top20_hit'])} | {m['n']} ({m['n_sellers']}) |"
            if m else f"| {n} | — | — | — | — | — | — | — | — |" for n, m in rows.items()]
    return "\n".join(head + body)


def data_table(data):
    head = ["| Nguồn | Dòng thô | Sau làm sạch | Trong bảng feature | Tập | Số dòng | Tỉ lệ top25 | Seller | "
            "Dòng không có seller |", "|---|---|---|---|---|---|---|---|---|"]
    body = []
    for src in ("tiki23", "tiki26"):
        d = data.get(src)
        if not d:
            continue
        for k, (split, s) in enumerate(d["splits"].items()):
            lead = f"| {src} | {d['raw_rows'] or '—'} | {d['clean_rows']} | {d['table_rows']} |" if k == 0 \
                else "| | | | |"
            body.append(f"{lead} {split} | {s['rows']} | {s['top25_rate']:.3f} | {s['sellers']} | {s['rows_no_seller']} |")
    return "\n".join(head + body)


def missing_table(data):
    head = ["| Nguồn | Nhóm danh mục | " + " | ".join(f"{AXIS_LABELS[a]} thiếu hẳn" for a in
                                                  ("image", "text", "market", "trend")) + " |",
            "|---|---|---|---|---|---|"]
    body = [f"| {s} | {', '.join(data[s]['groups'])} | " + " | ".join(
        pct(data[s]["axis_all_nan_share"][a]) for a in ("image", "text", "market", "trend")) + " |"
        for s in ("tiki23", "tiki26") if s in data]
    return "\n".join(head + body)


def ablation_table(ab, evidence):
    head = ["| Trục bỏ ra | AUC giảm (lift) | CI95 ghép cặp | Số dòng test đo | Nguồn đo | Nhãn |",
            "|---|---|---|---|---|---|"]
    body = [f"| {AXIS_LABELS[a]} | {signed(e['lift'])} "
            f"| {ci(e['ci95'])} | {e['n']} | {', '.join(e.get('sources', [])) or '—'} | {evidence.get(a, '—')} |"
            for a, e in ab.items()]
    return "\n".join(head + body)


def shift_table(sh):
    head = ["| Cách học | Số dòng học | ROC-AUC trên tiki26 test | CI95 | AUC trong nhóm | Chênh với học tại chỗ | CI95 chênh |",
            "|---|---|---|---|---|---|---|"]
    body = [f"| {v['label']} | {v['rows_fit']} | {f3(v.get('roc_auc'))} | {ci(v.get('auc_ci95'))} | "
            f"{f3(v.get('within_cat_auc'))} | {signed(v.get('delta_vs_in_domain'))} | {ci(v.get('delta_ci95'))} |"
            for k, v in sh.items() if isinstance(v, dict)]
    return "\n".join(head + body)


def season_table(sc):
    head = ["| Nhóm | Số từ khoá Google Trends | Pearson r (p) | Spearman ρ (p) |", "|---|---|---|---|"]
    body = [f"| {g} | {v['n_keywords']} | " + (f"{v['pearson']:.3f} ({v['p_pearson']:.3f}) | "
                                                f"{v['spearman']:.3f} ({v['p_spearman']:.3f}) |"
                                                if v["n_keywords"] else "— | — |") for g, v in sc.items()]
    return "\n".join(head + body)


def peaks_table(pk):
    lo, hi = pk["window_weeks"]
    head = [f"| Từ khoá | Dịp | Số năm | Độ lệch đỉnh trung vị (tuần) | Tỉ lệ năm có đỉnh ở độ lệch {lo:+d} … {hi:+d} tuần |",
            "|---|---|---|---|---|"]
    body = [f"| {r['keyword']} | {r['event']} | {r['years']} | {r['median_offset']:+.1f} | {pct(r['share_before'])} |"
            for r in pk["per_keyword"]]
    return "\n".join(head + body)
