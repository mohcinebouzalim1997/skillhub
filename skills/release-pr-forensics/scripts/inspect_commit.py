from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from _github import GitHubCommandError, commit_details, validate_repo
from inspect_pr import select_patches


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect a direct/unmapped commit using smart selective patches")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--query", default="")
    parser.add_argument("--path-hint", action="append", default=[])
    parser.add_argument("--max-patch-chars", type=int, default=60_000)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        validate_repo(args.repo)
        payload = commit_details(args.repo, args.sha)
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / "commit.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        plan = select_patches(payload.get("files") or [], args.query, args.path_hint, max_patch_chars=max(5_000, args.max_patch_chars))
        summary = {
            "strategy": plan["strategy"],
            "selected": [{k: v for k, v in row.items() if k != "patch"} for row in plan["selected"]],
            "omitted": [{k: v for k, v in row.items() if k != "patch"} for row in plan["omitted"]],
            "full_diff_recommended": plan["full_diff_recommended"],
        }
        (args.output / "diff-plan.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        lines = [f"# Commit `{args.sha}` — selected patches", ""]
        for row in plan["selected"]:
            lines.extend([f"## `{row.get('filename')}`", "", "```diff", str(row.get("patch") or ""), "```", ""])
        (args.output / "selected-patches.md").write_text("\n".join(lines), encoding="utf-8")
        print(json.dumps({"success": True, "sha": args.sha, "selected_files": len(plan["selected"]), "output": str(args.output)}, indent=2))
        return 0
    except (GitHubCommandError, ValueError) as exc:
        print(json.dumps({"success": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
