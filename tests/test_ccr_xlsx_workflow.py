from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from openpyxl import Workbook


def _write_result(path: Path, rows):
    wb=Workbook(); wb.remove(wb.active)
    header=["LegalEntity","AggregationLevel","EffectiveMaturity (Ref)","RiskWeightedExposureFactor (Ref)","Mtf00 (Ref)","Currency (Ref)","EepeInEur (Ref)","EffectiveMaturity (Test)","RiskWeightedExposureFactor (Test)","Mtf00 (Test)","Currency (Test)","EepeInEur (Test)","Mtf00 Gap","EepeInEur Gap"]
    for name in ["Details","Non Ref","Non Test"]:
        ws=wb.create_sheet(name); ws.append(header)
        for sheet,row in rows:
            if sheet==name: ws.append(row)
    wb.save(path)


def _write_errors(path: Path, rows):
    wb=Workbook(); wb.remove(wb.active)
    header=["GroupingCriterionId","NettingSetId","ErrorType","AnalysisIndex","TradeId","Message (Ref)","Message (Test)","Message (Result)"]
    for name in ["Details","Non Ref","Non Test"]:
        ws=wb.create_sheet(name); ws.append(header)
        for sheet,row in rows:
            if sheet==name: ws.append(row)
    wb.save(path)


def test_full_xlsx_workflow_with_errors_and_gcvar_reuse(tmp_path: Path):
    repo=Path(__file__).resolve().parents[1]
    cvar=tmp_path/"CcrMetrics.xlsx"
    gcvar=tmp_path/"CcrMetrics_Gcvar.xlsx"
    result_rows=[
        ("Details",["LE1","/LegalEntity:LE1/Master:1",1,100,10000,"EUR",20000,2,130,90000,"EUR",140000,80000,120000]),
        ("Non Ref",["LE2","/LegalEntity:LE2/Master:2","","","","","","", "",50000,"USD",70000,"",""]),
    ]
    _write_result(cvar,result_rows); _write_result(gcvar,result_rows)

    bt=tmp_path/"Backtesting.xlsx"
    bt_rows=[
        ("Details",["LE1","/LegalEntity:LE1/TRD:ELI-100",1,100,1000,"EUR",5000,2,120,51000,"EUR",75000,50000,70000]),
        ("Details",["LE1","/LegalEntity:LE1/TRD:IRD-200",1,100,1000,"EUR",5000,1,100,21000,"EUR",35000,20000,30000]),
        ("Details",["LE1","/LegalEntity:LE1/TRD:123456",1,100,1000,"EUR",5000,1,100,16000,"EUR",25000,15000,20000]),
    ]
    _write_result(bt,bt_rows)

    err=tmp_path/"ErrorByTrade.xlsx"
    _write_errors(err,[
        ("Non Ref",[1,"/LegalEntity:LE1/Master:1","Pricing",0,"ELI-100","","CCR product mtms failed for ELI-100",""]),
        ("Details",[1,"/LegalEntity:LE1/Master:1","Pricing",0,"IRD-200","Nothing has been found to price the netting set","Nothing has been found to price the netting set",True]),
    ])
    bt_err=tmp_path/"BacktestingErrorByTrade.xlsx"
    _write_errors(bt_err,[
        ("Non Ref",[1,"/LegalEntity:LE1/TRD:ELI-100","Pricing",0,"ELI-100","","CCR product mtms failed for ELI-100",""]),
    ])

    out=tmp_path/"work"
    proc=subprocess.run([
        sys.executable,str(repo/"skills/prepare-ccr-release-evidence/scripts/prepare.py"),
        "--cvar",str(cvar),"--cvar-backtesting",str(bt),"--cvar-errors",str(err),"--cvar-backtesting-errors",str(bt_err),
        "--gcvar",str(gcvar),"--gcvar-backtesting",str(bt),"--gcvar-errors",str(err),"--gcvar-backtesting-errors",str(bt_err),
        "--prod-ref","release/26.9","--candidate-ref","release/26.10","--output",str(out),"--backend","streaming"
    ],cwd=repo,env={**os.environ,"PYTHONPATH":str(repo),"SKILLHUB_ROOT":str(repo)},capture_output=True,text=True,check=True)
    manifest=json.loads((out/"workflow_manifest.json").read_text())
    assert "backtesting" in manifest["branches"]["cvar"]
    assert "errors" in manifest["branches"]["cvar"]
    assert "backtesting_errors" in manifest["branches"]["cvar"]
    result_errors=json.loads((out/"cvar-errors/error_summary.json").read_text())
    backtesting_errors=json.loads((out/"cvar-backtesting-errors/error_summary.json").read_text())
    assert "Mtf00Gap" in result_errors["metric_linkage"]
    assert "EepeInEurGap" in result_errors["metric_linkage"]
    assert backtesting_errors["metric_linkage"]["Mtf00Gap"]["asymmetric_error_rows"] >= 1
    assert manifest["branches"]["gcvar"]["cvar_similarity"]["same_issue_likely"] is True
    assert "deep_drilldown_skipped" in manifest["branches"]["gcvar"]
    routing=json.loads((out/"root_cause_routing.json").read_text())
    assert routing["cvar_mtf00_eepe"]["classification"] in {"strong_mtf00_overlap","partial_mtf00_overlap","weak_or_no_mtf00_overlap"}
    ctx=(out/"workflow_context.md").read_text()
    assert "CVAR — investigate MTF00 first" in ctx
    assert "then EEPE" in ctx
    assert "mtm_failed" in ctx
    assert "GCVAR" in ctx and "Deep GCVAR drilldown skipped" in ctx
