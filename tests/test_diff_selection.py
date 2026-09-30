from __future__ import annotations
import importlib.util, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SCRIPTS=ROOT/'skills'/'release-pr-forensics'/'scripts'
SCRIPT=SCRIPTS/'inspect_pr.py'

def load():
    sys.path.insert(0,str(SCRIPTS))
    try:
        spec=importlib.util.spec_from_file_location('inspect_pr_test',SCRIPT); mod=importlib.util.module_from_spec(spec); assert spec.loader; sys.modules[spec.name]=mod; spec.loader.exec_module(mod); return mod
    finally:
        sys.path.remove(str(SCRIPTS))

def test_smart_diff_prefers_relevant_production_patch():
    m=load()
    files=[
      {'filename':'docs/readme.md','patch':'+ words','changes':10},
      {'filename':'tests/MTFTests.cs','patch':'+ test first passage','changes':20},
      {'filename':'src/SmartXVA/MTF/FirstPassage.cs','patch':'- if (d > end)\n+ if (d >= end)','changes':2},
      {'filename':'package-lock.json','patch':'+ huge lock','changes':500},
    ]
    plan=m.select_patches(files,'MTF first passage boundary',['MTF'],max_patch_chars=10000)
    assert plan['selected'][0]['filename']=='src/SmartXVA/MTF/FirstPassage.cs'
    assert any(x['filename']=='docs/readme.md' for x in plan['omitted'])
    assert any(x['filename']=='package-lock.json' for x in plan['omitted'])

def test_smart_diff_respects_budget_even_for_first_huge_patch():
    m=load()
    files=[{'filename':'src/core.py','patch':'+' + ('x'*20000),'changes':20000}]
    plan=m.select_patches(files,'core',[],max_patch_chars=5000)
    assert plan['selected_patch_chars']==5000
    assert plan['selected'][0]['patch_truncated'] is True
    assert plan['full_diff_recommended'] is True
