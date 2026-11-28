import hashlib
import io
import json
import os
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from app.api.v1._live import LOC_SP_THAT, db_live
from app.core.f29.checks.duplicates import as_row, external_host, match_level, pix_hd
from app.core.f29.checks.duplicates import fingerprint
from app.core.f29.checks import run
from app.core.f29.shared import embedder, image_load
from scripts.f29.train.i_dupes.dupes_copies import KINDS, make_copy

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "app/core/f29/models/i_dupes/v1"
CACHE = Path(os.environ.get("F29_IMG_CACHE", "/tmp/claude-1000/-home-rio-Documents-CODE-nodejs-vietcraft/"
                            "6ecfcc2a-1536-45d6-a4c1-f6bffb34e441/scratchpad/research/vc_imgs"))
N_ORIG = 200
MAX_FPR = 0.01
NEAR_DUP = 0.99
SEED = 0
HIT = ("exact", "near")
C_GRID = np.round(np.arange(0.50, 1.0005, 0.001), 3)


def _cache_path(url: str) -> Path:
    return CACHE / hashlib.sha1(url.encode()).hexdigest()



def _decode(data: bytes):
    rgba = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGBA")
    out = Image.new("RGB", rgba.size, "white")
    out.paste(rgba, mask=rgba.getchannel("A"))
    return out


def _load(url: str):
    path = _cache_path(url)
    return _decode(path.read_bytes()) if path.exists() else run.rgba(url)


def _listings() -> list[tuple]:
    rows = db_live()["products"].find({"status": "PUBLISHED", **LOC_SP_THAT}, {"images": 1, "categories": 1})
    items = []
    for p in rows:
        if not p.get("categories"):
            continue
        for url in p.get("images") or []:
            if isinstance(url, str) and external_host(url) is None:
                items.append((url, str(p["_id"]), p["categories"][0]))
    return sorted(items, key=lambda it: not _cache_path(it[0]).exists())


def _originals() -> list[dict]:
    out = []
    for url, pid, cat in _listings():
        img = _load(url)
        if img is not None:
            out.append({"pid": pid, "cat": cat, "img": img})
        if len(out) == N_ORIG:
            break
    return out


def _embed(img) -> np.ndarray:
    return embedder.embed_images([image_load.as_trained(img)])[0]


def _record(fp: dict, vec) -> dict:
    row = as_row(fp, vec)
    return {"fp": fp, "row": row, "v": np.asarray(row["vec"], dtype=float)}


def _build(origs: list[dict]) -> tuple[list[dict], list[dict]]:
    orig = [_record(fingerprint(o["img"]), _embed(o["img"])) for o in origs]
    copies = []
    for i, o in enumerate(origs):
        for k, kind in enumerate(KINDS):
            c = make_copy(o["img"], kind, np.random.default_rng([SEED, i, k]))
            copies.append({"src": i, "kind": kind, **_record(fingerprint(c), _embed(c))})
    return orig, copies


def _groups(n: int) -> np.ndarray:
    grp = np.zeros(n, dtype=bool)
    grp[np.random.default_rng(SEED).permutation(n)[: n // 2]] = True
    return grp


def _negatives(origs: list[dict], orig: list[dict], grp: np.ndarray) -> tuple[list[tuple], int]:
    pairs, excluded = [], 0
    for i in range(len(origs)):
        for j in range(i + 1, len(origs)):
            if grp[i] != grp[j] or origs[i]["cat"] != origs[j]["cat"] or origs[i]["pid"] == origs[j]["pid"]:
                continue
            if float(orig[i]["v"] @ orig[j]["v"]) >= NEAR_DUP:
                excluded += 1
                continue
            pairs.append((i, j))
    return pairs, excluded


def _stats(q: dict, r: dict) -> tuple[float, float]:
    return float(pix_hd(q["fp"], r["row"])), float(q["v"] @ r["v"])


def _search_h(pos: np.ndarray, neg: np.ndarray) -> int:
    best = None
    for h in range(65):
        fpr = float(np.mean(neg <= h))
        if fpr <= MAX_FPR:
            key = (float(np.mean(pos <= h)), -fpr, -h)
            if best is None or key > best[0]:
                best = (key, h)
    return best[1]


def _search_c(pos: np.ndarray, neg: np.ndarray, h: int) -> float:
    best = None
    for c in C_GRID:
        fpr = float(np.mean((neg[:, 0] <= h) | (neg[:, 1] >= c)))
        if fpr <= MAX_FPR:
            key = (float(np.mean((pos[:, 0] <= h) | (pos[:, 1] >= c))), -fpr, float(c))
            if best is None or key > best[0]:
                best = (key, float(c))
    return round(best[1], 3)


def _wilson(k: int, n: int, z: float = 1.96) -> list[float]:
    p = k / n
    d = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / d
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(float(mid - half), 4), round(float(mid + half), 4)]


def _metrics(th: dict, pos: np.ndarray, copies: list, orig: list, negs: list, n_a: int) -> dict:
    neg_lvl = [match_level(orig[i]["fp"], orig[i]["v"], orig[j]["row"], th) for i, j in negs]
    pos_lvl = [match_level(c["fp"], c["v"], orig[c["src"]]["row"], th) for c in copies]
    n = len(negs)
    k_warn = sum(lvl in HIT for lvl in neg_lvl)
    k_info = sum(lvl is not None for lvl in neg_lvl)
    fpr_warn, fpr_info = k_warn / n, k_info / n
    per_kind = {}
    for kind in KINDS:
        idx = [m for m, c in enumerate(copies) if c["kind"] == kind]
        warn = float(np.mean([pos_lvl[m] in HIT for m in idx]))
        tp = warn * len(idx)
        per_kind[kind] = {
            "warn_recall": round(warn, 3),
            "info_recall": round(float(np.mean([pos_lvl[m] is not None for m in idx])), 3),
            "precision_balanced": round(tp / (tp + fpr_warn * len(idx)), 3) if tp else 0.0,
            "recall_cos_only": round(float(np.mean(pos[idx, 1] >= th["c"])), 3),
        }
    return {**th, "h_dung_cho": "mức near (warn): pHash phash, phash_flip, phash_crop",
            "c_dung_cho": "mức similar (info): cosine, và hợp với pHash để giữ báo nhầm ≤ 1%",
            "c_similar_dung_cho": "tham khảo, không dùng để khớp",
            "chia_nhom": {"seed": SEED, "goc_nhom_A": n_a, "goc_nhom_B": len(orig) - n_a,
                          "chon_nguong_tren": "nhóm A", "bao_cao_tren": "nhóm B"},
            "n_B_copies": len(copies), "n_B_negatives": n,
            "fpr_warn_B": round(fpr_warn, 4), "fpr_warn_wilson95_B": _wilson(k_warn, n),
            "fpr_info_B": round(fpr_info, 4), "fpr_info_wilson95_B": _wilson(k_info, n),
            "muc_tieu_1pct": {"warn": "đạt" if fpr_warn <= MAX_FPR else "không đạt",
                              "info": "đạt" if fpr_info <= MAX_FPR else "không đạt"},
            "per_kind_B": per_kind}


def main() -> None:
    t0 = time.time()
    origs = _originals()
    orig, copies = _build(origs)
    grp = _groups(len(origs))
    negs, excluded = _negatives(origs, orig, grp)
    pos = np.array([_stats(c, orig[c["src"]]) for c in copies])
    neg = np.array([_stats(orig[i], orig[j]) for i, j in negs])
    cg = np.array([grp[c["src"]] for c in copies])
    ng = np.array([grp[i] for i, _ in negs])
    h = _search_h(pos[cg, 0], neg[ng, 0])
    c = _search_c(pos[cg], neg[ng], h)
    th = {"h": h, "c": c, "c_similar": round(float(np.percentile(neg[ng, 1], 95)), 4)}
    b_copies = [c_ for c_, g in zip(copies, cg) if not g]
    b_negs = [p for p, g in zip(negs, ng) if not g]
    metrics = _metrics(th, pos[~cg], b_copies, orig, b_negs, int(grp.sum()))
    metrics |= {"excluded_near_dup_pairs": excluded, "seconds": round(time.time() - t0, 1)}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "thresholds.json").write_text(json.dumps(th, indent=2) + "\n")
    (OUT / "metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(metrics, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
