from typing import Any, Dict, Optional


def _num(x: float) -> str:
    return f"{x:g}".replace(".", ",")


REVIEW_KEY = "review"
REVIEW_BLAME = "mục Đánh giá thay đổi vì có đánh giá mới hoặc sản phẩm cùng loại thay đổi."


def _points(doc: Dict[str, Any]) -> Dict[str, float]:
    return {f["key"]: f["points"] for f in doc.get("factors") or [] if f.get("points") is not None}


def _labels(doc: Dict[str, Any]) -> Dict[str, str]:
    return {f["key"]: f.get("label") or f["key"] for f in doc.get("factors") or []}


def _same_model(prev: Dict[str, Any], result: Dict[str, Any]) -> bool:
    if prev.get("model_version") != result.get("model_version") or prev.get("incomplete"):
        return False
    return (prev.get("versions") or {}).get("stamp") == (result.get("versions") or {}).get("stamp")


def _biggest_change(prev: Dict[str, Any], result: Dict[str, Any]) -> Optional[str]:
    before, after = _points(prev), _points(result)
    if not before or not after:
        return None
    keys = list(after) + [k for k in before if k not in after]
    delta = {k: after.get(k, 0) - before.get(k, 0) for k in keys}
    key = max(keys, key=lambda k: abs(delta[k]))
    return key if delta[key] != 0 else None


def _market_blame(key: str, result: Dict[str, Any]) -> str:
    if key == REVIEW_KEY:
        return REVIEW_BLAME
    return f"mục {_labels(result).get(key, key)} thay đổi vì các sản phẩm cùng loại trên sàn thay đổi."


def explain(prev: Optional[Dict[str, Any]], result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if prev is None or not prev.get("content_snapshot") or result.get("incomplete"):
        return None
    old, new = prev.get("score"), result.get("score")
    if old is None or new is None or abs(new - old) < 1.0 or not _same_model(prev, result):
        return None
    word = "lên" if new > old else "xuống"
    edited = (prev["content_snapshot"] != result.get("content_snapshot")
              or prev.get("content_hash") != result.get("content_hash"))
    if edited:
        text = f"Điểm {word} từ {_num(old)} thành {_num(new)} sau khi bạn sửa sản phẩm."
        return {"from": old, "to": new, "reason": "content", "factor": None, "text": text}
    key = _biggest_change(prev, result)
    if key is None:
        return None
    text = (f"Điểm {word} từ {_num(old)} thành {_num(new)} dù bạn không sửa gì: "
            f"{_market_blame(key, result)}")
    return {"from": old, "to": new, "reason": "market", "factor": key, "text": text}
