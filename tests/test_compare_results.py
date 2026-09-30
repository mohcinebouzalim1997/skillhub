from __future__ import annotations
import importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/'skills'/'compare-result-snapshots'/'scripts'/'compare_results.py'

def load():
    spec=importlib.util.spec_from_file_location('compare_results',SCRIPT); mod=importlib.util.module_from_spec(spec); assert spec.loader; spec.loader.exec_module(mod); return mod

def test_compare_detects_jump():
    m=load(); result=m.compare(ROOT/'examples/demo/before.csv',ROOT/'examples/demo/after.csv',['counterparty','date'],['EEPE','EPE'],10)
    eepe=next(x for x in result['metrics'] if x['metric']=='EEPE')
    assert eepe['absolute_delta']==125.0
    movers=result['row_analysis']['top_movers']
    assert movers[0]['key']['counterparty']=='B'
    assert movers[0]['key']['date']=='2026-07-22'
