from typing import Any, Dict, List

from app.core.f29.score.preview import preview_health

LEVERS = {"n_images": ("image", 3), "description_length": ("description", 200), "n_tags": ("tags", 2)}
EPS = 0.05


def _base(r: Dict[str, Any]) -> Dict[str, float]:
    snap = r["content_snapshot"]
    tags = next(f for f in r["factors"] if f["key"] == "tags")
    return {"n_images": snap["n_images"], "description_length": snap["desc_words"],
            "n_tags": tags["evidence"]["approved"], "price": snap["price"]}


def eligible(r: Dict[str, Any]) -> bool:
    rows = {f["key"]: f["state"] for f in r["factors"]}
    return all(rows[k] == "scored" for k in ("image", "description", "tags", "price")) and bool(_base(r)["price"])


def violations(calc, r: Dict[str, Any]) -> List[str]:
    pid, base, out = r["product_id"], _base(r), []

    def at(lever: str, value: float) -> Dict[str, Any]:
        res = preview_health(calc, pid, {lever: value})
        if not res or "axes" not in res:
            raise RuntimeError(f"preview {lever}={value} returned {res}")
        return res

    for lever, (key, step) in LEVERS.items():
        cur, zero, up = at(lever, base[lever]), at(lever, 0), at(lever, base[lever] + step)
        if zero["axes"][key] != 0:
            out.append(f"{lever}=0 gives {key} sub {zero['axes'][key]}")
        for name, hi, lo in (("up<cur", up, cur), ("zero>cur", cur, zero)):
            if hi["score"] < lo["score"] - EPS or (hi["axes"][key] or 0) < (lo["axes"][key] or 0) - EPS:
                out.append(f"{lever} {name}: {hi['score']}/{hi['axes'][key]} < {lo['score']}/{lo['axes'][key]}")
    low, high = at("price", base["price"] * 0.5), at("price", base["price"] * 2)
    if (low["axes"]["price"] or 0) < (high["axes"]["price"] or 0) - EPS:
        out.append(f"price half sub {low['axes']['price']} < double sub {high['axes']['price']}")
    return out
