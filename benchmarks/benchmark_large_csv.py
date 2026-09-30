from __future__ import annotations

import argparse
import csv
import random
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def generate(path: Path, rows: int) -> None:
    """Generate a lightweight synthetic file using the real CCR gap header names."""
    rng = random.Random(7)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["LegalEntity", "AggregationLevel", "Mtf00 Gap", "EepeInEur Gap", "EffectiveMaturity (Ref)", "EffectiveMaturity (Test)", "Noise"])
        for i in range(rows):
            le = f"LE_{i % 100}"
            agg = f"/LegalEntity:{i % 100}/Master:{i}"
            mtf = rng.gauss(0, 1500)
            eepe = rng.gauss(0, 1800)
            maturity_ref = 1.0 + (i % 10) / 10
            maturity_test = maturity_ref
            if i % 100_003 == 0:
                mtf += 150_000
                eepe += 2_000_000
                maturity_test += 0.5
            writer.writerow([le, agg, mtf, eepe, maturity_ref, maturity_test, "x"])


def main() -> int:
    p = argparse.ArgumentParser(description="Benchmark CVAR/GCVAR large-CSV reduction using production materiality defaults.")
    p.add_argument("--rows", type=int, default=1_000_000)
    p.add_argument("--backend", choices=["auto", "polars", "streaming"], default="auto")
    p.add_argument("--coverage", type=float, default=0.9)
    p.add_argument("--keep", action="store_true")
    args = p.parse_args()
    root = Path(__file__).resolve().parents[1]
    work = Path(tempfile.mkdtemp(prefix="skillhub-bench-"))
    source = work / "cvar.csv"
    out = work / "out"
    t0 = time.perf_counter()
    generate(source, args.rows)
    generated = time.perf_counter() - t0
    cmd = [
        sys.executable,
        str(root / "skills/analyze-large-result-diff/scripts/analyze.py"),
        "--profile", "cvar",
        "--input", str(source),
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
    print(f"rows={args.rows:,} size={mb:.1f} MiB generation={generated:.2f}s analysis={elapsed:.2f}s throughput={mb/elapsed:.1f} MiB/s backend={args.backend}")
    print(proc.stdout)
    if args.keep:
        print(f"artifacts={work}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
