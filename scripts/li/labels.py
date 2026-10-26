import numpy as np
import pandas as pd
from sklearn.model_selection import GroupShuffleSplit


def top25(df: pd.DataFrame, score_col: str, by: list[str]) -> pd.Series:
    return (df.groupby(by)[score_col].rank(pct=True) > 0.75).astype(int)


def split_by_seller(df: pd.DataFrame, seller_col: str) -> pd.Series:
    idx = np.arange(len(df))
    missing = df[seller_col].isna().to_numpy()
    solo = np.char.add("row-", idx.astype(str))
    groups = np.where(missing, solo, df[seller_col].astype(str).to_numpy()).astype(str)
    train, rest = next(GroupShuffleSplit(1, train_size=0.7, random_state=42).split(idx, groups=groups))
    val, test = next(GroupShuffleSplit(1, train_size=0.5, random_state=42).split(rest, groups=groups[rest]))
    out = np.empty(len(df), dtype=object)
    out[train], out[rest[val]], out[rest[test]] = "train", "val", "test"
    return pd.Series(out, index=df.index)
