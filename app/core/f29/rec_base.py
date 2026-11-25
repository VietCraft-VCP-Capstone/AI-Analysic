from typing import Any, Dict, Optional

from app.core.f29.constants import EFFORT


def make(kind: str, key: str, field: str, title: str, why: str, action: str, effort_key: str,
         gain: float, method: str, evidence: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {"id": f"{kind}:{key}", "kind": kind, "title": title, "why": why, "action": action,
            "field": field, "effort": EFFORT[effort_key], "gain_points": round(gain, 1),
            "method": method, "evidence": evidence or {}}


def factor(result: Dict[str, Any], key: str) -> Dict[str, Any]:
    return next(f for f in result["factors"] if f["key"] == key)


def num(value: float) -> str:
    return f"{value:,.0f}".replace(",", ".")


def scope(category: Optional[str], in_category: bool) -> str:
    return f"danh mục {category}" if in_category and category else "toàn sàn"
