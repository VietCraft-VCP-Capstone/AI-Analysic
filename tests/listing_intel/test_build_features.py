import math
from dataclasses import replace
from datetime import date

import numpy as np
import pandas as pd

from scripts.li import build_features as B
from scripts.li import paths
from tests.listing_intel.test_features import rich_ctx


def test_load_rows_guards_text_and_drops_label_columns(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    base = {"listing_id": [1, 2], "group": "bags", "price": [1e5, 2e5], "sold": [3, 0], "top25": [1, 0],
            "split": ["train", "val"], "title": ["Túi da", None], "description": [None, "mô tả"]}
    pd.DataFrame({**base, "source": "tiki23", "n_images": [4, 6], "seller": ["s1", "s2"],
                  "age_days": [100, 40]}).to_parquet(paths.clean("tiki23.parquet"))
    pd.DataFrame({**base, "source": "tiki26", "image_url": ["u1", "u2"], "scraped_at": "2026-04-18T16:07:30.36",
                  "seller": pd.array(["x", None], dtype="string")}).to_parquet(paths.clean("tiki26.parquet"))
    df = B.load_rows()
    assert "age_days" not in df
    assert df["title"].tolist() == ["Túi da", "", "Túi da", ""]
    assert df["description"].tolist() == ["", "mô tả", "", "mô tả"]
    assert df["at"].tolist() == [date(2023, 9, 15)] * 2 + [date(2026, 4, 18)] * 2
    assert df["seller"].tolist()[3] is None
    assert df["n_images"].iloc[:2].tolist() == [4, 6] and df["n_images"].iloc[2:].isna().all()


def test_assemble_rows_uses_fold_context_and_self_exclusion():
    ctx = rich_ctx()
    fold = replace(ctx, lift={"bags": {"túi": 5.0}})
    vec = ctx.knn["bags"].vecs[3].astype(np.float32)
    df = pd.DataFrame({"title": "túi da", "description": "", "group": "bags", "price": 1e5,
                       "image_url": "u", "seller": None, "at": date(2026, 4, 18)}, index=[0, 1])
    txt = np.stack([vec, vec])
    img = np.zeros_like(txt)
    quals = [{"img_w": 1.0}, {"img_w": 1.0}]
    out = B.assemble_rows(df, txt, img, quals, ctx, {0: fold}, np.array([0, -1]), {0: 3})
    assert out["kw_lift_sum"].tolist() == [5.0, 0.1]
    assert out["knn_dup_count"].iloc[0] < out["knn_dup_count"].iloc[1]
    assert list(out.columns) == B.F.FEATURE_COLS and not math.isnan(out["trend_factor"].iloc[0])


def test_knn_positions_leave_seller_out():
    from scripts.li.fit_context import _knn, seller_keys

    df = pd.DataFrame({"source": "tiki26", "seller": ["a", "a", None, "b"]})
    vecs = np.eye(4, dtype=np.float32)
    _, pos = _knn(vecs, np.ones(4), np.zeros(4, bool), np.array(["g"] * 4), np.ones(4, bool), seller_keys(df))
    assert pos[0].tolist() == [0, 1] and pos[1].tolist() == [0, 1]
    assert pos[2].tolist() == [2] and pos[3].tolist() == [3]
