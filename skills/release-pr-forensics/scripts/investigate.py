from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from _github import GitHubCommandError
from collect_prs import collect
from inspect_pr import inspect
from rank_candidates import rank


def main() -> int:
    parser = argparse.ArgumentParser(description="One-command release/PR regression forensic workflow")
    parser.add_argument("--repo", required=True)
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--release")
    scope.add_argument("--head")
    scope.add_argument("--from-date")
    parser.add_argument("--base")
    parser.add_argument("--previous")
    parser.add_argument("--to-date")
    parser.add_argument("--base-branch")
    parser.add_argument("--query", required=True)
    parser.add_argument("--path-hint", action="append", default=[])
    parser.add_argument("--first-bad-date")
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--inspect-top", type=int, default=3)
    parser.add_argument("--max-patch-chars", type=int, default=60_000)
    parser.add_argument("--output", type=Path, default=Path("release-analysis"))
    args = parser.parse_args()

    try:
        index = collect(
            args.repo,
            args.output,
            base=args.base,
            head=args.head,
            release=args.release,
            previous=args.previous,
            from_date=args.from_date,
            to_date=args.to_date,
            base_branch=args.base_branch,
        )
        candidates = rank(index, args.query, args.path_hint, max(1, args.top), args.first_bad_date)
        (args.output / "candidates.json").write_text(json.dumps(candidates, indent=2), encoding="utf-8")

        inspected = []
        for row in candidates["candidates"][: max(0, args.inspect_top)]:
            number = row.get("pr")
            if not isinstance(number, int):
                continue
            target = args.output / f"inspect-{number}"
            inspected.append(
                inspect(
                    args.repo,
                    number,
                    target,
                    diff_mode="smart",
                    query=args.query,
                    path_hints=args.path_hint,
                    max_patch_chars=max(5_000, args.max_patch_chars),
                )
            )
        result = {
            "success": True,
            "scope": index["scope"],
            "prs": len(index["prs"]),
            "candidate_count": len(candidates["candidates"]),
            "inspected": inspected,
            "output": str(args.output),
            "next": "Read release-summary.md, candidates.json, then selected-patches.md for inspected candidates.",
        }
        print(json.dumps(result, indent=2))
        return 0
    except (GitHubCommandError, ValueError, OSError) as exc:
        print(json.dumps({"success": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
