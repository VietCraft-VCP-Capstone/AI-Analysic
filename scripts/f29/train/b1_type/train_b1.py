import argparse
import json
from collections import Counter

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression

from app.core.f29.checks import category as cat
from app.core.f29.shared import embedder
from scripts.f29.train.b1_type.b1_baseline import tfidf_probs
from scripts.f29.train.b1_type.b1_card import card
from scripts.f29.train.b1_type.b1_data import load, split_indices
from scripts.f29.train.b1_type.b1_stats import NAMES, compare, macro_f1, reject, scores

C_GRID = (0.1, 1, 10)
W_GRID = np.arange(0, 2.01, 0.25)
ZS_MIX, TEMP, TARGET = 0.5, 100, 0.95


def pick(raw: dict) -> tuple:
    best = max(raw, key=raw.get)
    return best, {str(k): round(v, 4) for k, v in raw.items()}


def fit_probe(X, y, tr, va):
    fits = {c: LogisticRegression(C=c, class_weight="balanced", max_iter=3000).fit(X[tr], y[tr]) for c in C_GRID}
    best, grid = pick({c: macro_f1(y[va], clf.predict(X[va])) for c, clf in fits.items()})
    return fits[best], grid


def pick_w(base: dict, img, txt, y, va):
    raw = {round(float(w), 2): macro_f1(y[va], NAMES[cat.probe_part({**base, "w": float(w)}, img[va], txt[va]).argmax(1)])
           for w in W_GRID}
    return pick(raw)


def pick_tau(P, y) -> float:
    conf, ok = P.max(1), NAMES[P.argmax(1)] == y
    order = np.argsort(-conf)
    acc = np.cumsum(ok[order]) / np.arange(1, len(y) + 1)
    good = np.flatnonzero(acc >= TARGET)
    return float(conf[order][good[-1]]) if good.size else 1.0


def prompt_matrix() -> np.ndarray | None:
    if not embedder.available():
        return None
    rows = []
    for t in cat.TYPES:
        spec = cat.TREE["types"][t]
        m = embedder.embed_texts(spec["prompts_vi"] + spec["prompts_en"]).mean(0)
        rows.append(m / np.linalg.norm(m))
    return np.stack(rows).astype(np.float32)


def variants(art, img, txt) -> dict:
    out = {"img": cat.probe_part(art, img, None), "txt": cat.probe_part(art, None, txt),
           "probe": cat.probe_part(art, img, txt), "fused": cat.probs(art, img, txt)}
    if art["prompts"] is not None:
        out |= {"zeroshot_img": cat.zs_part(art, img, None), "zeroshot_txt": cat.zs_part(art, None, txt),
                "zeroshot": cat.zs_part(art, img, txt)}
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    seed = args.seed
    d = load()
    img, txt, y, name = d["img"], d["txt"], d["y"], d["name"]
    tr, va, te, groups = split_indices(img, txt, seed)
    if args.dry_run:
        print(f"train/val/test: {len(tr)}/{len(va)}/{len(te)}")
        return
    img_clf, c_img = fit_probe(img, y, tr, va)
    txt_clf, c_txt = fit_probe(txt, y, tr, va)
    base = {"img": img_clf, "txt": txt_clf, "classes": [str(c) for c in img_clf.classes_]}
    w, w_grid = pick_w(base, img, txt, y, va)
    prompts = prompt_matrix()
    art = {**base, "w": w, "temp": TEMP, "tau": 1.0,
           "zs_mix": ZS_MIX if prompts is not None else 0.0, "prompts": prompts}
    art["tau"] = pick_tau(cat.probs(art, img[va], txt[va]), y[va])
    V = variants(art, img[te], txt[te])
    V["tfidf"] = tfidf_probs(name[tr], y[tr], name[te])
    gte = groups[te]
    hit = {k: NAMES[P.argmax(1)] == y[te] for k, P in V.items()}
    metrics = {"seed": seed, "clusters": int(len(np.unique(groups))),
               "rows": {"train": len(tr), "val": len(va), "test": len(te)},
               "test_count": {str(t): int(n) for t, n in sorted(Counter(y[te]).items())},
               "trained_types": art["classes"], "untrained_types": sorted(set(cat.TYPES) - cat.TRAINED),
               "C": {"img": img_clf.C, "txt": txt_clf.C}, "w": w, "zs_mix": art["zs_mix"], "temp": TEMP,
               "tau": art["tau"], "val_grid": {"C_img": c_img, "C_txt": c_txt, "w": w_grid},
               "test": {k: scores(P, y[te], gte) for k, P in V.items()}, "compare": compare(hit, gte),
               "reject": {"val": reject(cat.probs(art, img[va], txt[va]), y[va], art["tau"]),
                          "test": reject(V["fused"], y[te], art["tau"])}}
    out = cat.MODEL_DIR
    out.mkdir(parents=True, exist_ok=True)
    joblib.dump({k: v for k, v in art.items() if k != "prompts"}, out / "model.joblib")
    if prompts is not None:
        np.save(out / "prompts.npy", prompts)
    (out / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), "utf-8")
    (out / "card.md").write_text(card(metrics), "utf-8")


if __name__ == "__main__":
    main()
