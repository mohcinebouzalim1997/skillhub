from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .catalog import iter_skills
from .installer import available_agents
from .utils import SkillHubError, load_yaml, parse_frontmatter

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
POSSIBLE_SECRET_PATTERNS = [
    re.compile(r"(?i)-----BEGIN (?:RSA|EC|OPENSSH|DSA) PRIVATE KEY-----"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
]
VALID_VERIFICATION = {"experimental", "community", "reviewed", "verified", "approved"}


@dataclass
class ValidationMessage:
    level: str
    location: str
    message: str


@dataclass
class ValidationReport:
    messages: list[ValidationMessage]

    @property
    def errors(self) -> list[ValidationMessage]:
        return [m for m in self.messages if m.level == "error"]

    @property
    def warnings(self) -> list[ValidationMessage]:
        return [m for m in self.messages if m.level == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors


def _error(messages: list[ValidationMessage], loc: str, message: str) -> None:
    messages.append(ValidationMessage("error", loc, message))


def _warning(messages: list[ValidationMessage], loc: str, message: str) -> None:
    messages.append(ValidationMessage("warning", loc, message))


def validate_repo(root: Path) -> ValidationReport:
    messages: list[ValidationMessage] = []
    config_path = root / "skillhub.config.yaml"
    if not config_path.exists():
        _error(messages, str(config_path), "Missing repository config")
    elif int(load_yaml(config_path).get("schema_version", 0)) != 1:
        _error(messages, str(config_path), "schema_version must be 1")

    seen_names: set[str] = set()
    skills = list(iter_skills(root))
    skill_ids = {skill.skill_id for skill in skills}
    if not skills:
        _warning(messages, "skills/", "No skills found")

    for skill in skills:
        loc = f"skills/{skill.skill_id}"
        name = str(skill.frontmatter.get("name", ""))
        description = str(skill.frontmatter.get("description", "")).strip()
        if not name:
            _error(messages, loc, "SKILL.md requires frontmatter.name")
        elif not NAME_RE.fullmatch(name):
            _error(messages, loc, "name must be <=64 chars and contain lowercase letters, digits, hyphens")
        elif name != skill.skill_id:
            _error(messages, loc, f"name '{name}' must match directory '{skill.skill_id}'")
        if name in seen_names:
            _error(messages, loc, f"Duplicate skill name: {name}")
        seen_names.add(name)
        if not description:
            _error(messages, loc, "SKILL.md requires description")
        elif len(description) > 1024:
            _error(messages, loc, "description exceeds 1024 characters")

        version = str(skill.metadata.get("version", ""))
        if not SEMVER_RE.fullmatch(version):
            _error(messages, loc, "skillhub.yaml version must be semantic x.y.z")
        for field in ("title", "category", "owner"):
            if not skill.metadata.get(field):
                _error(messages, loc, f"skillhub.yaml requires {field}")
        if not isinstance(skill.metadata.get("tags", []), list):
            _error(messages, loc, "tags must be a YAML list")

        verification = skill.metadata.get("verification") or {}
        level = str(verification.get("level") or skill.metadata.get("status", "experimental"))
        if level not in VALID_VERIFICATION:
            _error(messages, loc, f"verification.level must be one of {sorted(VALID_VERIFICATION)}")
        if level in {"verified", "approved"} and not verification.get("reviewed_by"):
            _warning(messages, loc, "Verified/approved skill should declare verification.reviewed_by")
        if level in {"verified", "approved"} and not (skill.path / "CHANGELOG.md").exists():
            _warning(messages, loc, "Verified/approved skill should include CHANGELOG.md")

        entrypoints = skill.metadata.get("entrypoints") or {}
        if entrypoints and not isinstance(entrypoints, dict):
            _error(messages, loc, "entrypoints must be a mapping")
        elif isinstance(entrypoints, dict):
            for entry_name, entry_path in entrypoints.items():
                relative = Path(str(entry_path))
                if relative.is_absolute() or ".." in relative.parts or not (skill.path / relative).is_file():
                    _error(messages, loc, f"Invalid entrypoint {entry_name}: {entry_path}")

        deps = skill.metadata.get("dependencies") or {}
        if not isinstance(deps, dict):
            _error(messages, loc, "dependencies must be a mapping")
        else:
            for key in ("commands", "python", "skills"):
                if key in deps and not isinstance(deps[key], list):
                    _error(messages, loc, f"dependencies.{key} must be a YAML list")
            for dependency_skill in deps.get("skills") or []:
                if dependency_skill not in skill_ids:
                    _error(messages, loc, f"Unknown dependent skill: {dependency_skill}")

        if bool(skill.metadata.get("executable", False)):
            scripts_dir = skill.path / "scripts"
            if not scripts_dir.exists() or not any(p.is_file() for p in scripts_dir.glob("*")):
                _error(messages, loc, "executable=true but no files exist under scripts/")
            if not (skill.path / "tests").exists():
                _warning(messages, loc, "Executable skill has no skill-local tests/ directory")
        allowed = skill.frontmatter.get("allowed-tools")
        if allowed == "*" or allowed == ["*"]:
            _error(messages, loc, "allowed-tools '*' is forbidden by SkillHub v0.1 policy")
        for path in skill.path.rglob("*"):
            if not path.is_file() or path.stat().st_size > 2_000_000:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if any(pattern.search(text) for pattern in POSSIBLE_SECRET_PATTERNS):
                _error(messages, str(path.relative_to(root)), "Possible secret/private key detected")

    agent_ids = set(available_agents(root))
    for path in sorted((root / "agents").glob("*.md")):
        loc = str(path.relative_to(root))
        try:
            meta, _ = parse_frontmatter(path)
        except SkillHubError as exc:
            _error(messages, loc, str(exc))
            continue
        if not meta.get("description"):
            _error(messages, loc, "Agent requires frontmatter.description")

    for folder in ("packs", "collections", "stacks", "workflows"):
        seen: set[str] = set()
        for path in sorted((root / folder).glob("*.yaml")):
            loc = str(path.relative_to(root))
            data = load_yaml(path)
            item_id = str(data.get("id") or "")
            if not NAME_RE.fullmatch(item_id):
                _error(messages, loc, "id must be lowercase letters/digits/hyphens")
            if item_id in seen:
                _error(messages, loc, f"Duplicate {folder[:-1]} id: {item_id}")
            seen.add(item_id)
            for sid in data.get("skills") or []:
                if sid not in skill_ids:
                    _error(messages, loc, f"Unknown skill reference: {sid}")
            if folder in {"stacks", "workflows"}:
                for agent_ref in data.get("agents") or []:
                    aid = str(agent_ref.get("id")) if isinstance(agent_ref, dict) else str(agent_ref)
                    if aid and aid not in agent_ids:
                        _error(messages, loc, f"Unknown agent reference: {aid}")
            if folder == "stacks" and data.get("workflow"):
                workflow_path = root / "workflows" / f"{data.get('workflow')}.yaml"
                if not workflow_path.exists():
                    _error(messages, loc, f"Unknown workflow reference: {data.get('workflow')}")

    return ValidationReport(messages)
