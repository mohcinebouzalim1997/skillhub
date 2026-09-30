from __future__ import annotations

import importlib.util
import os
import shutil
from pathlib import Path
from typing import Any

from .catalog import get_skill, iter_skills
from .utils import SkillHubError, copytree_atomic, load_yaml, parse_frontmatter


def default_personal_skill_dir() -> Path:
    return Path(os.environ.get("COPILOT_SKILLS_DIR", "~/.copilot/skills")).expanduser()


def default_personal_agent_dir() -> Path:
    return Path(os.environ.get("COPILOT_AGENTS_DIR", "~/.copilot/agents")).expanduser()


def install_skill(root: Path, skill_id: str, destination: Path | None = None, force: bool = False) -> Path:
    try:
        skill = get_skill(root, skill_id)
    except KeyError as exc:
        raise SkillHubError(f"Unknown skill: {skill_id}") from exc
    target = (destination or default_personal_skill_dir()).expanduser() / skill_id
    copytree_atomic(skill.path, target, force=force)
    return target


def uninstall_skill(skill_id: str, destination: Path | None = None) -> Path:
    target = (destination or default_personal_skill_dir()).expanduser() / skill_id
    if not target.exists():
        raise SkillHubError(f"Skill is not installed at {target}")
    shutil.rmtree(target)
    return target


def _agent_source(root: Path, agent_id: str) -> Path:
    for suffix in (".agent.md", ".md"):
        path = root / "agents" / f"{agent_id}{suffix}"
        if path.exists():
            return path
    raise SkillHubError(f"Unknown agent: {agent_id}")


def install_agent(root: Path, agent_id: str, destination: Path | None = None, force: bool = False) -> Path:
    source = _agent_source(root, agent_id)
    target_dir = (destination or default_personal_agent_dir()).expanduser()
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{agent_id}.agent.md"
    if target.exists() and not force:
        raise SkillHubError(f"Agent already exists: {target}. Use --force to replace it.")
    tmp = target.with_suffix(target.suffix + ".skillhub-tmp")
    shutil.copy2(source, tmp)
    os.replace(tmp, target)
    return target


def uninstall_agent(agent_id: str, destination: Path | None = None) -> Path:
    target = (destination or default_personal_agent_dir()).expanduser() / f"{agent_id}.agent.md"
    if not target.exists():
        raise SkillHubError(f"Agent is not installed at {target}")
    target.unlink()
    return target


def install_pack(root: Path, pack_id: str, destination: Path | None = None, force: bool = False) -> list[Path]:
    pack_path = root / "packs" / f"{pack_id}.yaml"
    if not pack_path.exists():
        raise SkillHubError(f"Unknown pack: {pack_id}")
    ids = load_yaml(pack_path).get("skills") or []
    if not isinstance(ids, list) or not ids:
        raise SkillHubError(f"Pack {pack_id} contains no skills")
    return [install_skill(root, str(skill_id), destination, force) for skill_id in ids]


def install_stack(
    root: Path,
    stack_id: str,
    skill_destination: Path | None = None,
    agent_destination: Path | None = None,
    force: bool = False,
) -> dict[str, list[Path]]:
    path = root / "stacks" / f"{stack_id}.yaml"
    if not path.exists():
        raise SkillHubError(f"Unknown stack: {stack_id}")
    data = load_yaml(path)
    skills = [install_skill(root, str(sid), skill_destination, force) for sid in data.get("skills") or []]
    agents = [install_agent(root, str(aid), agent_destination, force) for aid in data.get("agents") or []]
    return {"skills": skills, "agents": agents}



def install_skill_tree(root: Path, skill_id: str, destination: Path | None = None, force: bool = False) -> list[Path]:
    """Install a skill and its declared skill dependencies, dependencies first."""
    installed: list[Path] = []
    visiting: set[str] = set()
    done: set[str] = set()

    def visit(current: str) -> None:
        if current in done:
            return
        if current in visiting:
            raise SkillHubError(f"Cyclic skill dependency involving {current}")
        visiting.add(current)
        try:
            skill = get_skill(root, current)
        except KeyError as exc:
            raise SkillHubError(f"Unknown skill dependency: {current}") from exc
        deps = skill.metadata.get("dependencies") or {}
        for dependency in deps.get("skills") or []:
            visit(str(dependency))
        target = (destination or default_personal_skill_dir()).expanduser() / current
        # Dependency installs should be idempotent when the same version is already present.
        if target.exists() and not force:
            metadata = target / "skillhub.yaml"
            current_version = None
            if metadata.exists():
                try:
                    current_version = str(load_yaml(metadata).get("version"))
                except SkillHubError:
                    current_version = None
            available_version = str(skill.metadata.get("version"))
            if current_version == available_version:
                installed.append(target)
            else:
                raise SkillHubError(f"Destination already exists with another version: {target}. Use --force/update.")
        else:
            installed.append(install_skill(root, current, destination, force))
        visiting.remove(current)
        done.add(current)

    visit(skill_id)
    return installed


def install_python_dependencies(root: Path, skill_id: str) -> dict[str, Any]:
    """Explicitly install declared Python packages. External commands are never auto-installed."""
    import subprocess, sys
    try:
        skill = get_skill(root, skill_id)
    except KeyError as exc:
        raise SkillHubError(f"Unknown skill: {skill_id}") from exc
    deps = skill.metadata.get("dependencies") or {}
    packages = [str(v) for v in deps.get("python") or []]
    if packages:
        proc = subprocess.run([sys.executable, "-m", "pip", "install", *packages], check=False)
        if proc.returncode:
            raise SkillHubError(f"pip dependency installation failed with exit code {proc.returncode}")
    commands = [str(v) for v in deps.get("commands") or []]
    missing_commands = [name for name in commands if shutil.which(name) is None]
    return {"python_installed": packages, "missing_external_commands": missing_commands}

def installed_skill_versions(destination: Path | None = None) -> dict[str, str]:
    destination = (destination or default_personal_skill_dir()).expanduser()
    result: dict[str, str] = {}
    if not destination.exists():
        return result
    for child in destination.iterdir():
        metadata = child / "skillhub.yaml"
        if not child.is_dir() or not metadata.exists():
            continue
        try:
            data = load_yaml(metadata)
        except SkillHubError:
            continue
        skill_id = str(data.get("id") or child.name)
        result[skill_id] = str(data.get("version") or "unknown")
    return result


def installed_agents(destination: Path | None = None) -> set[str]:
    directory = (destination or default_personal_agent_dir()).expanduser()
    if not directory.exists():
        return set()
    return {p.name.removesuffix(".agent.md").removesuffix(".md") for p in directory.glob("*.md")}


def sync_installed(root: Path, destination: Path | None = None) -> list[Path]:
    destination = (destination or default_personal_skill_dir()).expanduser()
    installed = installed_skill_versions(destination)
    available = {skill.skill_id for skill in iter_skills(root)}
    return [
        install_skill(root, skill_id, destination=destination, force=True)
        for skill_id in sorted(installed)
        if skill_id in available
    ]


def dependency_status(root: Path, skill_id: str) -> dict[str, Any]:
    try:
        skill = get_skill(root, skill_id)
    except KeyError as exc:
        raise SkillHubError(f"Unknown skill: {skill_id}") from exc
    deps = skill.metadata.get("dependencies") or {}
    command_rows = []
    for command in deps.get("commands") or []:
        command_rows.append({"name": str(command), "available": shutil.which(str(command)) is not None})
    python_rows = []
    for package in deps.get("python") or []:
        module = str(package).split("[")[0].split("=")[0].split(">")[0].split("<")[0].strip().replace("-", "_")
        python_rows.append({"name": str(package), "available": importlib.util.find_spec(module) is not None})
    recommended = skill.metadata.get("recommended_dependencies") or {}
    recommended_python = []
    for package in recommended.get("python") or []:
        module = str(package).split("[")[0].split("=")[0].split(">")[0].split("<")[0].strip().replace("-", "_")
        recommended_python.append({"name": str(package), "available": importlib.util.find_spec(module) is not None})
    return {
        "commands": command_rows,
        "python": python_rows,
        "recommended_python": recommended_python,
        "ok": all(r["available"] for r in command_rows + python_rows),
    }


def available_agents(root: Path) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for path in sorted((root / "agents").glob("*.md")):
        meta, _ = parse_frontmatter(path)
        agent_id = path.name.removesuffix(".agent.md").removesuffix(".md")
        result[agent_id] = {"name": str(meta.get("name") or agent_id), "description": str(meta.get("description") or "")}
    return result
