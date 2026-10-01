from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def test_large_result_diff_and_backtesting_end_to_end(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[1]
    cvar = tmp_path / "cvar.csv"
    _write(
        cvar,
        "RowId,LegalEntity,AggregationLevel,Product,mtf00Gap,EepeInEurGap,Noise\n"
        "1,LE_A,AGG_X,Swap,0.01,100,x\n"
        "2,LE_A,AGG_X,Swap,0.80,2500000,x\n"
        "3,LE_A,AGG_X,Swap,-0.70,-1800000,x\n"
        "4,LE_B,AGG_Y,FX,0.02,200,x\n",
    )
    out = tmp_path / "evidence"
    cmd = [
        sys.executable,
        str(repo / "skills/analyze-large-result-diff/scripts/analyze.py"),
        "--profile", "cvar",
        "--input", str(cvar),
        "--output", str(out),
        "--threshold", "EepeInEurGap=1000000",
        "--threshold", "mtf00Gap=0.5",
        "--backend", "streaming",
    ]
    subprocess.run(cmd, cwd=repo, check=True, capture_output=True, text=True, env={**__import__("os").environ, "PYTHONPATH": str(repo)})
    evidence = json.loads((out / "summary.json").read_text())
    assert evidence["summary"]["rows_scanned"] == 4
    assert evidence["summary"]["material_rows"] >= 2
    assert "LE_A" in evidence["impacted_dimensions"].get("LegalEntity", [])
    context = (out / "agent_context.md").read_text()
    assert "2500000" in context
    assert "RowId,LegalEntity" not in context  # raw CSV is not embedded

    bt = tmp_path / "bt.csv"
    _write(
        bt,
        "DealId,LegalEntity,AggregationLevel,EepeInEurGap,mtf00Gap\n"
        "D1,LE_A,AGG_X,1500000,0.4\n"
        "D2,LE_A,AGG_X,800000,0.2\n"
        "D3,LE_A,AGG_X,100000,0.1\n"
        "D4,LE_B,AGG_Y,9000000,4.0\n",
    )
    btout = tmp_path / "btout"
    subprocess.run(
        [
            sys.executable,
            str(repo / "skills/backtesting-drilldown/scripts/drilldown.py"),
            "--input", str(bt),
            "--evidence", str(out / "summary.json"),
            "--output", str(btout),
            "--backend", "streaming",
        ],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        env={**__import__("os").environ, "PYTHONPATH": str(repo)},
    )
    result = json.loads((btout / "backtesting_summary.json").read_text())
    assert result["summary"]["rows_scanned"] == 4
    assert result["summary"]["rows_matching_upstream_dimensions"] == 3
    deals = {next(iter(row["identity"].values())) for row in result["material_impacts"] if row["identity"]}
    assert "D1" in deals
    assert "D4" not in deals


def test_polars_fast_path_when_available(tmp_path: Path) -> None:
    import importlib.util
    import pytest

    if importlib.util.find_spec("polars") is None:
        pytest.skip("Polars fast-path dependency is not installed in this environment")
    repo = Path(__file__).resolve().parents[1]
    source = tmp_path / "fast.csv"
    _write(
        source,
        "RowId,LegalEntity,AggregationLevel,mtf00Gap,EepeInEurGap\n"
        "1,LE_A,AGG_X,0.01,10\n"
        "2,LE_A,AGG_X,0.8,2500000\n"
        "3,LE_B,AGG_Y,0.02,20\n",
    )
    out = tmp_path / "fast-out"
    proc = subprocess.run(
        [
            sys.executable,
            str(repo / "skills/analyze-large-result-diff/scripts/analyze.py"),
            "--profile", "cvar",
            "--input", str(source),
            "--output", str(out),
            "--threshold", "EepeInEurGap=1000000",
            "--threshold", "mtf00Gap=0.5",
            "--backend", "polars",
        ],
        cwd=repo,
        env={**__import__("os").environ, "PYTHONPATH": str(repo)},
        text=True,
        capture_output=True,
        check=True,
    )
    assert '"backend": "polars"' in proc.stdout
    payload = json.loads((out / "summary.json").read_text())
    assert payload["summary"]["backend"] == "polars"
    assert payload["summary"]["material_rows"] == 1


def test_real_ccr_headers_strict_10k_coverage_and_ref_test_diagnostics(tmp_path: Path) -> None:
    """Exercise the real compare-job naming shown in the CCR screenshots."""
    repo = Path(__file__).resolve().parents[1]
    cvar = tmp_path / "cvar-real.csv"
    _write(
        cvar,
        "LegalEntity,AggregationLevel,EepeError (Ref),EepeRatio (Ref),EffectiveMaturity (Ref),RiskWeightedExposureFactor (Ref),"
        "EepeError (Test),EepeRatio (Test),EffectiveMaturity (Test),RiskWeightedExposureFactor (Test),"
        "Mtf00 (Ref),CashFlowType (Ref),Currency (Ref),Eepe (Ref),EepeInEur (Ref),Rwa (Ref),"
        "Mtf00 (Test),CashFlowType (Test),Currency (Test),Eepe (Test),EepeInEur (Test),Rwa (Test),"
        "Mtf00 Gap,Abs(Mtf00 Gap),Mtf00 Ratio,CashFlowType (Result),Currency (Result),Eepe Gap,Abs(Eepe Gap),Eepe Ratio,"
        "EepeInEur Gap,Abs(EepeInEur Gap),EepeInEur Ratio,Rwa Gap,Abs(Rwa Gap),Rwa Ratio\n"
        "LE_A,/LegalEntity:1/Master:1,10,1,1,100,11,1,2,101,-1,None,EUR,100,100,0,99999,None,EUR,101,101,0,100000,100000,0.1,TRUE,TRUE,1,1,0.01,120000,120000,1.2,0,0,0\n"
        "LE_A,/LegalEntity:1/Master:2,10,1,1,100,10,1,1,100,-1,None,EUR,100,100,0,19999,None,EUR,100,100,0,20000,20000,0.1,TRUE,TRUE,0,0,0,20000,20000,0.2,0,0,0\n"
        "LE_B,/LegalEntity:2/Master:3,10,1,1,100,10,1,1,100,-1,None,USD,100,100,0,9999,None,USD,100,100,0,10000,10000,0.1,TRUE,TRUE,0,0,0,10000,10000,0.1,0,0,0\n"
        "LE_C,/LegalEntity:3/Master:4,10,1,1,100,9,1,1,99,-1,None,EUR,100,100,0,-11002,None,EUR,90,90,0,-11001,-11001,-0.1,TRUE,TRUE,-10,10,-0.1,-15000,15000,-0.15,0,0,0\n",
    )
    out = tmp_path / "real-evidence"
    subprocess.run(
        [
            sys.executable,
            str(repo / "skills/analyze-large-result-diff/scripts/analyze.py"),
            "--profile", "cvar",
            "--input", str(cvar),
            "--output", str(out),
            "--backend", "streaming",
        ],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        env={**__import__("os").environ, "PYTHONPATH": str(repo)},
    )
    evidence = json.loads((out / "summary.json").read_text())
    assert evidence["metric_policy"]["Mtf00Gap"]["source_column"] == "Mtf00 Gap"
    assert evidence["metric_policy"]["EepeInEurGap"]["source_column"] == "EepeInEur Gap"
    # Exactly 10,000 is not material because the confirmed rule is strictly "over 10k".
    assert evidence["metric_statistics"]["Mtf00Gap"]["material_count"] == 3
    assert evidence["metric_statistics"]["EepeInEurGap"]["material_count"] == 3
    # 100k + 20k already explains >90% of the MTF material movement.
    assert evidence["metric_statistics"]["Mtf00Gap"]["selected_count"] == 2
    assert evidence["metric_statistics"]["Mtf00Gap"]["selected_coverage_pct"] >= 90
    assert "LE_A" in evidence["impacted_dimensions"]["LegalEntity"]
    changed_fields = {row["field"] for row in evidence["ref_test_change_patterns"]}
    assert "EffectiveMaturity" in changed_fields
    assert "RiskWeightedExposureFactor" in changed_fields
    context = (out / "agent_context.md").read_text()
    assert "strict |gap| > 10000.0" in context
    assert "Ref/Test fields that changed" in context


def test_backtesting_derives_deal_from_trd_aggregation_and_uses_legal_entity_filter(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[1]
    upstream = tmp_path / "upstream.json"
    upstream.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "evidence_type": "large-result-diff",
                "source": {},
                "summary": {},
                "material_impacts": [],
                "patterns": [],
                "impacted_dimensions": {
                    "LegalEntity": ["LE_A"],
                    # This upstream aggregation MUST NOT be used as an exact filter because
                    # backtesting has /TRD:<deal> aggregation levels instead.
                    "AggregationLevel": ["/LegalEntity:1/Master:999"],
                },
                "timings": [],
                "warnings": [],
            }
        ),
        encoding="utf-8",
    )
    bt = tmp_path / "backtesting-real.csv"
    _write(
        bt,
        "LegalEntity,AggregationLevel,Mtf00 Gap,EepeInEur Gap\n"
        "LE_A,/LegalEntity:1/TRD:DEAL_001,90000,120000\n"
        "LE_A,/LegalEntity:1/TRD:DEAL_002,20000,30000\n"
        "LE_A,/LegalEntity:1/TRD:DEAL_003,5000,5000\n"
        "LE_B,/LegalEntity:2/TRD:DEAL_999,999999,999999\n",
    )
    out = tmp_path / "bt-real-out"
    subprocess.run(
        [
            sys.executable,
            str(repo / "skills/backtesting-drilldown/scripts/drilldown.py"),
            "--input", str(bt),
            "--evidence", str(upstream),
            "--output", str(out),
            "--backend", "streaming",
        ],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        env={**__import__("os").environ, "PYTHONPATH": str(repo)},
    )
    evidence = json.loads((out / "backtesting_summary.json").read_text())
    assert evidence["summary"]["rows_matching_upstream_dimensions"] == 3
    deals = {row["identity"].get("DealId") for row in evidence["material_impacts"]}
    assert "DEAL_001" in deals
    assert "DEAL_002" in deals
    assert "DEAL_999" not in deals
    assert evidence["concentration"]["Mtf00Gap"]["selected_coverage_pct"] >= 90
    assert any("derived" in warning.lower() and "aggregationlevel" in warning.lower() for warning in evidence["warnings"])


def test_mtf00_coverage_is_currency_aware(tmp_path: Path) -> None:
    """MTF00 native-currency amounts must not be Pareto-ranked by summing EUR and USD together."""
    repo = Path(__file__).resolve().parents[1]
    source = tmp_path / "multi-currency.csv"
    _write(
        source,
        "LegalEntity,AggregationLevel,Currency (Test),Mtf00 Gap,EepeInEur Gap\n"
        "LE_EUR,/LegalEntity:1/Master:1,EUR,90000,0\n"
        "LE_EUR,/LegalEntity:1/Master:2,EUR,20000,0\n"
        "LE_USD,/LegalEntity:2/Master:3,USD,1000000,0\n"
        "LE_USD,/LegalEntity:2/Master:4,USD,20000,0\n",
    )
    out = tmp_path / "currency-aware"
    subprocess.run(
        [
            sys.executable,
            str(repo / "skills/analyze-large-result-diff/scripts/analyze.py"),
            "--profile", "cvar",
            "--input", str(source),
            "--output", str(out),
            "--backend", "streaming",
        ],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        env={**__import__("os").environ, "PYTHONPATH": str(repo)},
    )
    evidence = json.loads((out / "summary.json").read_text())
    mtf = evidence["metric_statistics"]["Mtf00Gap"]
    assert mtf["selection_mode"] == "threshold+coverage-by-group"
    assert mtf["coverage_group_by"] == "Currency (Test)"
    assert mtf["coverage_groups"]["EUR"]["selected_count"] == 2
    assert mtf["coverage_groups"]["USD"]["selected_count"] == 1
    assert mtf["selected_count"] == 3
    assert mtf["top1_share_pct"] is None  # cross-currency concentration is intentionally not fabricated
    context = (out / "agent_context.md").read_text()
    assert "`EUR`" in context and "`USD`" in context


def test_backtesting_selected_deal_diagnostics_use_real_compare_columns(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[1]
    upstream = tmp_path / "upstream.json"
    upstream.write_text(
        json.dumps({
            "schema_version": "1.0",
            "evidence_type": "large-result-diff",
            "source": {}, "summary": {}, "material_impacts": [], "patterns": [],
            "impacted_dimensions": {"LegalEntity": ["LE_A"]},
            "timings": [], "warnings": [],
        }), encoding="utf-8"
    )
    bt = tmp_path / "bt-diagnostics.csv"
    _write(
        bt,
        "LegalEntity,AggregationLevel,EffectiveMaturity (Ref),EffectiveMaturity (Test),RiskWeightedExposureFactor (Ref),RiskWeightedExposureFactor (Test),CashFlowType (Result),Currency (Result),Currency (Test),Mtf00 Gap,Mtf00 Ratio,EepeInEur Gap,Rwa Gap,Rwa Ratio\n"
        "LE_A,/LegalEntity:1/TRD:D1,1,2,100,120,TRUE,TRUE,EUR,90000,0.10,120000,5000,0.2\n"
        "LE_A,/LegalEntity:1/TRD:D2,1,1,100,100,FALSE,TRUE,EUR,20000,0.02,30000,100,0.01\n"
        "LE_B,/LegalEntity:2/TRD:D9,1,9,100,999,FALSE,FALSE,USD,999999,1.0,999999,999999,9\n",
    )
    out = tmp_path / "bt-diag-out"
    subprocess.run(
        [
            sys.executable,
            str(repo / "skills/backtesting-drilldown/scripts/drilldown.py"),
            "--input", str(bt),
            "--evidence", str(upstream),
            "--output", str(out),
            "--backend", "streaming",
        ],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        env={**__import__("os").environ, "PYTHONPATH": str(repo)},
    )
    evidence = json.loads((out / "backtesting_summary.json").read_text())
    fields = {row["field"] for row in evidence["ref_test_change_patterns"]}
    assert "EffectiveMaturity" in fields
    assert "RiskWeightedExposureFactor" in fields
    flags = {row["column"] for row in evidence["comparison_flag_failures"]}
    assert "CashFlowType (Result)" in flags
    diagnostics = {row["name"] for row in evidence["secondary_numeric_diagnostics"]}
    assert "RwaGap" in diagnostics
    assert "Mtf00Ratio" in diagnostics


def test_backtesting_mtf_coverage_is_currency_aware(tmp_path):
    from skillhub.runtime.config import load_profile
    from skillhub.runtime.csv_engine import detect_layout, filter_and_rank_deals, resolve_metric_specs

    p = tmp_path / "bt_currency.csv"
    p.write_text(
        "LegalEntity,AggregationLevel,Currency (Test),Mtf00 Gap,EepeInEur Gap\n"
        "LE_A,Book/TRD:D1,EUR,90000,0\n"
        "LE_A,Book/TRD:D2,EUR,20000,0\n"
        "LE_A,Book/TRD:D3,USD,1000000,0\n"
        "LE_A,Book/TRD:D4,USD,20000,0\n",
        encoding="utf-8",
    )
    profile = load_profile("backtesting")
    layout = detect_layout(p)
    metrics, missing = resolve_metric_specs(layout.columns, profile["metrics"])
    assert not missing
    result = filter_and_rank_deals(
        p,
        filters={"LegalEntity": {"LE_A"}},
        deal_columns=[],
        deal_derivation={
            "source_column": "AggregationLevel",
            "regex": r"(?:^|/)TRD:([^/]+)",
            "output_name": "DealId",
            "fallback_to_source": True,
        },
        metrics=metrics,
        delimiter=layout.delimiter,
        top_k=100,
    )
    mtf = result["concentration"]["Mtf00Gap"]
    assert mtf["selection_mode"] == "threshold+coverage-by-group"
    groups = mtf["coverage_groups"]
    assert groups["EUR"]["selected_count"] == 2
    assert groups["USD"]["selected_count"] == 1
    assert mtf["top1_share_pct"] is None


def test_percentage_formatted_numeric_diagnostics_are_parsed():
    from skillhub.runtime.diagnostics import summarize_numeric_columns

    result = summarize_numeric_columns(
        [{"Mtf00 Ratio": "0.25%"}, {"Mtf00 Ratio": "(0.50%)"}],
        [{"name": "Mtf00Ratio", "aliases": ["Mtf00 Ratio"]}],
    )
    assert result[0]["valid"] == 2
    assert result[0]["max_abs"] == 0.005


def _write_three_sheet_workbook(path, details, non_ref, non_test):
    from openpyxl import Workbook
    wb = Workbook()
    wb.remove(wb.active)
    for name, rows in [("Details", details), ("Non Ref", non_ref), ("Non Test", non_test)]:
        ws = wb.create_sheet(name)
        for row in rows:
            ws.append(row)
    wb.save(path)


def test_xlsx_three_sheet_result_semantics_and_side_only_gaps(tmp_path):
    import os, subprocess, sys, json
    from pathlib import Path
    repo = Path(__file__).resolve().parents[1]
    wb = tmp_path / "CcrMetrics.xlsx"
    header = ["LegalEntity","AggregationLevel","Currency (Ref)","Currency (Test)","Mtf00 (Ref)","Mtf00 (Test)","EepeInEur (Ref)","EepeInEur (Test)","Mtf00 Gap","EepeInEur Gap"]
    _write_three_sheet_workbook(
        wb,
        [header, ["LE1","/LegalEntity:LE1/Master:1","EUR","EUR",1000,25000,5000,30000,24000,25000]],
        [header, ["LE2","/LegalEntity:LE2/Master:2","","USD","",50000,"",75000,"",""]],
        [header, ["LE3","/LegalEntity:LE3/Master:3","EUR","",40000,"",60000,"","",""]],
    )
    out = tmp_path / "out-xlsx"
    subprocess.run([
        sys.executable, str(repo / "skills/analyze-large-result-diff/scripts/analyze.py"),
        "--profile","cvar","--input",str(wb),"--output",str(out),"--backend","streaming"
    ], cwd=repo, env={**os.environ,"PYTHONPATH":str(repo)}, check=True, capture_output=True, text=True)
    evidence=json.loads((out/"summary.json").read_text())
    assert evidence["source"]["input_format"] == "xlsx"
    assert evidence["source"]["workbook_sheets"] == {"Details":1,"Non Ref":1,"Non Test":1}
    states=set(evidence["impacted_dimensions"].get("PresenceState", []))
    assert {"matched","test_only","ref_only"}.issubset(states)
    impacts=evidence["material_impacts"]
    vals={(r["metric"], r["identity"].get("AggregationLevel")): r["value"] for r in impacts}
    assert vals[("Mtf00Gap","/LegalEntity:LE2/Master:2")] == 50000
    assert vals[("Mtf00Gap","/LegalEntity:LE3/Master:3")] == -40000
    assert vals[("EepeInEurGap","/LegalEntity:LE2/Master:2")] == 75000
    assert vals[("EepeInEurGap","/LegalEntity:LE3/Master:3")] == -60000


def test_xlsx_backtesting_derives_deals_and_deal_families(tmp_path):
    import os, subprocess, sys, json
    from pathlib import Path
    repo = Path(__file__).resolve().parents[1]
    upstream=tmp_path/"up.json"
    upstream.write_text(json.dumps({
        "schema_version":"1.0","evidence_type":"large-result-diff","source":{},"summary":{},"material_impacts":[],"patterns":[],
        "impacted_dimensions":{"LegalEntity":["LE1"]},"timings":[],"warnings":[]
    }), encoding="utf-8")
    wb=tmp_path/"Backtesting.xlsx"
    header=["LegalEntity","AggregationLevel","Currency (Test)","Mtf00 Gap","EepeInEur Gap"]
    _write_three_sheet_workbook(
        wb,
        [header,["LE1","/LegalEntity:LE1/TRD:ELI-123","EUR",50000,70000],["LE1","/LegalEntity:LE1/TRD:123456","EUR",30000,40000],["LE1","/LegalEntity:LE1/TRD:IRD-9","EUR",20000,30000]],
        [header], [header]
    )
    out=tmp_path/"bt"
    subprocess.run([sys.executable,str(repo/"skills/backtesting-drilldown/scripts/drilldown.py"),"--input",str(wb),"--evidence",str(upstream),"--output",str(out),"--backend","streaming"],cwd=repo,env={**os.environ,"PYTHONPATH":str(repo)},check=True,capture_output=True,text=True)
    evidence=json.loads((out/"backtesting_summary.json").read_text())
    families={(r["metric"],r["deal_family"]):r["selected_deals"] for r in evidence["deal_family_patterns"]}
    assert families[("Mtf00Gap","equity")] >= 1
    assert families[("Mtf00Gap","equity_dps")] >= 1
    assert families[("Mtf00Gap","fic")] >= 1
