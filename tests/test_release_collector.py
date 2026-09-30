from __future__ import annotations
import importlib.util, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; SCRIPTS=ROOT/'skills'/'release-pr-forensics'/'scripts'; SCRIPT=SCRIPTS/'collect_prs.py'

def load():
    sys.path.insert(0,str(SCRIPTS))
    try:
        spec=importlib.util.spec_from_file_location('collect_prs_test',SCRIPT); mod=importlib.util.module_from_spec(spec); assert spec.loader; sys.modules[spec.name]=mod; spec.loader.exec_module(mod); return mod
    finally:
        sys.path.remove(str(SCRIPTS))

def test_collector_preserves_direct_commits(monkeypatch,tmp_path):
    m=load()
    monkeypatch.setattr(m,'resolve_ref',lambda repo,ref:{'sha':ref})
    monkeypatch.setattr(m,'compare_commits',lambda repo,base,head:{'status':'ahead','ahead_by':2,'behind_by':0,'total_commits':2,'commits':[{'sha':'aaa','commit':{'message':'via PR','author':{'date':'2026-01-01','name':'A'}}},{'sha':'bbb','commit':{'message':'direct change','author':{'date':'2026-01-02','name':'B'}}}],'files':[]})
    monkeypatch.setattr(m,'associated_prs',lambda repo,sha:[{'number':7}] if sha=='aaa' else [])
    monkeypatch.setattr(m,'pr_details',lambda repo,n:{'number':7,'title':'Change algo','body':'','author':{'login':'dev'},'labels':[],'files':[{'path':'src/a.py'}],'commits':[],'changedFiles':1,'additions':2,'deletions':1,'url':'x'})
    out=m.collect('org/repo',tmp_path,base='good',head='bad')
    assert len(out['prs'])==1
    assert out['direct_commits'][0]['sha']=='bbb'
    assert out['scope']['mode']=='range'


def test_release_mode_infers_previous(monkeypatch,tmp_path):
    m=load()
    monkeypatch.setattr(m,'matching_refs',lambda repo,prefix:['refs/heads/release/26.8','refs/heads/release/26.9','refs/heads/release/26.10'] if prefix.startswith('heads/') else [])
    monkeypatch.setattr(m,'resolve_ref',lambda repo,ref:{'sha':ref})
    monkeypatch.setattr(m,'compare_commits',lambda repo,base,head:{'status':'ahead','commits':[],'files':[]})
    out=m.collect('org/repo',tmp_path,release='release/26.10')
    assert out['scope']['base']=='release/26.9'
    assert out['scope']['inferred_base'] is True


def test_date_mode_collects_merged_prs(monkeypatch,tmp_path):
    m=load()
    monkeypatch.setattr(m,'list_merged_prs',lambda repo,start,end,branch:[{'number':9,'title':'Fix metric','body':'','author':{'login':'q'},'labels':[{'name':'quant'}],'files':[{'path':'src/a.cs'}],'commits':[],'changedFiles':1,'additions':2,'deletions':1,'url':'x','mergedAt':'2026-09-20T10:00:00Z'}])
    out=m.collect('org/repo',tmp_path,from_date='2026-09-15',to_date='2026-09-22')
    assert out['scope']['mode']=='dates'
    assert out['prs'][0]['number']==9
