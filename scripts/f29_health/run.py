import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from app.core.f29 import material
from app.core.f29.constants import MODEL_VERSION
from scripts.f29_health import candidates, evidence, frames, learn, report, shopee
from scripts.f29_ml import data
from scripts.f29_ml.run import TEST, TRAIN, VAL

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "app" / "core" / "f29" / "health_weights.json"
REPORT = ROOT.parent / "notes" / "docs-listing" / "04_KET_QUA_TRAIN_DIEM_SUC_KHOE.md"
REVIEW_M = 5
O_COLS = {"image": "photos", "description": "description_length",
          "review": ("review_good", "review_n"), "price": "price_pct"}
T_COLS = {"image": "n_images", "description": "desc_len", "price": "price_pct"}
CONTROLS = {"olist": ["log_seller_sales", "log_seller_listings", "seller_rating"],
            "tiki": ["log_seller_listings"],
            "shopee": ["log_seller_listings", "log_followers", "official", "shop_rating"]}
SHARED = ["image", "description", "price"]
ACCEPT_NOTE = ("Chủ dự án chấp nhận: trọng số học thắng chia đều về AUC ở Tiki và Shopee, "
               "chưa đạt mức lift 1,2 ở Olist và Shopee (chia đều cũng chưa đạt ở Olist).")


def _prepare(df, by):
    seller = "seller_id" if "seller_id" in df else "seller"
    if "log_seller_listings" not in df:
        df = df.assign(log_seller_listings=np.log1p(df.groupby(seller)[seller].transform("size")))
    return df.assign(price_pct=df.groupby(by)["price"].rank(pct=True) * 100)


def _print(metrics):
    names = list(dict.fromkeys(n for split in metrics.values() for n in split))
    for n in names:
        cells = [f"{split}={metrics[split].get(n, {}).get('roc_auc')}" for split in metrics]
        print(f"{n:32} " + "  ".join(cells))


def _pair(sub, y):
    img, price = evidence.pair_share(learn.fit_coefs(sub[["image", "price"]], y), "image", "price")
    return {"image": img, "price": price}


def _material_rate(df):
    has = df[["title", "description"]].apply(lambda r: material.has_material(r.to_dict()), axis=1)
    top = df["top25"] == 1
    return {"share": round(100 * has.mean(), 1), "top25_with": round(100 * top[has].mean(), 1),
            "top25_without": round(100 * top[~has].mean(), 1)}


def _load_shopee():
    try:
        return shopee.load()
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        sys.exit(2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(OUT))
    parser.add_argument("--accept-gate-fail", action="store_true")
    args = parser.parse_args()
    out = Path(args.out)
    shop_all = _load_shopee()
    sales, products, rated, _ = data.load()
    tables = (sales, products, rated)
    olist = {k: _prepare(frames.olist(tables, c), "category") for k, c in (("train", TRAIN), ("val", [VAL]), ("test", [TEST]))}
    tiki = {k: _prepare(frames.tiki(k), "group") for k in ("train", "test")}
    shop = {k: _prepare(shop_all[shop_all["split"] == k], "group") for k in ("train", "test")}
    targets = learn.targets(olist["train"], tiki["train"])
    review = {"p0": frames.olist_p0(tables, TRAIN), "m": REVIEW_M}
    o_sub = {k: learn.subscores(df, O_COLS, targets, review) for k, df in olist.items()}
    t_sub = {k: learn.subscores(df, T_COLS, targets, review) for k, df in tiki.items()}
    s_sub = {k: learn.subscores(df, T_COLS, targets, review) for k, df in shop.items()}
    o_train_y, t_train_y, s_train_y = olist["train"]["top25"], tiki["train"]["top25"], shop["train"]["top25"]
    market = {
        "olist": learn.fit_coefs(o_sub["train"], o_train_y, olist["train"][CONTROLS["olist"]]),
        "tiki": learn.fit_coefs(t_sub["train"], t_train_y, tiki["train"][CONTROLS["tiki"]]),
        "shopee": learn.fit_coefs(s_sub["train"], s_train_y, shop["train"][CONTROLS["shopee"]]),
    }
    coefs = learn.pooled(list(market.values()), SHARED) | {"review": learn.shares(market["olist"])["review"]}
    lam = learn.agreement(list(market.values()), SHARED)
    weights = learn.to_weights(coefs, lam)
    o_val = candidates.olist(o_sub["train"], o_train_y, o_sub["val"], olist["val"], weights)
    o_test = candidates.olist(o_sub["train"], o_train_y, o_sub["test"], olist["test"], weights)
    t_test = candidates.tiki(t_sub["train"], t_train_y, t_sub["test"], tiki["test"], weights)
    s_test = candidates.tiki(s_sub["train"], s_train_y, s_sub["test"], shop["test"], weights)
    metrics = {
        "olist_val": candidates.olist_metrics(olist["val"], o_val),
        "olist_test": candidates.olist_metrics(olist["test"], o_test),
        "tiki_test": candidates.tiki_metrics(tiki["test"], t_test),
        "shopee_test": candidates.tiki_metrics(shop["test"], s_test),
    }
    gate = candidates.gate({"olist_test": (olist["test"], o_test), "tiki_test": (tiki["test"], t_test),
                            "shopee_test": (shop["test"], s_test)})
    ranges = evidence.weight_ranges(o_sub["train"], o_train_y, olist["train"]["product_id"].to_numpy())
    tiki_check = {"tiki": _pair(t_sub["train"], t_train_y), "olist": _pair(o_sub["train"], o_train_y)}
    _print(metrics)
    print(f"lambda={lam} weights={weights} coefficients={market} p0={review['p0']:.4f}")
    print(f"gate={gate}")
    payload = {
        "model_version": MODEL_VERSION,
        "weights": weights,
        "targets": targets,
        "review": {"m": REVIEW_M, "p0": round(review["p0"], 4)},
        "lambda": lam,
        "coefficients": {k: round(v, 4) for k, v in coefs.items()},
        "market_coefficients": {m: {k: round(v, 4) for k, v in c.items()} for m, c in market.items()},
        "controls": CONTROLS,
        "trained_on": {"source": "Olist (Brazil)", "cutoffs": TRAIN, "rows": len(olist["train"]), "label": "top25",
                       "blend": "shares averaged over Olist/Tiki/Shopee (review from Olist); lambda * learned + (1 - lambda) * equal, tags fixed 20, floor 10"},
        "rows": {"olist_train": len(olist["train"]), "olist_val": len(olist["val"]),
                 "olist_test": len(olist["test"]), "tiki_train": len(tiki["train"]), "tiki_test": len(tiki["test"]),
                 "shopee_test": len(shop["test"])},
        "dates": {"val": VAL, "test": TEST},
        "metrics": metrics,
        "gate": gate,
        "lift": {m: v["lift"] for m, v in gate["per_market"].items()},
        "ranges": ranges,
        "tiki_check": tiki_check,
        "material_rate": _material_rate(tiki["train"]),
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if args.accept_gate_fail and not gate["passed"]:
        payload["gate"]["accepted_by_owner"] = ACCEPT_NOTE
    _publish(payload, out)


def _publish(payload, out):
    if not payload["gate"]["passed"] and "accepted_by_owner" not in payload["gate"]:
        print("Cổng đạt KHÔNG ĐẠT: không ghi json, không ghi báo cáo.", file=sys.stderr)
        sys.exit(2)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report.write(REPORT, payload)
    print(f"Đã ghi {out} và {REPORT}")


if __name__ == "__main__":
    main()
