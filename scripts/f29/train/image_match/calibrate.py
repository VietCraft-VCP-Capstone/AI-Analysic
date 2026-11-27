import argparse
import json
import sys

import numpy as np
import pandas as pd

from app.core.f29.paths import MODELS, WORKSPACE

FEATURES = WORKSPACE / "agent-skills/ai-data-train-prod/data-li/features"
OUT = MODELS / "image_match/v1/metrics.json"
TARGET_FA = 0.01
GATE_FA = 0.02
GATE_CATCH = 0.5


def unit(x: np.ndarray) -> np.ndarray:
    return x / np.maximum(np.linalg.norm(x, axis=1, keepdims=True), 1e-12)


def choose_tau(pos: np.ndarray) -> float:
    return float(np.quantile(pos, TARGET_FA))


def negatives(groups: np.ndarray, rng, same: bool = False) -> np.ndarray:
    out = np.empty(len(groups), dtype=int)
    for g in np.unique(groups):
        mine = np.where(groups == g)[0]
        if same:
            out[mine] = mine[(np.arange(len(mine)) + rng.integers(1, len(mine), len(mine))) % len(mine)]
        else:
            out[mine] = rng.choice(np.where(groups != g)[0], size=len(mine))
    return out


def rates(pos: np.ndarray, neg: np.ndarray, tau: float) -> dict:
    return {"false_alarm": round(float(np.mean(pos < tau)), 4), "catch": round(float(np.mean(neg < tau)), 4)}


def mode(r: dict) -> str:
    return "live" if r["false_alarm"] <= GATE_FA and r["catch"] >= GATE_CATCH else "hint"


def load() -> pd.DataFrame:
    z = np.load(FEATURES / "emb.npz", allow_pickle=True)
    ok = np.isfinite(z["img"]).all(axis=1) & np.isfinite(z["txt"]).all(axis=1)
    key = pd.DataFrame({"listing_id": z["listing_id"], "source": z["source"], "row": np.arange(len(ok))})[ok]
    t = pd.read_parquet(FEATURES / "table.parquet", columns=["listing_id", "source", "group", "split"])
    m = t.merge(key, on=["listing_id", "source"])
    m.attrs.update(img=unit(z["img"][m["row"]]), txt=unit(z["txt"][m["row"]]))
    return m


def pairs(m: pd.DataFrame, split: str, rng) -> dict:
    s = (m["split"] == split).to_numpy()
    img, txt, groups = m.attrs["img"][s], m.attrs["txt"][s], m["group"].to_numpy()[s]
    cos = lambda j: (img * txt[j]).sum(1)
    return {"n": int(s.sum()), "pos": cos(np.arange(len(groups))),
            "other": cos(negatives(groups, rng)), "same": cos(negatives(groups, rng, same=True))}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    m = load()
    rng = np.random.default_rng(0)
    val, test = pairs(m, "val", rng), pairs(m, "test", rng)
    tau = choose_tau(val["pos"])
    other, same = rates(test["pos"], test["other"], tau), rates(test["pos"], test["same"], tau)
    out = {"tau": round(tau, 4), "mode": mode(other), "rows": {"total": len(m), "val": val["n"], "test": test["n"]},
           "groups": sorted(m["group"].unique().tolist()), "val": rates(val["pos"], val["other"], tau),
           "test": {"other_group": other, "same_group": same},
           "gate": {"false_alarm_max": GATE_FA, "catch_min": GATE_CATCH}}
    print(json.dumps(out, ensure_ascii=False, indent=1))
    if not args.dry_run:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", "utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
