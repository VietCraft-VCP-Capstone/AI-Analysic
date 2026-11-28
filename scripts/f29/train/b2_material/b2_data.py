import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

from app.core.f29.score.text_rules import MATERIALS, find_materials, material_line, strip_accents
from app.core.f29.score.text_rules import materials_of
from scripts.f29.eval_kit import group_split

ROOT = Path(__file__).resolve().parents[5]
DATA = ROOT / "agent-skills/ai-data-train-prod/data-li/clean/tiki23.parquet"
NONE = "none"
MERGE = {"jean": "khac"}
FORMS = sorted({f for syns in MATERIALS.values() for s in syns for f in (s.lower(), strip_accents(s.lower()))},
               key=len, reverse=True)
SYN_RE = re.compile(r"(?<!\w)(?:" + "|".join(map(re.escape, FORMS)) + r")(?!\w)", re.IGNORECASE)


def first_class(classes: list[str]) -> str:
    return MERGE.get(classes[0], classes[0]) if classes else NONE


def label_and_rest(description: str) -> tuple[str, str]:
    value, rest = material_line(description)
    return (first_class(find_materials(value)) if value else NONE), rest


def drop_materials(text: str) -> str:
    return " ".join(SYN_RE.sub(" ", unicodedata.normalize("NFC", text)).split())


def baseline_current(text: str) -> str:
    return first_class([c for term in sorted(materials_of({"title": text})) for c in find_materials(term)])


def baseline_text_vi(text: str) -> str:
    return first_class(find_materials(text))


def build() -> dict:
    df = pd.read_parquet(DATA)
    a, y, sellers = [], [], []
    for title, desc, seller in zip(df["title"].fillna(""), df["description"].fillna(""), df["seller"].fillna("")):
        label, rest = label_and_rest(str(desc))
        if label != NONE:
            a.append(f"{title} {rest}")
            y.append(label)
            sellers.append(str(seller))
    a, sellers = np.array(a), np.array(sellers)
    return {"a": a, "b": np.array([drop_materials(t) for t in a]), "y": np.array(y), "sellers": sellers,
            "splits": group_split(sellers, seed=0)}
