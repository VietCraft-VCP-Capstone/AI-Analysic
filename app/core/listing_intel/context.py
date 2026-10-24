import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import numpy as np

from .market_axis import KnnIndex

PROMPTS = Path(__file__).parent / "data" / "style_prompts.json"


@dataclass
class Projection:
    components_: np.ndarray
    mean_: np.ndarray

    def transform(self, x) -> np.ndarray:
        x = np.asarray(x, dtype=np.float64)
        return x @ self.components_.T - self.mean_[None] @ self.components_.T


@dataclass
class FeatureContext:
    lift: dict = field(default_factory=dict)
    group_median_price: dict = field(default_factory=dict)
    pca: object = None
    prompt_vecs: dict = field(default_factory=dict)
    knn: dict = field(default_factory=dict)
    trend_series: dict = field(default_factory=dict)
    trend_kw_vecs: dict = field(default_factory=dict)
    group_season: dict = field(default_factory=dict)
    at: date = field(default_factory=date.today)
    centroids: dict = field(default_factory=dict)
    trend_match_cos: float | None = None
    trend_keywords: list | None = None


def prompt_texts() -> dict[str, str]:
    data = json.loads(PROMPTS.read_text("utf-8"))
    return {**data["groups"], **{f"style_{k}": v for k, v in data["styles"].items()}}


def _write(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


def _read(path: Path):
    return json.loads(path.read_text("utf-8"))


def save_context(ctx: FeatureContext, out) -> None:
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    _write(out / "lift.json", ctx.lift)
    _write(out / "group_median_price.json", ctx.group_median_price)
    _write(out / "thresholds.json", {"trend_match_cos": ctx.trend_match_cos, "trend_keywords": ctx.trend_keywords})
    _write(out / "group_season.json", {g: [float(x) for x in v] for g, v in ctx.group_season.items()})
    if ctx.pca is not None:
        np.savez(out / "pca.npz", components=ctx.pca.components_, mean=ctx.pca.mean_)
    np.savez(out / "prompt_vecs.npz", **ctx.prompt_vecs)
    kws = list(ctx.trend_kw_vecs)
    vecs = np.stack([ctx.trend_kw_vecs[k] for k in kws]) if kws else np.zeros((0, 0), np.float32)
    np.savez(out / "trend_kw_vecs.npz", keywords=np.array(kws, dtype=str), vecs=vecs)
    for g, idx in ctx.knn.items():
        np.savez(out / f"knn_{g}.npz", vecs=idx.vecs.astype(np.float16), prices=idx.prices, top=idx.top)
    cents = {f"{g}__{k}": c for g, pair in ctx.centroids.items() for k, c in zip(("top", "rest"), pair)}
    np.savez(out / "centroids.npz", **cents)


def _pca(path: Path):
    if not path.exists():
        return None
    z = np.load(path)
    return Projection(z["components"], z["mean"])


def load_context(src, at: date | None = None, trend_series: dict | None = None) -> FeatureContext:
    src = Path(src)
    if trend_series is None:
        from .trend_store import weekly_series

        trend_series = weekly_series()
    kw = np.load(src / "trend_kw_vecs.npz")
    cents = np.load(src / "centroids.npz")
    groups = {k.rsplit("__", 1)[0] for k in cents.files}
    th = _read(src / "thresholds.json")
    return FeatureContext(
        lift=_read(src / "lift.json"),
        group_median_price=_read(src / "group_median_price.json"),
        pca=_pca(src / "pca.npz"),
        prompt_vecs=dict(np.load(src / "prompt_vecs.npz")),
        knn={p.stem.removeprefix("knn_"): KnnIndex(**np.load(p)) for p in sorted(src.glob("knn_*.npz"))},
        trend_series=trend_series,
        trend_kw_vecs=dict(zip(kw["keywords"].tolist(), kw["vecs"])),
        group_season={g: np.asarray(v) for g, v in _read(src / "group_season.json").items()},
        at=at or date.today(),
        centroids={g: (cents[f"{g}__top"], cents[f"{g}__rest"]) for g in groups},
        trend_match_cos=th["trend_match_cos"],
        trend_keywords=th.get("trend_keywords"),
    )
