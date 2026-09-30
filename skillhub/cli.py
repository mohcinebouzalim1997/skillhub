from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .bridge import serve_marketplace
from .catalog import get_skill, iter_skills
from .doctor import run_doctor
from .exporter import export_skill
from .installer import (
    available_agents,
    dependency_status,
    install_agent,
    install_pack,
    install_python_dependencies,
    install_skill,
    install_skill_tree,
    install_stack,
    installed_agents,
    installed_skill_versions,
    sync_installed,
    uninstall_agent,
    uninstall_skill,
)
from .registry import build_registry
from .runner import run_skill
from .scaffold import scaffold_from_issue_event, scaffold_skill
from .site import build_site, prepare_site_sources, serve_site
from .utils import SkillHubError, configure_hub_root, find_repo_root, load_yaml
from .validation import validate_repo


def _root(value: str | None) -> Path:
    return Path(value).resolve() if value else find_repo_root()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="skillhub", description="Quant SkillHub CLI")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--root")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor")
    sub.add_parser("list")
    sub.add_parser("status")
    sub.add_parser("agents")
    sub.add_parser("stacks")
    sub.add_parser("workflows")
    cfg = sub.add_parser("configure")
    cfg.add_argument("--hub", type=Path, required=True)
    sync = sub.add_parser("sync")
    sync.add_argument("--dest")
    show = sub.add_parser("show")
    show.add_argument("skill")
    run = sub.add_parser("run")
    run.add_argument("skill")
    run.add_argument("--entry", default="default")
    run.add_argument("args", nargs=argparse.REMAINDER)
    deps = sub.add_parser("deps")
    deps.add_argument("skill")
    ideps = sub.add_parser("install-deps")
    ideps.add_argument("skill")
    val = sub.add_parser("validate")
    val.add_argument("--json", action="store_true", dest="as_json")
    reg = sub.add_parser("build-registry")
    reg.add_argument("--output")
    site = sub.add_parser("build-site")
    site.add_argument("--output")
    preview = sub.add_parser("serve-site")
    preview.add_argument("--addr", default="127.0.0.1:8000")
    sub.add_parser("generate-site")
    market = sub.add_parser("marketplace")
    market.add_argument("--host", default="127.0.0.1")
    market.add_argument("--port", type=int, default=8765)
    market.add_argument("--open", action="store_true", dest="open_browser")
    ins = sub.add_parser("install")
    ins.add_argument("skill")
    ins.add_argument("--dest")
    ins.add_argument("--force", action="store_true")
    ins.add_argument("--check-deps", action="store_true")
    update = sub.add_parser("update")
    update.add_argument("skill")
    update.add_argument("--dest")
    un = sub.add_parser("uninstall")
    un.add_argument("skill")
    un.add_argument("--dest")
    pack = sub.add_parser("install-pack")
    pack.add_argument("pack")
    pack.add_argument("--dest")
    pack.add_argument("--force", action="store_true")
    ains = sub.add_parser("install-agent")
    ains.add_argument("agent")
    ains.add_argument("--dest")
    ains.add_argument("--force", action="store_true")
    aun = sub.add_parser("uninstall-agent")
    aun.add_argument("agent")
    aun.add_argument("--dest")
    stack = sub.add_parser("install-stack")
    stack.add_argument("stack")
    stack.add_argument("--skill-dest")
    stack.add_argument("--agent-dest")
    stack.add_argument("--force", action="store_true")
    stack.add_argument("--check-deps", action="store_true")
    exp = sub.add_parser("export")
    exp.add_argument("skill")
    exp.add_argument("--budget", type=int, default=6000)
    exp.add_argument("--output", required=True)
    exp.add_argument("--include-code", action="store_true")
    new = sub.add_parser("new")
    new.add_argument("name")
    new.add_argument("--description", required=True)
    new.add_argument("--category", default="engineering")
    new.add_argument("--owner", default="unassigned")
    issue = sub.add_parser("scaffold-from-issue")
    issue.add_argument("event_path")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "doctor":
            for name, info in run_doctor().items():
                print(f"[{'OK' if info['ok'] else '!!'}] {name}: {info['value']}")
            try:
                print(f"[OK] hub_root: {find_repo_root()}")
            except SkillHubError as exc:
                print(f"[!!] hub_root: {exc}")
            return 0
        if args.command == "configure":
            print(configure_hub_root(args.hub))
            return 0

        root = _root(args.root)
        if args.command == "list":
            for skill in iter_skills(root):
                print(f"{skill.skill_id:30} {skill.metadata.get('status','?'):10} {skill.title}")
        elif args.command == "status":
            installed = installed_skill_versions()
            available = {skill.skill_id: str(skill.metadata.get("version", "?")) for skill in iter_skills(root)}
            for skill_id, version in sorted(available.items()):
                have = installed.get(skill_id)
                state = "not-installed" if have is None else ("current" if have == version else f"update {have} -> {version}")
                print(f"{skill_id:30} {state}")
        elif args.command == "agents":
            have = installed_agents()
            for agent_id, info in available_agents(root).items():
                print(f"{agent_id:30} {'installed' if agent_id in have else 'not-installed':14} {info['description']}")
        elif args.command == "stacks":
            for path in sorted((root / "stacks").glob("*.yaml")):
                data = load_yaml(path)
                print(f"{data.get('id', path.stem):30} {data.get('name','')}")
        elif args.command == "workflows":
            for path in sorted((root / "workflows").glob("*.yaml")):
                data = load_yaml(path)
                print(f"{data.get('id', path.stem):30} {data.get('status','?'):12} {data.get('name','')}")
        elif args.command == "sync":
            paths = sync_installed(root, Path(args.dest).expanduser() if args.dest else None)
            for path in paths:
                print(path)
        elif args.command == "show":
            try:
                skill = get_skill(root, args.skill)
            except KeyError as exc:
                raise SkillHubError(f"Unknown skill: {args.skill}") from exc
            print(json.dumps(skill.to_registry_entry(), indent=2))
        elif args.command == "run":
            return run_skill(root, args.skill, args.entry, args.args)
        elif args.command == "deps":
            print(json.dumps(dependency_status(root, args.skill), indent=2))
        elif args.command == "install-deps":
            print(json.dumps(install_python_dependencies(root, args.skill), indent=2))
        elif args.command == "validate":
            report = validate_repo(root)
            if args.as_json:
                print(json.dumps([m.__dict__ for m in report.messages], indent=2))
            else:
                for message in report.messages:
                    print(f"[{message.level.upper():7}] {message.location}: {message.message}")
                print(f"Validation: {'PASS' if report.ok else 'FAIL'} ({len(report.errors)} errors, {len(report.warnings)} warnings)")
            return 0 if report.ok else 1
        elif args.command == "build-registry":
            print(f"Registry built with {len(build_registry(root, Path(args.output).resolve() if args.output else None)['skills'])} skills")
        elif args.command == "generate-site":
            print(f"Generated site sources for {len(prepare_site_sources(root)['skills'])} skills")
        elif args.command == "build-site":
            print(build_site(root, Path(args.output).resolve() if args.output else None))
        elif args.command == "serve-site":
            return serve_site(root, args.addr)
        elif args.command == "marketplace":
            return serve_marketplace(root, args.host, args.port, args.open_browser)
        elif args.command == "install":
            if args.check_deps:
                status = dependency_status(root, args.skill)
                if not status["ok"]:
                    raise SkillHubError(f"Missing dependencies: {json.dumps(status)}")
            for path in install_skill_tree(root, args.skill, Path(args.dest).expanduser() if args.dest else None, args.force):
                print(path)
        elif args.command == "update":
            for path in install_skill_tree(root, args.skill, Path(args.dest).expanduser() if args.dest else None, True):
                print(path)
        elif args.command == "uninstall":
            print(uninstall_skill(args.skill, Path(args.dest).expanduser() if args.dest else None))
        elif args.command == "install-pack":
            for path in install_pack(root, args.pack, Path(args.dest).expanduser() if args.dest else None, args.force):
                print(path)
        elif args.command == "install-agent":
            print(install_agent(root, args.agent, Path(args.dest).expanduser() if args.dest else None, args.force))
        elif args.command == "uninstall-agent":
            print(uninstall_agent(args.agent, Path(args.dest).expanduser() if args.dest else None))
        elif args.command == "install-stack":
            if args.check_deps:
                stack_path = root / "stacks" / f"{args.stack}.yaml"
                if not stack_path.exists():
                    raise SkillHubError(f"Unknown stack: {args.stack}")
                missing = {sid: dependency_status(root, str(sid)) for sid in load_yaml(stack_path).get("skills") or []}
                missing = {sid: state for sid, state in missing.items() if not state["ok"]}
                if missing:
                    raise SkillHubError(f"Missing stack dependencies: {json.dumps(missing)}")
            result = install_stack(
                root,
                args.stack,
                Path(args.skill_dest).expanduser() if args.skill_dest else None,
                Path(args.agent_dest).expanduser() if args.agent_dest else None,
                args.force,
            )
            for path in result["skills"] + result["agents"]:
                print(path)
        elif args.command == "export":
            print(json.dumps(export_skill(root, args.skill, Path(args.output), args.budget, args.include_code), indent=2))
        elif args.command == "new":
            print(scaffold_skill(root, args.name, args.description, args.category, args.owner))
        elif args.command == "scaffold-from-issue":
            print(scaffold_from_issue_event(root, Path(args.event_path)))
        return 0
    except SkillHubError as exc:
        print(f"skillhub: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
