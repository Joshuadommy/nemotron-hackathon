"""Disk-backed LLM response cache for development.

Keyed on a stable hash of (model, messages, tools, temperature, response_format).
Saves identical calls from re-billing while iterating on the UI/agent.
Disable with COMPLIANCE_CACHE=0 in the environment.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

CACHE_DIR = Path(__file__).parent / ".cache"


def _enabled() -> bool:
    return os.getenv("COMPLIANCE_CACHE", "1") != "0"


def _key(payload: dict[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:32]


def _path(key: str) -> Path:
    return CACHE_DIR / f"{key}.json"


def get(payload: dict[str, Any]) -> dict[str, Any] | None:
    if not _enabled():
        return None
    p = _path(_key(payload))
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def put(payload: dict[str, Any], response: dict[str, Any]) -> None:
    if not _enabled():
        return
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _path(_key(payload)).write_text(json.dumps(response, default=str))


def clear() -> int:
    if not CACHE_DIR.exists():
        return 0
    n = 0
    for f in CACHE_DIR.glob("*.json"):
        f.unlink()
        n += 1
    return n
