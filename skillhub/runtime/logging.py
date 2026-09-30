from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from typing import Any, TextIO


def event(name: str, *, stream: TextIO | None = None, **fields: Any) -> None:
    """Emit one machine-readable JSON event without bringing in a logging framework."""
    payload = {"timestamp": datetime.now(timezone.utc).isoformat(), "event": name, **fields}
    (stream or sys.stderr).write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
