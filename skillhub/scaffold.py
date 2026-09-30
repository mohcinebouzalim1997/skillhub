from __future__ import annotations
import json
from pathlib import Path
import yaml
from .utils import SkillHubError, slugify

def scaffold_skill(root: Path,name: str,description: str,category: str,owner: str)->Path:
    skill_id=slugify(name)
    if not skill_id: raise SkillHubError("Skill name produces an empty identifier")
    path=root/"skills"/skill_id
    if path.exists(): raise SkillHubError(f"Skill already exists: {skill_id}")
    (path/"references").mkdir(parents=True); (path/"tests").mkdir()
    (path/"SKILL.md").write_text(f"---\nname: {skill_id}\ndescription: >\n  {description}\n---\n\n# Goal\n\nDescribe the outcome.\n\n# Inputs\n\n- Required input\n\n# Workflow\n\n1. First step.\n2. Second step.\n\n# Output\n\nReturn evidence, conclusions, uncertainty, and next action.\n",encoding="utf-8")
    meta={"schema_version":1,"id":skill_id,"version":"0.1.0","title":name,"category":category,"owner":owner,"status":"draft","executable":False,"tags":[],"aliases":[],"compatibility":{"github-copilot":"full","microsoft-copilot":"export"}}
    (path/"skillhub.yaml").write_text(yaml.safe_dump(meta,sort_keys=False),encoding="utf-8")
    return path

def scaffold_from_issue_event(root: Path,event_path: Path)->Path:
    event=json.loads(event_path.read_text(encoding="utf-8")); issue=event.get("issue") or {}; title=issue.get("title") or "New skill"; body=issue.get("body") or ""
    sections={}; current=None; lines=[]
    for line in body.splitlines():
        if line.startswith("### "):
            if current: sections[current]="\n".join(lines).strip()
            current=line[4:].strip().lower(); lines=[]
        elif current: lines.append(line)
    if current: sections[current]="\n".join(lines).strip()
    name=sections.get("skill name") or title.removeprefix("[Skill request] ")
    desc=sections.get("when should someone use it?") or sections.get("what should this skill do?") or "Reusable internal capability."
    return scaffold_skill(root,name,desc.replace("\n"," "),sections.get("category") or "engineering",sections.get("owner/team") or "unassigned")
