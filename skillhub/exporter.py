from __future__ import annotations
from pathlib import Path
from .catalog import SkillRecord, get_skill
from .utils import SkillHubError, estimate_tokens

TEXT_SUFFIXES={".md",".txt",".yaml",".yml",".json",".py",".ps1",".bat",".sh"}

def _candidate_files(skill: SkillRecord, include_code: bool = False) -> list[tuple[int,Path]]:
    rows=[(0,skill.path/"SKILL.md")]
    for path in skill.path.rglob("*"):
        if not path.is_file() or path.name in {"SKILL.md","skillhub.yaml"} or path.suffix.lower() not in TEXT_SUFFIXES: continue
        rel=path.relative_to(skill.path).as_posix()
        if rel.startswith("tests/"):
            continue
        if rel.startswith("scripts/") and not include_code:
            continue
        priority=10 if rel.startswith("references/") else 20 if rel.startswith("examples/") else 40 if rel.startswith("scripts/") else 50
        rows.append((priority,path))
    return sorted(rows,key=lambda x:(x[0],x[1].as_posix()))

def export_skill(root: Path, skill_id: str, output: Path, budget: int=6000, include_code: bool=False) -> dict:
    try: skill=get_skill(root,skill_id)
    except KeyError as exc: raise SkillHubError(f"Unknown skill: {skill_id}") from exc
    sections=[]; used=0; included=[]; omitted=[]
    for _,path in _candidate_files(skill, include_code=include_code):
        rel=path.relative_to(skill.path).as_posix(); text=path.read_text(encoding="utf-8",errors="replace")
        section=f"\n\n---\n\n## SkillHub source: `{rel}`\n\n{text.strip()}\n"; cost=estimate_tokens(section)
        if rel=="SKILL.md" or used+cost<=budget: sections.append(section); used+=cost; included.append(rel)
        else: omitted.append(rel)
    header=f"# SkillHub Export — {skill.title}\n\nSkill: `{skill.skill_id}`  \nGenerated for attachment/context use.  \nEstimated context: ~{used} tokens (heuristic, not an exact tokenizer).\n"
    if omitted: header += "\nOmitted due to context budget: " + ", ".join(f"`{x}`" for x in omitted) + "\n"
    output.parent.mkdir(parents=True,exist_ok=True); output.write_text(header+"".join(sections),encoding="utf-8")
    return {"output":str(output),"estimated_tokens":used,"included":included,"omitted":omitted}
