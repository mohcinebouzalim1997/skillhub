from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def test_prepare_ccr_release_evidence_end_to_end(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[1]
    cvar = tmp_path / "cvar.csv"
    gcvar = tmp_path / "gcvar.csv"
    bt = tmp_path / "bt.csv"
    header = "LegalEntity,AggregationLevel,Currency (Test),EffectiveMaturity (Ref),EffectiveMaturity (Test),Mtf00 Gap,EepeInEur Gap,Rwa Gap\n"
    _write(cvar, header + "LE_A,/LegalEntity:1/Master:1,EUR,1,2,90000,120000,5000\n")
    _write(gcvar, header + "LE_A,/LegalEntity:1/Master:1,EUR,1,1,20000,30000,0\n")
    _write(
        bt,
        "LegalEntity,AggregationLevel,Currency (Test),EffectiveMaturity (Ref),EffectiveMaturity (Test),Mtf00 Gap,EepeInEur Gap,Rwa Gap\n"
        "LE_A,/LegalEntity:1/TRD:D1,EUR,1,2,70000,100000,5000\n"
        "LE_A,/LegalEntity:1/TRD:D2,EUR,1,1,20000,20000,0\n"
        "LE_B,/LegalEntity:2/TRD:D9,USD,1,9,999999,999999,999999\n",
    )
    out = tmp_path / "release-work"
    proc = subprocess.run(
        [
            sys.executable,
            str(repo / "skills/prepare-ccr-release-evidence/scripts/prepare.py"),
            "--cvar", str(cvar),
            "--cvar-backtesting", str(bt),
            "--gcvar", str(gcvar),
            "--gcvar-backtesting", str(bt),
            "--prod-ref", "release/26.9",
            "--candidate-ref", "release/26.10",
            "--output", str(out),
            "--backend", "streaming",
        ],
        cwd=repo,
        env={**os.environ, "PYTHONPATH": str(repo), "SKILLHUB_ROOT": str(repo)},
        text=True,
        capture_output=True,
        check=True,
    )
    assert '"ok": true' in proc.stdout.lower()
    manifest = json.loads((out / "workflow_manifest.json").read_text())
    assert manifest["production_ref"] == "release/26.9"
    assert manifest["candidate_ref"] == "release/26.10"
    context = (out / "workflow_context.md").read_text()
    assert "CVAR" in context and "GCVAR" in context
    assert "D1" in context
    assert "raw compare/backtesting csvs are intentionally not embedded" in context.lower()
    assert "LegalEntity,AggregationLevel" not in context
    hints = json.loads((out / "pr_forensics_hints.json").read_text())
    assert "EffectiveMaturity" in hints["changed_fields"]
