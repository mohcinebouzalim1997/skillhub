from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from .catalog import get_skill
from .utils import SkillHubError


def _command_for(path: Path, args: list[str]) -> list[str]:
    suffix = path.suffix.lower()
    if suffix == ".py":
        return [sys.executable, str(path), *args]
    if suffix == ".ps1":
        host = shutil.which("pwsh") or shutil.which("powershell")
        if not host:
            raise SkillHubError("PowerShell entrypoint requires pwsh or powershell on PATH")
        return [host, "-NoProfile", "-File", str(path), *args]
    if suffix in {".bat", ".cmd"}:
        if os.name != "nt":
            raise SkillHubError(".bat/.cmd entrypoints can only run on Windows")
        return ["cmd.exe", "/d", "/c", str(path), *args]
    if suffix == ".sh":
        host = shutil.which("bash")
        if not host:
            raise SkillHubError("Shell entrypoint requires bash on PATH")
        return [host, str(path), *args]
    if os.access(path, os.X_OK):
        return [str(path), *args]
    raise SkillHubError(f"Unsupported/non-executable entrypoint: {path}")


def resolve_entrypoint(root: Path, skill_id: str, name: str = "default") -> Path:
    try:
        skill = get_skill(root, skill_id)
    except KeyError as exc:
        raise SkillHubError(f"Unknown skill: {skill_id}") from exc
    entrypoints = skill.metadata.get("entrypoints") or {}
    if not isinstance(entrypoints, dict) or name not in entrypoints:
        choices = ", ".join(sorted(entrypoints)) or "none"
        raise SkillHubError(f"Skill '{skill_id}' has no entrypoint '{name}'. Available: {choices}")
    relative = Path(str(entrypoints[name]))
    if relative.is_absolute() or ".." in relative.parts:
        raise SkillHubError("Entrypoint must be a path inside the skill package")
    path = (skill.path / relative).resolve()
    try:
        path.relative_to(skill.path.resolve())
    except ValueError as exc:
        raise SkillHubError("Entrypoint escapes the skill package") from exc
    if not path.is_file():
        raise SkillHubError(f"Entrypoint does not exist: {relative}")
    return path


def run_skill(root: Path, skill_id: str, name: str, args: list[str]) -> int:
    path = resolve_entrypoint(root, skill_id, name)
    cleaned = args[1:] if args and args[0] == "--" else args
    command = _command_for(path, cleaned)
    # Preserve the caller's working directory so analysis outputs land where the user is working.
    # Also expose the hub package to skill scripts when running from an editable clone. Installed
    # workstations already have the package, but this keeps development and CI deterministic.
    env = os.environ.copy()
    current_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(root) + (os.pathsep + current_pythonpath if current_pythonpath else "")
    env["SKILLHUB_ROOT"] = str(root)
    return subprocess.call(command, cwd=Path.cwd(), env=env)
