"""Shared Redis + L1 in-memory TTL cache helper cho AI Analytics."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Optional

_L1: dict[str, tuple[float, Any]] = {}
_CLIENT = None
_CLIENT_INIT = False


def _resolve_redis_url() -> Optional[str]:
    url = os.getenv("REDIS_URL")
    if url:
        return url.strip()
    for env_path in (
        Path(__file__).resolve().parents[1] / ".env",
        Path(__file__).resolve().parents[3] / "backend" / ".env",
    ):
        if env_path.exists():
            try:
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    s = line.strip()
                    if s.startswith("REDIS_URL="):
                        return s.split("=", 1)[1].strip().strip('"').strip("'")
            except Exception:
                pass
    return None


def _get_client():
    global _CLIENT, _CLIENT_INIT
    if _CLIENT_INIT:
        return _CLIENT
    _CLIENT_INIT = True
    url = _resolve_redis_url()
    if not url:
        return None
    try:
        import redis
        cli = redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=1.5,
            socket_timeout=1.5,
        )
        cli.ping()
        _CLIENT = cli
    except Exception:
        _CLIENT = None
    return _CLIENT


def cache_get_json(key: str) -> Optional[Any]:
    now = time.monotonic()
    hit = _L1.get(key)
    if hit and hit[0] > now:
        return hit[1]
    cli = _get_client()
    if cli is not None:
        try:
            raw = cli.get(key)
            if raw:
                val = json.loads(raw)
                _L1[key] = (now + 600.0, val)
                return val
        except Exception:
            pass
    return None


def cache_set_json(key: str, val: Any, ttl_seconds: int = 1800) -> None:
    _L1[key] = (time.monotonic() + min(float(ttl_seconds), 300.0), val)
    cli = _get_client()
    if cli is not None:
        try:
            cli.setex(key, ttl_seconds, json.dumps(val, ensure_ascii=False))
        except Exception:
            pass

