"""Huấn luyện + backtest rolling-origin cho mô hình dự báo cầu mùa vụ.

Chạy:  python -m app.core.seasonal_dl.train
Sinh:  model/forecaster.pt (ensemble) + model/meta.json (số liệu backtest THẬT, cờ validated).

Nguyên tắc production (học từ Amazon Forecast / Uber / Etsy):
  * Deep ensemble nhiều seed -> ước lượng bất định tốt hơn 1 mạng đơn lẻ.
  * Backtest rolling-origin 2 năm, không rò rỉ (huấn luyện chỉ thấy dữ liệu trước điểm cắt).
  * Bắt buộc thắng baseline seasonal-naive mới được bật (validated). Không thắng -> API tự
    rơi về baseline và ghi rõ, không "giả vờ AI".
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd
import torch

from app.core.listing_intel.trend_store import weekly_series
from app.core.seasonal_dl.features import FEATURE_DIM, H, L, QUANTILES, build_samples, extract_lag52_from_features
from app.core.seasonal_dl.model import QuantileForecaster, pinball_loss

MODEL_DIR = Path(__file__).parent / "model"
SEEDS = (11, 23, 37, 41, 59)
EPOCHS = 80
BATCH = 256
VAL_ORIGINS = 26


def _fit_one(seed: int, Xtr, Ytr, Xva, Yva) -> QuantileForecaster:
    torch.manual_seed(seed)
    np.random.seed(seed)
    model = QuantileForecaster()
    opt = torch.optim.AdamW(model.parameters(), lr=1.5e-3, weight_decay=1e-3)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=EPOCHS)
    xt, yt = torch.from_numpy(Xtr), torch.from_numpy(Ytr)
    xv, yv = torch.from_numpy(Xva), torch.from_numpy(Yva)
    best, best_state, bad = 1e9, None, 0
    n = len(xt)
    for _ in range(EPOCHS):
        model.train()
        perm = torch.randperm(n)
        for i in range(0, n, BATCH):
            idx = perm[i:i + BATCH]
            xb = xt[idx] + 0.01 * torch.randn_like(xt[idx])      # nhiễu nhẹ chống overfit
            loss = pinball_loss(model(xb), yt[idx])
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
        sched.step()
        model.eval()
        with torch.no_grad():
            vl = float(pinball_loss(model(xv), yv))
        if vl < best - 1e-5:
            best, bad = vl, 0
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
        else:
            bad += 1
            if bad >= 12:
                break
    model.load_state_dict(best_state)
    model.eval()
    return model


def fit_ensemble(X, Y, meta, t_val_start: int, seeds=SEEDS) -> List[QuantileForecaster]:
    """Tách validation theo thời gian (t >= t_val_start), huấn luyện N seed."""
    t = np.array([m[1] for m in meta])
    va = t >= t_val_start
    tr = t <= t_val_start - H            # purge: target train kết thúc trước target val
    if tr.sum() < 200 or va.sum() < 20:
        raise RuntimeError(f"Không đủ mẫu: train={int(tr.sum())}, val={int(va.sum())}")
    return [_fit_one(s, X[tr], Y[tr], X[va], Y[va]) for s in seeds]


def predict_ratio(models: List[QuantileForecaster], X: np.ndarray) -> np.ndarray:
    with torch.no_grad():
        xs = torch.from_numpy(X)
        out = torch.stack([m(xs) for m in models]).mean(0).numpy()   # (N,H,3), trung bình phân vị
    out = np.maximum(out, 0.0)
    out[..., 0] = np.minimum(out[..., 0], out[..., 1])
    out[..., 2] = np.maximum(out[..., 2], out[..., 1])
    return out


def evaluate(models, X, Y, S) -> Dict[str, float]:
    """Chỉ số trên tập kiểm thử. Baseline seasonal-naive = lag-52 (cột lag trong features)."""
    naive = np.clip(extract_lag52_from_features(X), 0, None)
    P = predict_ratio(models, X)
    p10, p50, p90 = P[..., 0], P[..., 1], P[..., 2]

    def smae(pred):                       # MAE theo thang từng chuỗi (mỗi từ khóa nặng như nhau)
        return float(np.abs(pred - Y).mean())

    def wmape(pred):                      # sai số tổng theo đơn vị gốc
        a = (np.abs(pred - Y) * S[:, None]).sum()
        b = (Y * S[:, None]).sum()
        return float(a / b)

    cover = float(((Y >= p10) & (Y <= p90)).mean())
    pin = float(pinball_loss(torch.from_numpy(P.astype(np.float32)), torch.from_numpy(Y)))
    naive_t = torch.from_numpy(np.stack([naive, naive, naive], -1).astype(np.float32))
    return {
        "n_samples": int(len(Y)),
        "scaled_mae_model": round(smae(p50), 4), "scaled_mae_naive": round(smae(naive), 4),
        "wmape_model": round(wmape(p50), 4), "wmape_naive": round(wmape(naive), 4),
        "coverage_p10_p90": round(cover, 4),
        "pinball_model": round(pin, 4),
        "pinball_naive_pointmass": round(float(pinball_loss(naive_t, torch.from_numpy(Y))), 4),
    }


def _horizon_breakdown(models, X, Y) -> Dict[str, Dict[str, float]]:
    naive = extract_lag52_from_features(X)
    p50 = predict_ratio(models, X)[..., 1]
    out = {}
    for name, (a, b) in {"1-4w": (0, 4), "5-13w": (4, 13), "14-26w": (13, 26)}.items():
        out[name] = {"model": round(float(np.abs(p50[:, a:b] - Y[:, a:b]).mean()), 4),
                     "naive": round(float(np.abs(naive[:, a:b] - Y[:, a:b]).mean()), 4)}
    return out


BUCKETS = {"1-4w": (0, 4), "5-13w": (4, 13), "14-26w": (13, 26)}


def _conformal(resid: np.ndarray) -> Dict[str, List[float]]:
    """Phân vị 10%/90% của sai số (thang chuỗi), theo nhóm tầm dự báo. Split-conformal."""
    out = {}
    for name, (a, b) in BUCKETS.items():
        r = resid[:, a:b].ravel()
        out[name] = [round(float(np.quantile(r, 0.10)), 4), round(float(np.quantile(r, 0.90)), 4)]
    return out


def _coverage(resid: np.ndarray, q: Dict[str, List[float]]) -> float:
    hit = []
    for name, (a, b) in BUCKETS.items():
        r = resid[:, a:b]
        hit.append(((r >= q[name][0]) & (r <= q[name][1])).ravel())
    return float(np.concatenate(hit).mean())


def backtest(series: Dict[str, pd.Series], seeds=SEEDS):
    """2 fold rolling-origin: kiểm thử trên 52 tuần cuối, và 52 tuần liền trước đó.
    Trả (kết quả JSON, sai số từng fold để hiệu chỉnh conformal)."""
    T = min(len(s) for s in series.values())
    folds, resids = [], []
    for k, cut in enumerate((T - 104, T - 52), start=1):
        X, Y, S, meta = build_samples(series, end_before=cut)
        models = fit_ensemble(X, Y, meta, t_val_start=cut - H - VAL_ORIGINS, seeds=seeds)
        Xt, Yt, St, _ = build_samples(series, t_lo=cut, t_hi=cut + 52 - H, end_before=cut + 52 + H)
        m = evaluate(models, Xt, Yt, St)
        m["fold"] = k
        m["test_from_week_index"] = int(cut)
        m["by_horizon_scaled_mae"] = _horizon_breakdown(models, Xt, Yt)
        folds.append(m)
        resids.append({"naive": Yt - extract_lag52_from_features(Xt), "model": Yt - predict_ratio(models, Xt)[..., 1]})
    return {"folds": folds}, resids


def evaluate_validation_gate(folds: List[Dict[str, Any]], margin: float = 0.97) -> Tuple[bool, float]:
    """Cổng validation nghiêm: thắng seasonal-naive ở MỌI FOLD (biên >=3%) và coverage [0.70, 0.90] ở MỌI FOLD lẫn trung bình."""
    if not folds:
        return False, 0.0
    beats_all = all(
        f["scaled_mae_model"] < margin * f["scaled_mae_naive"]
        and f["wmape_model"] < margin * f["wmape_naive"]
        for f in folds
    )
    fold_cov_ok = all(0.70 <= f["coverage_p10_p90"] <= 0.90 for f in folds)
    cov = float(np.mean([f["coverage_p10_p90"] for f in folds]))
    return bool(beats_all and fold_cov_ok and 0.70 <= cov <= 0.90), cov


def main() -> None:
    t0 = time.time()
    series = {k: v for k, v in weekly_series().items() if len(v) >= 200}
    if len(series) < 10:
        raise SystemExit(f"Dữ liệu trend không đủ ({len(series)} chuỗi)")
    T = min(len(s) for s in series.values())
    series = {k: v.iloc[-T:] for k, v in series.items()}            # căn thẳng các chuỗi
    print(f"[data] {len(series)} chuỗi x {T} tuần, đến {next(iter(series.values())).index[-1].date()}")

    bt, resids = backtest(series)
    for f in bt["folds"]:
        print(f"[fold {f['fold']}] sMAE model={f['scaled_mae_model']} naive={f['scaled_mae_naive']} | "
              f"wMAPE model={f['wmape_model']} naive={f['wmape_naive']} | cover80={f['coverage_p10_p90']}", flush=True)

    avg = lambda key: float(np.mean([f[key] for f in bt["folds"]]))
    validated, cov = evaluate_validation_gate(bt["folds"])

    # Hiệu chỉnh conformal: học trên fold 1, kiểm trên fold 2 (và ngược lại), rồi gộp cả hai để dùng thật.
    check = {}
    for key in ("naive", "model"):
        q1 = _conformal(resids[0][key])
        q2 = _conformal(resids[1][key])
        check[key] = {"calibrate_fold1_test_fold2": round(_coverage(resids[1][key], q1), 4),
                      "calibrate_fold2_test_fold1": round(_coverage(resids[0][key], q2), 4)}
    pooled = {k: np.concatenate([resids[0][k], resids[1][k]]) for k in ("naive", "model")}
    conformal = {k: _conformal(v) for k, v in pooled.items()}
    print(f"[conformal] cross-check coverage (danh định 0.80): {check}", flush=True)

    X, Y, S, meta = build_samples(series)
    models = fit_ensemble(X, Y, meta, t_val_start=T - H - VAL_ORIGINS)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    torch.save({"states": [m.state_dict() for m in models]}, MODEL_DIR / "forecaster.pt")
    meta_out = {
        "architecture": "Temporal Fusion + Lunar-Shift Attention Quantile Forecaster (Causal Conv1D + GRU + GRN + ±3w Lunar Attention)",
        "loss": "pinball (q=0.1,0.5,0.9)", "ensemble_size": len(models), "seeds": list(SEEDS),
        "horizon_weeks": H, "window_weeks": L, "quantiles": list(QUANTILES),
        "data": {"source": "Google Trends weekly (trend_interest)", "n_series": len(series), "n_weeks": T,
                 "first_week": str(next(iter(series.values())).index[0].date()),
                 "last_week": str(next(iter(series.values())).index[-1].date()),
                 "target_semantics": "chỉ số quan tâm tìm kiếm (0-100), KHÔNG phải số đơn"},
        "backtest": bt,
        "avg_scaled_mae_model": round(avg("scaled_mae_model"), 4),
        "avg_scaled_mae_naive": round(avg("scaled_mae_naive"), 4),
        "avg_wmape_model": round(avg("wmape_model"), 4), "avg_wmape_naive": round(avg("wmape_naive"), 4),
        "avg_coverage_p10_p90": round(cov, 4),
        "improvement_vs_naive_scaled_mae_pct": round(100 * (1 - avg("scaled_mae_model") / avg("scaled_mae_naive")), 1),
        "validated": validated,
        "validation_rule": "thắng seasonal-naive Ở MỌI FOLD trên cả sMAE và wMAPE với biên >=3%, và coverage P10-P90 thô Ở MỌI FOLD lẫn trung bình trong [0.70,0.90]",
        "conformal_residual_quantiles": conformal,
        "conformal_cross_check_coverage": check,
        "conformal_note": "q10/q90 của (y/scale - dự báo) theo nhóm tầm; cộng vào dự báo để có khoảng 80% đã hiệu chỉnh",
        "trained_at": datetime.now(timezone.utc).isoformat(), "torch": torch.__version__,
        "train_seconds": round(time.time() - t0, 1),
    }
    (MODEL_DIR / "meta.json").write_text(json.dumps(meta_out, ensure_ascii=False, indent=2), "utf-8")
    print(f"[done] validated={validated} improvement={meta_out['improvement_vs_naive_scaled_mae_pct']}% "
          f"coverage={meta_out['avg_coverage_p10_p90']} ({meta_out['train_seconds']}s)")


if __name__ == "__main__":
    main()

