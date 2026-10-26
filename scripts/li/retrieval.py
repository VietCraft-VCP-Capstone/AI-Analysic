import numpy as np

from app.core.listing_intel.features import unit
from scripts.li import paths

N_PAIRS = 200


def retrieval(img, txt, n=N_PAIRS, seed=42):
    img, txt = np.asarray(img, np.float32), np.asarray(txt, np.float32)
    ok = np.flatnonzero(np.isfinite(img).all(1) & np.isfinite(txt).all(1))
    idx = np.random.default_rng(seed).choice(ok, min(n, len(ok)), replace=False)
    sims = unit(img[idx]) @ unit(txt[idx]).T
    diag = np.diag(sims)
    rank_i2t = (sims > diag[:, None]).sum(1) + 1
    rank_t2i = (sims > diag[None, :]).sum(0) + 1
    chance = 1 / len(idx)
    top1 = float(np.mean(rank_i2t == 1))
    return {
        "n": int(len(idx)),
        "top1_img_to_txt": round(top1, 3),
        "top1_txt_to_img": round(float(np.mean(rank_t2i == 1)), 3),
        "recall5_img_to_txt": round(float(np.mean(rank_i2t <= 5)), 3),
        "median_rank_img_to_txt": float(np.median(rank_i2t)),
        "chance_top1": round(chance, 4),
        "ratio_vs_chance": round(top1 / chance, 1),
        "mean_cos_pair": round(float(diag.mean()), 4),
        "mean_cos_other": round(float((sims.sum() - diag.sum()) / (sims.size - len(diag))), 4),
    }


def run():
    path = paths.DATA_DIR / "features" / "emb_tikifashion.npz"
    if not path.exists():
        return None
    z = np.load(path)
    return retrieval(z["img"], z["txt"])
