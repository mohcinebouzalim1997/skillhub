from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .catalog import iter_skills
from .installer import available_agents
from .utils import dump_json, load_yaml


def _load_yaml_dir(root: Path, name: str) -> list[dict]:
    rows = []
    for path in sorted((root / name).glob("*.yaml")):
        data = load_yaml(path)
        data["_file"] = path.name
        rows.append(data)
    return rows


def build_registry(root: Path, output: Path | None = None) -> dict:
    config = load_yaml(root / "skillhub.config.yaml")
    skills = [skill.to_registry_entry() for skill in iter_skills(root)]
    categories: dict[str, int] = {}
    for skill in skills:
        category = str(skill["category"])
        categories[category] = categories.get(category, 0) + 1
    registry = {
        "schema_version": 2,
        "skillhub_version": __version__,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "hub": {
            "name": config.get("name", "SkillHub"),
            "description": config.get("description", ""),
            "default_token_budget": config.get("default_token_budget", 6000),
        },
        "categories": categories,
        "skills": skills,
        "packs": _load_yaml_dir(root, "packs"),
        "collections": _load_yaml_dir(root, "collections"),
        "stacks": _load_yaml_dir(root, "stacks"),
        "workflows": _load_yaml_dir(root, "workflows"),
        "agents": [{"id": key, **value} for key, value in available_agents(root).items()],
    }
    dump_json(output or root / "registry" / "registry.json", registry)
    return registry
