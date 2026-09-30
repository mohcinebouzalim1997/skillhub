from __future__ import annotations
from pathlib import Path
import yaml

from skillhub.bridge import _status
from skillhub.installer import install_skill

ROOT=Path(__file__).resolve().parents[1]


def test_local_status_detects_installed_and_update(monkeypatch,tmp_path):
    skill_dir=tmp_path/'skills'; agent_dir=tmp_path/'agents'
    monkeypatch.setenv('COPILOT_SKILLS_DIR',str(skill_dir))
    monkeypatch.setenv('COPILOT_AGENTS_DIR',str(agent_dir))
    install_skill(ROOT,'compare-result-snapshots',skill_dir)
    state=_status(ROOT)
    assert state['skills']['compare-result-snapshots']['state']=='current'
    meta=skill_dir/'compare-result-snapshots'/'skillhub.yaml'
    data=yaml.safe_load(meta.read_text()); data['version']='0.0.1'; meta.write_text(yaml.safe_dump(data,sort_keys=False))
    state=_status(ROOT)
    assert state['skills']['compare-result-snapshots']['state']=='update-available'
