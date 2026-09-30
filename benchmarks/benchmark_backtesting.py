from __future__ import annotations

import argparse
import csv
import json
import random
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def generate(path: Path, rows: int, impacted_le: str = "LE_7") -> None:
    rng = random.Random(11)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["LegalEntity", "AggregationLevel", "Mtf00 Gap", "EepeInEur Gap"])
        for i in range(rows):
            le = f"LE_{i % 100}"
            deal = f"D{i % 250_000:07d}"
            mtf = rng.gauss(0, 1200)
            eepe = rng.gauss(0, 1600)
            if le == impacted_le and i % 50_003 == 7:
                mtf += 100_000
                eepe += 750_000
            writer.writerow([le, f"/LegalEntity:{i % 100}/TRD:{deal}", mtf, eepe])


def upstream(path: Path, impacted_le: str = "LE_7") -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "evidence_type": "large-result-diff",
                "source": {},
                "summary": {},
                "material_impacts": [],
                "patterns": [],
                "impacted_dimensions": {"LegalEntity": [impacted_le]},
                "timings": [],
                "warnings": [],
            }
        ),
        encoding="utf-8",
    )


def main() -> int:
    p = argparse.ArgumentParser(description="Benchmark early-filtered CCR backtesting deal drilldown.")
    p.add_argument("--rows", type=int, default=1_000_000)
    p.add_argument("--backend", choices=["auto", "polars", "streaming"], default="auto")
    p.add_argument("--coverage", type=float, default=0.9)
    p.add_argument("--keep", action="store_true")
    args = p.parse_args()
    root = Path(__file__).resolve().parents[1]
    work = Path(tempfile.mkdtemp(prefix="skillhub-bt-bench-"))
    source = work / "backtesting.csv"
    evidence = work / "upstream.json"
    out = work / "out"
    t0 = time.perf_counter()
    generate(source, args.rows)
    upstream(evidence)
    generated = time.perf_counter() - t0
    cmd = [
        sys.executable,
        str(root / "skills/backtesting-drilldown/scripts/drilldown.py"),
        "--input", str(source),
        "--evidence", str(evidence),
        "--output", str(out),
        "--coverage", str(args.coverage),
        "--backend", args.backend,
    ]
    t1 = time.perf_counter()
    proc = subprocess.run(cmd, cwd=root, env={**__import__("os").environ, "PYTHONPATH": str(root)}, check=False, text=True, capture_output=True)
    elapsed = time.perf_counter() - t1
    if proc.returncode:
        print(proc.stderr, file=sys.stderr)
        return proc.returncode
    mb = source.stat().st_size / (1024 * 1024)
    print(f"rows={args.rows:,} size={mb:.1f} MiB generation={generated:.2f}s drilldown={elapsed:.2f}s throughput={mb/elapsed:.1f} MiB/s backend={args.backend}")
    print(proc.stdout)
    if args.keep:
        print(f"artifacts={work}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
