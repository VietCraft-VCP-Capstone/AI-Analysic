import functools
import hashlib
import json
import tempfile
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from bson import ObjectId
from PIL import Image
from sklearn.decomposition import PCA

from app.api.v1 import f29_health
from app.core.listing_intel import embedder, fusion, image_fetch, intel, live_data, store, trend_store
from app.core.listing_intel.context import FeatureContext, prompt_texts, save_context
from app.core.listing_intel.market_axis import KnnIndex
from app.core.listing_intel.types import ListingInput
from tests.f29.fake_mongo import _FakeCollection, _FakeMongoClient
from tests.listing_intel.test_bundle import synthetic

SHOP = "64b000000000000000000001"
OTHER_SHOP = "64b000000000000000000002"
PID = "64c000000000000000000001"
URLS = ["https://res.cloudinary.com/demo/image/upload/a.jpg",
        "https://res.cloudinary.com/demo/image/upload/b.jpg"]


def fake_vec(text) -> np.ndarray:
    seed = int(hashlib.sha1(str(text).encode()).hexdigest()[:8], 16)
    v = np.random.default_rng(seed).normal(size=embedder.EMBED_DIM).astype(np.float32)
    return v / np.linalg.norm(v)


def _context(out: Path) -> None:
    rng = np.random.default_rng(1)
    vecs = rng.normal(size=(60, embedder.EMBED_DIM)).astype(np.float32)
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    ctx = FeatureContext(
        lift={"fashion": {"áo": 0.3, "áo thun": 0.5, "cotton": 0.4, "basic": -0.2}},
        group_median_price={"fashion": 200000.0, "bags": 300000.0, "all": 250000.0},
        pca=PCA(16, random_state=0).fit(vecs.astype(np.float64)),
        prompt_vecs={k: fake_vec(v) for k, v in prompt_texts().items()},
        knn={"fashion": KnnIndex(vecs, rng.uniform(1e5, 4e5, 60), rng.random(60) > 0.75)},
        trend_kw_vecs={k: fake_vec(k) for k in ("áo thun", "túi tote")},
        group_season={"fashion": np.linspace(0.6, 1.4, 52)},
        centroids={"fashion": (vecs[0], vecs[1])},
    )
    save_context(ctx, out)


@functools.cache
def bundle_dir() -> Path:
    from scripts.li.train import fit_bundle

    root = Path(tempfile.mkdtemp(prefix="li-bundle-"))
    _context(root / "ctx")
    table = synthetic()
    fit_bundle(table, root / "model", root / "ctx")
    (root / "model/reference/top_medians.json").write_text(json.dumps(fusion.top_medians(table)), "utf-8")
    return root / "model"


def series() -> dict:
    idx = pd.date_range("2021-10-03", "2026-10-18", freq="W-SUN")
    woy = idx.isocalendar().week.to_numpy().astype(float)
    return {"áo thun": pd.Series(50 + 30 * np.sin(woy / 52 * 2 * np.pi), index=idx)}


def product(pid=PID, shop=SHOP, **kw) -> dict:
    return {"_id": ObjectId(pid), "shop_id": ObjectId(shop), "title": "Áo thun nam cotton cổ tròn",
            "description": "Áo thun mềm mại", "tags": ["áo thun"], "materials": ["cotton"],
            "categories": ["Áo thun"], "images": list(URLS), "is_hidden": False,
            "updated_at": datetime(2026, 10, 20), **kw}


def listing(**kw) -> ListingInput:
    base = dict(title="Áo thun nam cotton cổ tròn basic", description="Áo thun mềm mại " * 12,
                tags=["áo thun", "cotton", "áo thun"], materials=["cotton"], category="Áo thun",
                group="fashion", price=199000.0, image_urls=list(URLS), product_id=PID, seller_id=SHOP)
    return ListingInput(**{**base, **kw})


def _image(*_a, **_k) -> Image.Image:
    return Image.fromarray(np.random.default_rng(3).integers(0, 255, (600, 600, 3), dtype=np.uint8))


@pytest.fixture
def env(monkeypatch):
    db = _FakeMongoClient()["vietcraft-test"]
    db.client, db.indexes = SimpleNamespace(address=("127.0.0.1", 27017)), []
    monkeypatch.setattr(_FakeCollection, "create_index", lambda self, keys, **kw: db.indexes.append((keys, kw)),
                        raising=False)
    monkeypatch.setitem(store._indexed, "done", False)
    monkeypatch.setattr(intel, "_PEER_ROWS", {})
    db["products"].seed([product(), product("64c000000000000000000002", title="Áo thun nữ in hình"),
                         product("64c000000000000000000003", OTHER_SHOP, title="Túi tote vải", categories=["Túi"])])
    db["product_variants"].seed([{"product_id": ObjectId(PID), "retail_price": 199000, "is_active": True}])
    db["tags"].seed([{"name": "sexy", "status": "pending"}, {"name": "áo thun", "status": "active"}])
    for mod in (store, live_data, f29_health):
        monkeypatch.setattr(mod, "db_live", lambda: db)
    monkeypatch.setenv("LI_BUNDLE_DIR", str(bundle_dir()))
    monkeypatch.setattr(embedder, "available", lambda: True)
    monkeypatch.setattr(embedder, "embed_texts", lambda texts: np.stack([fake_vec(t) for t in texts]))
    monkeypatch.setattr(embedder, "embed_images", lambda ims: np.stack([fake_vec(np.asarray(i).mean()) for i in ims]))
    monkeypatch.setattr(image_fetch, "fetch", _image)
    monkeypatch.setattr(trend_store, "weekly_series", series)
    return db
