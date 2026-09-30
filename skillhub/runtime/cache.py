from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .artifacts import file_metadata, stable_cache_key


def source_cache_key(path: str | Path, *configuration: object) -> str:
    """Stable metadata cache key without hashing multi-GB source contents."""
    meta = file_metadata(path)
    return stable_cache_key(meta["path"], meta["size_bytes"], meta["modified_ns"], *configuration)


def read_cache(cache_dir: str | Path, key: str) -> dict[str, Any] | None:
    path = Path(cache_dir) / f"{key}.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def write_cache(cache_dir: str | Path, key: str, payload: dict[str, Any]) -> Path:
    path = Path(cache_dir) / f"{key}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    return path
