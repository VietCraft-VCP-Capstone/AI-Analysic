import numpy as np
import pandas as pd

from tests.listing_intel.test_bundle import synthetic


def test_image_override_reads_saved_robustness():
    from scripts.li.assess import image_override

    design = {"n_val": 507, "configs": 241, "model": {"params": {"max_iter": 10, "max_depth": 4}, "max_shift": 0.0,
                                                      "p90_shift": 33.75},
              "formula": {"name": "c8", "p90_shift": {"a": 13.26, "b": 5.75}}}
    reason = image_override(design)
    assert "33,8" in reason and "13,3" in reason and "max_iter=10" in reason
    assert image_override({**design, "model": {**design["model"], "p90_shift": 9.0}}) is None
    assert image_override(None) is None


def test_availability_maps():
    from scripts.li.availability import feature_constants, image_impute
    from scripts.li.fit import FULL, fit

    train = synthetic(seed=1)
    train = train[train["split"] == "train"].assign(desc_len=0.0)
    train.loc[train["group"] == "bags", "img_sharpness"] = np.nan
    fill = image_impute(train, fit(train, FULL))
    assert set(fill) == {"fashion"}
    rows = train[train["group"] == "fashion"][list(fill["fashion"])].round(6)
    assert (rows == pd.Series(fill["fashion"])).all(axis=1).any()
    assert all(v["desc_len"] == 0.0 for v in feature_constants(train).values())


def test_trained_on_is_plain_vietnamese():
    from scripts.li.train import _trained_on

    text = _trained_on({"rows": 30402, "by_source": {"tiki23": {"rows": 27693}, "tiki26": {"rows": 2709}},
                        "date": "2026-10-21"})
    assert text.startswith("30.402 sản phẩm Tiki (27.693 năm 2023 và 2.709 năm 2026)") and "21/10/2026" in text
