from __future__ import annotations
import json, os, subprocess, sys
from pathlib import Path
from openpyxl import Workbook


def _wb(path: Path):
    wb=Workbook(); wb.remove(wb.active)
    header=["GroupingCriterionId","NettingSetId","ErrorType","AnalysisIndex","TradeId","Message (Ref)","Message (Test)","Message (Result)"]
    details=[header,["1","/LegalEntity:LE1/Master:1","Pricing",0,"ELI-1","ok","CCR product mtms failed",False]]
    non_ref=[header,["2","/LegalEntity:LE1/Master:1","Loading",0,"IRD-2","","Dead trade detected during load",""]]
    non_test=[header,["3","/LegalEntity:LE2/Master:2","Pricing",0,"123456","Schedule not found","",""]]
    for name, rows in [("Details",details),("Non Ref",non_ref),("Non Test",non_test)]:
        ws=wb.create_sheet(name)
        for row in rows: ws.append(row)
    wb.save(path)


def test_error_workbook_asymmetry_and_scope(tmp_path: Path):
    repo=Path(__file__).resolve().parents[1]
    upstream=tmp_path/"up.json"
    upstream.write_text(json.dumps({
        "schema_version":"1.0","evidence_type":"backtesting-drilldown","source":{},"summary":{},"material_impacts":[],"patterns":[],
        "impacted_dimensions":{"LegalEntity":["LE1"],"Deal":["ELI-1","IRD-2"]},"timings":[],"warnings":[]
    }), encoding="utf-8")
    xlsx=tmp_path/"ErrorByTrade.xlsx"; _wb(xlsx)
    out=tmp_path/"errors"
    subprocess.run([sys.executable,str(repo/"skills/analyze-ccr-errors/scripts/analyze_errors.py"),"--input",str(xlsx),"--evidence",str(upstream),"--output",str(out)],cwd=repo,env={**os.environ,"PYTHONPATH":str(repo)},check=True,capture_output=True,text=True)
    ev=json.loads((out/"error_summary.json").read_text())
    assert ev["summary"]["asymmetric_error_rows"] == 2
    assert ev["error_state_counts"]["changed_between_ref_and_test"] == 1
    assert ev["error_state_counts"]["introduced_in_test"] == 1
    assert ev["deal_family_counts"]["equity"] == 1
    assert ev["deal_family_counts"]["fic"] == 1
    assert "mtm_failed" in ev["error_category_counts"]
    assert "dead_trade" in ev["error_category_counts"]
