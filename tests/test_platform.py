from pathlib import Path
import json
from skillhub.exporter import export_skill
from skillhub.installer import install_pack, install_skill, sync_installed
from skillhub.registry import build_registry
from skillhub.site import prepare_site_sources
from skillhub.utils import find_repo_root
from skillhub.validation import validate_repo

ROOT=Path(__file__).resolve().parents[1]

def test_repo_validates():
    report=validate_repo(ROOT)
    assert report.ok, [m.__dict__ for m in report.messages]

def test_registry_has_three_skills(tmp_path):
    data=build_registry(ROOT,tmp_path/'registry.json')
    assert {s['id'] for s in data['skills']} == {'release-pr-forensics','compare-result-snapshots','investigate-metric-jump','analyze-large-result-diff','backtesting-drilldown','prepare-ccr-release-evidence'}

def test_site_sources_generate():
    data=prepare_site_sources(ROOT)
    assert len(data['skills']) == 6
    assert (ROOT/'docs'/'marketplace'/'index.md').exists()
    assert 'Release PR Forensics' in (ROOT/'docs'/'marketplace'/'index.md').read_text(encoding='utf-8')
    assert (ROOT/'docs'/'marketplace'/'skills'/'release-pr-forensics'/'index.md').exists()

def test_personal_install_and_pack(tmp_path):
    p=install_skill(ROOT,'release-pr-forensics',tmp_path)
    assert (p/'SKILL.md').exists()
    targets=install_pack(ROOT,'release-investigation',tmp_path/'pack')
    assert len(targets)==3
    assert all((p/'SKILL.md').exists() for p in targets)

def test_compact_export(tmp_path):
    result=export_skill(ROOT,'release-pr-forensics',tmp_path/'context.md',budget=2500)
    text=(tmp_path/'context.md').read_text(encoding='utf-8')
    assert 'release-pr-forensics' in text
    assert 'SKILL.md' in result['included']
    assert result['estimated_tokens'] >= 1


def test_cli_can_resolve_hub_outside_clone(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    assert find_repo_root() == ROOT

def test_sync_installed_skills(tmp_path):
    install_skill(ROOT, 'release-pr-forensics', tmp_path)
    targets = sync_installed(ROOT, tmp_path)
    assert [p.name for p in targets] == ['release-pr-forensics']

def test_stack_installs_skills_and_agent(tmp_path):
    from skillhub.installer import install_stack
    result=install_stack(ROOT,'ccr-release-validation',tmp_path/'skills',tmp_path/'agents')
    assert {p.name for p in result['skills']} == {'release-pr-forensics','analyze-large-result-diff','backtesting-drilldown','prepare-ccr-release-evidence'}
    assert (tmp_path/'agents'/'ccr-cvar-release-validator.agent.md').exists()
    assert (tmp_path/'agents'/'ccr-gcvar-release-validator.agent.md').exists()
    assert (tmp_path/'agents'/'ccr-release-validation-synthesizer.agent.md').exists()


def test_release_skill_has_default_runner():
    from skillhub.runner import resolve_entrypoint
    path=resolve_entrypoint(ROOT,'release-pr-forensics','default')
    assert path.name=='investigate.py'

def test_skill_dependency_tree_install(tmp_path):
    from skillhub.installer import install_skill_tree
    paths=install_skill_tree(ROOT,'investigate-metric-jump',tmp_path)
    assert {p.name for p in paths} == {'release-pr-forensics','compare-result-snapshots','investigate-metric-jump'}
