from typing import Any

LEARNED = "Học (health-2.0)"
EQUAL = "Chia đều"


def _auc(entry: Any) -> float | None:
    return entry.get("roc_auc") if isinstance(entry, dict) else None


def build(data: dict) -> dict:
    trained = data.get("trained_on") or {}
    cutoffs = trained.get("cutoffs") or ["?"]
    tiki = (data.get("metrics") or {}).get("tiki_test") or {}
    source = str(trained.get("source", "?"))
    source = source[:1].upper() + source[1:]
    return {
        "weights": data["weights"],
        "trained_on": f"{source}, {trained.get('rows', '?')} dòng, mốc {cutoffs[0]}..{cutoffs[-1]}",
        "tiki_test_auc": _auc(tiki.get(LEARNED)),
        "equal_auc": _auc(tiki.get(EQUAL)),
    }
