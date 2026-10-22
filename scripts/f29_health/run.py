import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from scripts.f29_health import candidates, frames, learn, report
from scripts.f29_ml import data
from scripts.f29_ml.run import TEST, TRAIN, VAL

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "app" / "core" / "f29" / "health_weights.json"
REPORT = ROOT.parents[1] / "notes" / "docs-listing" / "F29_HEALTH_V2.md"
REVIEW_M = 5
MIN_PEERS = 8
PRICE = {"full_at": 1.0, "zero_at": 2.0}
O_COLS = {"image": "photos", "description": "description_length",
          "review": ("review_good", "review_n"), "price": ("price", "price_ref")}
T_COLS = {"image": "n_images", "description": "desc_len", "price": ("price", "price_ref")}


def _print(metrics):
    names = list(dict.fromkeys(n for split in metrics.values() for n in split))
    for n in names:
        cells = [f"{split}={metrics[split].get(n, {}).get('roc_auc')}" for split in metrics]
        print(f"{n:32} " + "  ".join(cells))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(OUT))
    out = Path(parser.parse_args().out)
    sales, products, rated, _ = data.load()
    tables = (sales, products, rated)
    olist = {"train": frames.olist(tables, TRAIN), "val": frames.olist(tables, [VAL]), "test": frames.olist(tables, [TEST])}
    tiki = {"train": frames.tiki("train"), "test": frames.tiki("test")}
    targets = learn.targets(olist["train"], tiki["train"])
    review = {"p0": frames.olist_p0(tables, TRAIN), "m": REVIEW_M}
    o_sub = {k: learn.subscores(df, O_COLS, targets, review, PRICE) for k, df in olist.items()}
    t_sub = {k: learn.subscores(df, T_COLS, targets, review, PRICE) for k, df in tiki.items()}
    coefs = learn.fit_coefs(o_sub["train"], olist["train"]["top25"])
    weights = learn.to_weights(coefs)
    o_train_y, t_train_y = olist["train"]["top25"], tiki["train"]["top25"]
    o_val = candidates.olist(o_sub["train"], o_train_y, o_sub["val"], olist["val"], weights)
    o_test = candidates.olist(o_sub["train"], o_train_y, o_sub["test"], olist["test"], weights)
    t_test = candidates.tiki(t_sub["train"], t_train_y, t_sub["test"], tiki["test"], weights)
    metrics = {
        "olist_val": candidates.olist_metrics(olist["val"], o_val),
        "olist_test": candidates.olist_metrics(olist["test"], o_test),
        "tiki_test": candidates.tiki_metrics(tiki["test"], t_test),
    }
    gate = candidates.gate(tiki["test"], t_test)
    _print(metrics)
    print(f"weights={weights} coefficients={coefs} targets={targets} p0={review['p0']:.4f}")
    print(f"gate={gate}")
    payload = {
        "model_version": "health-2.0",
        "weights": weights,
        "targets": targets,
        "review": {"m": REVIEW_M, "p0": round(review["p0"], 4)},
        "price": PRICE | {"min_peers": MIN_PEERS},
        "coefficients": {k: round(v, 4) for k, v in coefs.items()},
        "trained_on": {"source": "Olist (Brazil)", "cutoffs": TRAIN, "rows": len(olist["train"]), "label": "top25"},
        "rows": {"olist_train": len(olist["train"]), "olist_val": len(olist["val"]),
                 "olist_test": len(olist["test"]), "tiki_train": len(tiki["train"]), "tiki_test": len(tiki["test"])},
        "dates": {"val": VAL, "test": TEST},
        "metrics": metrics,
        "gate": gate,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    _publish(payload, out)


def _publish(payload, out):
    if not payload["gate"]["passed"]:
        print("Cổng đạt KHÔNG ĐẠT: không ghi json, không ghi báo cáo.", file=sys.stderr)
        sys.exit(2)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report.write(REPORT, payload)
    print(f"Đã ghi {out} và {REPORT}")


if __name__ == "__main__":
    main()
