"""Backward-compatible wrapper for the v0.1 ref-range collector."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from _github import GitHubCommandError
from collect_prs import collect


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a compact release-to-PR forensic index")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--output", type=Path, default=Path("release-analysis"))
    args = parser.parse_args()
    try:
        index = collect(args.repo, args.output, base=args.base, head=args.head)
        print(json.dumps({"success": True, "output": str(args.output), "prs": len(index["prs"])}, indent=2))
        return 0
    except (GitHubCommandError, ValueError) as exc:
        print(json.dumps({"success": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
