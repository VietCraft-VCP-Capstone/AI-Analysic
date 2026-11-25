PILLARS = ("print", "description", "image", "duplicate")
SEVERITIES = ("block", "warn", "info", "pass", "na")
MODES = ("live", "hint", "shadow")
_RANK = {s: i for i, s in enumerate(SEVERITIES)}


def make_check(id: str, pillar: str, severity: str, evidence: dict, action: str,
               confidence: float = 1.0, model_version: str = "rule", mode: str = "live") -> dict:
    if pillar not in PILLARS:
        raise ValueError(f"pillar không hợp lệ: {pillar!r}")
    if severity not in SEVERITIES:
        raise ValueError(f"severity không hợp lệ: {severity!r}")
    if mode not in MODES:
        raise ValueError(f"mode không hợp lệ: {mode!r}")
    if not 0 <= confidence <= 1:
        raise ValueError(f"confidence ngoài 0..1: {confidence!r}")
    return {"id": id, "pillar": pillar, "severity": severity, "confidence": float(confidence),
            "evidence": evidence, "action": action, "model_version": model_version, "mode": mode}


def worst(checks: list[dict]) -> str:
    live = [c.get("severity", "na") for c in checks if c.get("mode", "live") == "live"]
    return min(live, key=lambda s: _RANK.get(s, len(_RANK)), default="na")
