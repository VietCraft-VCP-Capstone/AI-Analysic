import numpy as np
import pandas as pd

from scripts.li import reference


def make_table():
    val_bags = pd.DataFrame({"id": range(25), "group": "bags", "split": "val"})
    val_wallet = pd.DataFrame({"id": range(100, 105), "group": "wallet", "split": "val"})
    rest = pd.DataFrame({"id": [200, 201], "group": "wallet", "split": ["train", "test"]})
    return pd.concat([val_bags, val_wallet, rest], ignore_index=True)


def test_population_is_validation_rows_only():
    pop = reference.population(make_table())
    assert set(pop["split"]) == {"val"}
    assert not set(pop["id"]) & {200, 201}


def test_small_group_gets_no_key_and_all_exists():
    table = make_table()
    pop = reference.population(table)
    s = np.arange(len(pop), dtype=float)
    dist = reference._dist(pop, s, reference.big_groups(table))
    assert "bags" in dist
    assert "wallet" not in dist
    assert "all" in dist
    assert np.array_equal(dist["all"], np.percentile(s, reference.QS))
