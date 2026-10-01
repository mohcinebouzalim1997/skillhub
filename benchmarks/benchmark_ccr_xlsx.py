from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser(description="Benchmark the real XLSX->evidence path on a CCR result workbook.")
    p.add_argument("--input", required=True, help="CcrMetrics.xlsx / CcrMetrics_Gcvar.xlsx / backtesting workbook")
    p.add_argument("--profile", choices=["cvar", "gcvar"], default="cvar")
    p.add_argument("--output")
    p.add_argument("--backend", choices=["auto", "polars", "streaming"], default="auto")
    p.add_argument("--repeat", type=int, default=2, help="Run twice by default to show first parse versus cache reuse")
    args = p.parse_args()

    root = Path(__file__).resolve().parents[1]
    out = Path(args.output).resolve() if args.output else Path(tempfile.mkdtemp(prefix="skillhub-xlsx-bench-"))
    script = root / "skills/analyze-large-result-diff/scripts/analyze.py"
    timings = []
    for run in range(1, max(1, args.repeat) + 1):
        started = time.perf_counter()
        proc = subprocess.run(
            [sys.executable, str(script), "--profile", args.profile, "--input", str(Path(args.input).resolve()), "--output", str(out), "--backend", args.backend],
            cwd=root,
            env={**os.environ, "PYTHONPATH": str(root)},
            text=True,
            capture_output=True,
        )
        elapsed = round(time.perf_counter() - started, 6)
        timings.append({"run": run, "elapsed_seconds": elapsed, "ok": proc.returncode == 0})
        if proc.returncode:
            print(proc.stdout); print(proc.stderr, file=sys.stderr); return proc.returncode
    manifest = json.loads((out / "run_manifest.json").read_text(encoding="utf-8"))
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    print(json.dumps({
        "input": str(Path(args.input).resolve()),
        "file_size_bytes": Path(args.input).stat().st_size,
        "rows_scanned": summary.get("summary", {}).get("rows_scanned"),
        "backend": summary.get("summary", {}).get("backend"),
        "runs": timings,
        "stage_timings_last_run": manifest.get("timings"),
        "workbook_cache_hit_last_run": summary.get("source", {}).get("workbook_cache_hit"),
        "output": str(out),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
