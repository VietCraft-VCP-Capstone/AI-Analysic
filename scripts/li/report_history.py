from scripts.li.report_parts import ci, f3, signed

LABELS = ["ROC-AUC model gộp, test tiki26", "AUC trong nhóm, test tiki26",
          "Model trục ảnh học có giám sát, test tiki26", "Trục ảnh đang phục vụ, test tiki26",
          "Chênh với baseline mạnh nhất trên test", "Bất biến ảnh: lệch trung vị (điểm phân vị)", "Chế độ chấm trục",
          "Nhãn chứng cứ"]


def summary(r):
    m = r["model"]
    return {"model_version": m["model_version"], "generated": r.get("generated"), "test": m["metrics"]["test"],
            "tables": m["tables"]["test"], "best": m["best_baseline"], "evidence": m["evidence"],
            "image_sanity": r.get("image_sanity"), "modes": {a: e["mode"] for a, e in (m.get("axis_modes") or {}).items()}}


def history(old, model_version):
    if not old:
        return []
    past = old.get("history") or ([old["previous"]] if old.get("previous") else [])
    return past if old["model"]["model_version"] == model_version else past + [summary(old)]


def _auc(tables, name):
    return ((tables or {}).get(name) or {}).get("roc_auc")


def _served_image(s):
    if (s.get("modes") or {}).get("image", "model") == "model":
        return f"{f3(_auc(s.get('tables'), 'Chỉ trục image'))} (model)"
    v = _auc(s.get("tables"), "Công thức trục image")
    return f"{f3(v)} (công thức)" if v is not None else "chưa đo (công thức)"


def _column(s):
    img = s.get("image_sanity") or {}
    shifts = "; ".join(f"{k} {v}" for k, v in (img.get("median_shift_pct") or {}).items()) or "—"
    served = f" ({img['served_mode']})" if img.get("served_mode") else ""
    return [f"{f3(s['test']['roc_auc'])} {ci(s['test']['auc_ci95'])}", f3(s["test"]["within_cat_auc"]),
            f3(_auc(s.get("tables"), "Chỉ trục image")), _served_image(s),
            f"{signed(s['best']['delta'])} {ci(s['best']['ci95'])} (`{s['best']['name']}`)", shifts + served,
            ", ".join(f"{a}: {v}" for a, v in (s.get("modes") or {}).items()) or "model (cả 3 trục)",
            ", ".join(f"{a}: {v}" for a, v in s["evidence"].items())]


def section(r):
    runs = list(r.get("history") or []) + [summary(r)]
    if len(runs) == 1:
        return "_Không có kết quả phiên bản trước để so._"
    cols = [_column(s) for s in runs]
    head = ["| Chỉ số | " + " | ".join(f"{s['model_version']} ({s['generated']})" for s in runs) + " |",
            "|---" * (len(runs) + 1) + "|"]
    return "\n".join(head + [f"| {label} | " + " | ".join(c[i] for c in cols) + " |" for i, label in enumerate(LABELS)])
