from pathlib import Path

from skillhub.registry import build_registry
from skillhub.validation import validate_repo


def test_ccr_workflow_is_first_class() -> None:
    root = Path(__file__).resolve().parents[1]
    registry = build_registry(root)
    workflows = {row["id"]: row for row in registry["workflows"]}
    workflow = workflows["ccr-release-validation"]
    agents = {row["id"] for row in workflow["agents"]}
    assert "ccr-cvar-release-validator" in agents
    assert "ccr-gcvar-release-validator" in agents
    assert "release-pr-forensics" in workflow["skills"]
    assert validate_repo(root).ok


def test_release_forensics_is_not_an_agent() -> None:
    root = Path(__file__).resolve().parents[1]
    assert not (root / "agents/release-forensics.agent.md").exists()
    assert (root / "skills/release-pr-forensics/SKILL.md").exists()
