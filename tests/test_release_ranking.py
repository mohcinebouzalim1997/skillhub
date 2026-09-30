from __future__ import annotations
import importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/'skills'/'release-pr-forensics'/'scripts'/'rank_candidates.py'

def load():
    spec=importlib.util.spec_from_file_location('rank_candidates',SCRIPT); mod=importlib.util.module_from_spec(spec); assert spec.loader; spec.loader.exec_module(mod); return mod

def test_relevant_path_ranks_first():
    m=load(); index={'prs':[{'number':10,'title':'Logging cleanup','body':'','labels':['observability'],'files':[{'path':'src/Logging/Log.cs'}],'changed_files':1,'additions':5,'deletions':2},{'number':11,'title':'Optimize first passage','body':'MTF boundary calculation','labels':['quant'],'files':[{'path':'src/SmartXVA/MTF/FirstPassage.cs'}],'changed_files':1,'additions':9,'deletions':4}],'direct_commits':[]}
    result=m.rank(index,'MTF first passage window boundary',['MTF'],10)
    assert result['candidates'][0]['pr']==11
    assert 'not probability of causation' in result['note']
