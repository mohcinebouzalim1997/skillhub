from __future__ import annotations
import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/'skills'/'investigate-metric-jump'/'scripts'/'build_investigation_brief.py'
def load():
    spec=importlib.util.spec_from_file_location('brief',SCRIPT); mod=importlib.util.module_from_spec(spec); assert spec.loader; spec.loader.exec_module(mod); return mod

def test_brief_keeps_causality_warning():
    m=load(); comp={'metrics':[{'metric':'EEPE','before_sum':100,'after_sum':135,'absolute_delta':35,'relative_delta_pct':35.0}],'row_analysis':{'top_movers':[]}}; c={'candidates':[{'pr':42,'title':'Boundary change','relevance_score':15,'signals':['path match']}]}; text=m.build(comp,c,'EEPE'); assert 'not a causal probability' in text; assert '35' in text
