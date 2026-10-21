from __future__ import annotations

import numpy as np

from app.services.f30.rules import TOP_LISTINGS, WINDOW


def top_listings(per_listing: dict[str, np.ndarray], titles: dict[str, str], t: int,
                 direction: str, listing_prefix: str = "") -> list[dict]:
    rows = []
    for pid, arr in per_listing.items():
        expected = float(np.mean(arr[t - WINDOW:t]))
        actual = float(arr[t])
        delta = actual - expected
        if (direction == "drop" and delta >= 0) or (direction == "spike" and delta <= 0):
            continue
        rows.append({
            "listing_id": listing_prefix + str(pid),
            "title": titles.get(pid, ""),
            "expected": int(round(expected)),
            "actual": int(round(actual)),
            "change_pct": None if expected == 0 else round(delta / expected * 100, 1),
            "_delta": abs(delta),
        })
    rows.sort(key=lambda r: r.pop("_delta"), reverse=True)
    return rows[:TOP_LISTINGS]
