from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def ensure_output_dir(path: str | Path) -> Path:
    out = Path(path).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    return out


def file_metadata(path: str | Path) -> dict[str, Any]:
    p = Path(path).expanduser().resolve()
    stat = p.stat()
    return {"path": str(p), "size_bytes": stat.st_size, "modified_ns": stat.st_mtime_ns}


def stable_cache_key(*parts: object) -> str:
    encoded = json.dumps(parts, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def write_json(path: str | Path, payload: Any) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    return p
