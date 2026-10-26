from typing import Any

from app.core.f29.constants import MODEL_VERSION

LEARNED = f"Học ({MODEL_VERSION})"
EQUAL = "Chia đều"
MARKETS = ("olist_test", "tiki_test", "shopee_test")
SOURCES = {"image": "learned", "description": "learned", "price": "learned",
           "tags": "policy", "material": "policy", "review": "floor"}


def _auc(entry: Any) -> float | None:
    return entry.get("roc_auc") if isinstance(entry, dict) else None


def _find_learned_key(metrics: dict, version: str | None = None) -> str:
    if version:
        cand = f"Học ({version})"
        for m in MARKETS:
            if cand in (metrics.get(m) or {}):
                return cand
    for m in MARKETS:
        for k in (metrics.get(m) or {}):
            if k.startswith("Học (") and k.endswith(")"):
                return k
    return LEARNED


def _markets(data: dict, learned_key: str) -> dict:
    metrics, lift = data.get("metrics") or {}, data.get("lift") or {}
    return {m: {"auc": _auc((metrics.get(m) or {}).get(learned_key)), "lift": lift.get(m)} for m in MARKETS}


def build(data: dict) -> dict:
    trained = data.get("trained_on") or {}
    cutoffs = trained.get("cutoffs") or ["?"]
    metrics = data.get("metrics") or {}
    tiki = metrics.get("tiki_test") or {}
    learned_key = _find_learned_key(metrics, data.get("model_version"))
    source = str(trained.get("source", "?"))
    source = source[:1].upper() + source[1:]
    return {
        "weights": data["weights"],
        "trained_on": f"{source}, {trained.get('rows', '?')} dòng, mốc {cutoffs[0]}..{cutoffs[-1]}",
        "tiki_test_auc": _auc(tiki.get(learned_key)),
        "equal_auc": _auc(tiki.get(EQUAL)),
        "ranges": data.get("ranges"),
        "sources": dict(SOURCES),
        "markets": _markets(data, learned_key),
    }
