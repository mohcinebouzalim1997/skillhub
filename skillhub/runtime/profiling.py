from __future__ import annotations

import os
try:
    import resource  # type: ignore
except ImportError:  # Windows
    resource = None
import time
from dataclasses import dataclass, field
from typing import Any


def _rss_mb() -> float | None:
    try:
        if resource is None:
            return None
        value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # Linux reports KiB; macOS reports bytes. The project primarily targets Linux/Windows
        # runners, but keep the value conservative across platforms.
        if os.name == "posix" and value > 10_000_000:
            return round(value / (1024 * 1024), 2)
        return round(value / 1024, 2)
    except Exception:
        return None


@dataclass
class StageTimer:
    """Tiny stage profiler that produces JSON-serializable timing records."""

    timings: list[dict[str, Any]] = field(default_factory=list)

    def measure(self, name: str):
        return _Stage(self, name)


class _Stage:
    def __init__(self, parent: StageTimer, name: str) -> None:
        self.parent = parent
        self.name = name
        self.started = 0.0
        self.rss_before: float | None = None

    def __enter__(self):
        self.started = time.perf_counter()
        self.rss_before = _rss_mb()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        elapsed = time.perf_counter() - self.started
        rss_after = _rss_mb()
        row: dict[str, Any] = {"stage": self.name, "elapsed_seconds": round(elapsed, 6)}
        if rss_after is not None:
            row["peak_rss_mb"] = rss_after
        if self.rss_before is not None and rss_after is not None:
            row["rss_delta_mb"] = round(max(0.0, rss_after - self.rss_before), 2)
        self.parent.timings.append(row)
