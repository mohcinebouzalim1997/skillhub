from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .utils import estimate_tokens, load_yaml, parse_frontmatter, sha256_file


@dataclass(frozen=True)
class SkillRecord:
    skill_id: str
    path: Path
    metadata: dict[str, Any]
    frontmatter: dict[str, Any]
    body: str

    @property
    def title(self) -> str:
        return str(self.metadata.get("title") or self.skill_id.replace("-", " ").title())

    @property
    def description(self) -> str:
        return str(self.frontmatter.get("description") or self.metadata.get("description") or "")

    def quality_score(self) -> int:
        """Transparent completeness score, not a user rating or effectiveness claim."""
        score = 35
        if self.metadata.get("owner") and self.metadata.get("owner") != "unassigned":
            score += 5
        if len(self.description.strip()) >= 80:
            score += 5
        verification = self.metadata.get("verification") or {}
        if str(verification.get("level") or self.metadata.get("status")) == "verified":
            score += 15
        if verification.get("reviewed_by"):
            score += 5
        if (self.path / "tests").exists():
            score += 10
        if (self.path / "references").exists() and any((self.path / "references").glob("*.md")):
            score += 5
        if (self.path / "examples").exists() or self.metadata.get("examples"):
            score += 5
        if (self.path / "CHANGELOG.md").exists():
            score += 5
        if self.metadata.get("dependencies") is not None:
            score += 5
        if bool(self.metadata.get("executable", False)) and (self.path / "scripts").exists():
            score += 5
        return min(100, score)

    def to_registry_entry(self) -> dict[str, Any]:
        files: list[dict[str, Any]] = []
        total_tokens = 0
        for path in sorted(p for p in self.path.rglob("*") if p.is_file()):
            rel = path.relative_to(self.path).as_posix()
            if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
                continue
            data = path.read_text(encoding="utf-8", errors="replace")
            tokens = estimate_tokens(data)
            total_tokens += tokens
            files.append({"path": rel, "bytes": path.stat().st_size, "estimated_tokens": tokens, "sha256": sha256_file(path)})
        verification = self.metadata.get("verification") or {"level": self.metadata.get("status", "experimental")}
        changelog = self.path / "CHANGELOG.md"
        latest_notes = ""
        if changelog.exists():
            text = changelog.read_text(encoding="utf-8", errors="replace")
            chunks = text.split("\n## ", 2)
            latest_notes = ("## " + chunks[1]).strip() if len(chunks) > 1 else text[:2000].strip()
        return {
            "id": self.skill_id,
            "name": self.frontmatter.get("name", self.skill_id),
            "title": self.title,
            "description": self.description,
            "version": str(self.metadata.get("version", "0.0.0")),
            "category": self.metadata.get("category", "uncategorized"),
            "subcategory": self.metadata.get("subcategory"),
            "tags": self.metadata.get("tags", []),
            "aliases": self.metadata.get("aliases", []),
            "status": self.metadata.get("status", "experimental"),
            "verification": verification,
            "quality_score": self.quality_score(),
            "owner": self.metadata.get("owner", "unowned"),
            "runtime": self.metadata.get("runtime", {}),
            "entrypoints": self.metadata.get("entrypoints", {}),
            "permissions": self.metadata.get("permissions", {}),
            "compatibility": self.metadata.get("compatibility", {}),
            "dependencies": self.metadata.get("dependencies", {}),
            "recommended_dependencies": self.metadata.get("recommended_dependencies", {}),
            "exports": self.metadata.get("exports", {}),
            "examples": self.metadata.get("examples", []),
            "latest_changelog": latest_notes,
            "estimated_tokens_full": total_tokens,
            "files": files,
        }


def iter_skills(root: Path) -> Iterable[SkillRecord]:
    skills_root = root / "skills"
    records: list[SkillRecord] = []
    if not skills_root.exists():
        return records
    for skill_md in sorted(skills_root.glob("*/SKILL.md")):
        path = skill_md.parent
        frontmatter, body = parse_frontmatter(skill_md)
        records.append(SkillRecord(path.name, path, load_yaml(path / "skillhub.yaml"), frontmatter, body))
    return records


def get_skill(root: Path, skill_id: str) -> SkillRecord:
    for skill in iter_skills(root):
        if skill.skill_id == skill_id:
            return skill
    raise KeyError(skill_id)
