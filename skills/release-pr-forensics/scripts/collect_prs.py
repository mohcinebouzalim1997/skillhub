from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from _github import (
    GitHubCommandError,
    associated_prs,
    compare_commits,
    list_commits_by_date,
    list_merged_prs,
    matching_refs,
    pr_details,
    resolve_ref,
    validate_repo,
)

_VERSION_LEAF = re.compile(r"^(?:v)?(\d{2,4})[._-](\d{1,2})(?:[._-](\d+))?$")


@dataclass(frozen=True)
class Scope:
    mode: str
    label: str
    base: str | None = None
    head: str | None = None
    release: str | None = None
    from_date: str | None = None
    to_date: str | None = None
    base_branch: str | None = None
    inferred_base: bool = False


def compact_pr(details: dict[str, Any]) -> dict[str, Any]:
    merge_commit = details.get("mergeCommit") or {}
    return {
        "number": details.get("number"),
        "title": details.get("title") or "",
        "body": details.get("body") or "",
        "author": (details.get("author") or {}).get("login"),
        "labels": [x.get("name") for x in details.get("labels") or [] if x.get("name")],
        "merged_at": details.get("mergedAt"),
        "created_at": details.get("createdAt"),
        "updated_at": details.get("updatedAt"),
        "additions": details.get("additions", 0),
        "deletions": details.get("deletions", 0),
        "changed_files": details.get("changedFiles", len(details.get("files") or [])),
        "files": details.get("files") or [],
        "commits": details.get("commits") or [],
        "merge_commit_sha": merge_commit.get("oid"),
        "base_ref": details.get("baseRefName"),
        "head_ref": details.get("headRefName"),
        "url": details.get("url"),
        "state": details.get("state"),
    }


def commit_summary(commit: dict[str, Any]) -> dict[str, Any]:
    data = commit.get("commit") or {}
    author = data.get("author") or {}
    committer = data.get("committer") or {}
    return {
        "sha": commit.get("sha"),
        "message": (data.get("message") or "").splitlines()[0],
        "date": committer.get("date") or author.get("date"),
        "author": author.get("name"),
    }


def _parse_date(value: str, *, end: bool) -> str:
    value = value.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return value + ("T23:59:59Z" if end else "T00:00:00Z")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Invalid date/time: {value}") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _version_tuple(ref: str) -> tuple[int, int, int] | None:
    leaf = ref.rstrip("/").rsplit("/", 1)[-1]
    match = _VERSION_LEAF.fullmatch(leaf)
    if not match:
        return None
    return tuple(int(x or 0) for x in match.groups())  # type: ignore[return-value]


def infer_previous_release(repo: str, release: str) -> str:
    """Infer the preceding sibling release ref (for patterns such as release/26.10)."""
    clean = release.removeprefix("refs/heads/").removeprefix("refs/tags/")
    current_version = _version_tuple(clean)
    if current_version is None:
        raise ValueError(
            f"Cannot infer the previous release from '{release}'. Use --previous/--base explicitly."
        )
    prefix = clean.rsplit("/", 1)[0] + "/" if "/" in clean else ""
    candidates: list[str] = []
    for namespace in ("heads/", "tags/"):
        refs = matching_refs(repo, namespace + prefix)
        for full in refs:
            normalized = full.removeprefix("refs/heads/").removeprefix("refs/tags/")
            version = _version_tuple(normalized)
            if version is not None and version < current_version and normalized.startswith(prefix):
                candidates.append(normalized)
    if not candidates:
        raise ValueError(
            f"No earlier sibling release ref was found for '{release}'. Use --previous/--base explicitly."
        )
    candidates.sort(key=lambda ref: _version_tuple(ref) or (0, 0, 0))
    return candidates[-1]


def _map_commits_to_prs(repo: str, commits: list[dict[str, Any]]) -> tuple[dict[int, set[str]], list[dict[str, Any]]]:
    pr_numbers: dict[int, set[str]] = {}
    direct: list[dict[str, Any]] = []
    for commit in commits:
        prs = associated_prs(repo, str(commit["sha"]))
        if not prs:
            direct.append(commit)
            continue
        mapped = False
        for pr in prs:
            number = pr.get("number")
            if isinstance(number, int):
                pr_numbers.setdefault(number, set()).add(str(commit["sha"]))
                mapped = True
        if not mapped:
            direct.append(commit)
    return pr_numbers, direct


def _write_prs(repo: str, numbers: dict[int, set[str]], output: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for number in sorted(numbers):
        details = compact_pr(pr_details(repo, number))
        details["interval_commit_shas"] = sorted(numbers[number])
        rows.append(details)
        (output / "prs" / f"{number}.json").write_text(json.dumps(details, indent=2), encoding="utf-8")
    return rows


def _collect_range(repo: str, base: str, head: str, output: Path, mode: str = "range", release: str | None = None, inferred: bool = False) -> dict[str, Any]:
    resolve_ref(repo, base)
    resolve_ref(repo, head)
    compare = compare_commits(repo, base, head)
    commits = [commit_summary(c) for c in compare.get("commits") or []]
    pr_numbers, direct = _map_commits_to_prs(repo, commits)
    prs = _write_prs(repo, pr_numbers, output)
    scope = Scope(
        mode=mode,
        label=(f"release {release}: {base} → {head}" if release else f"{base} → {head}"),
        base=base,
        head=head,
        release=release,
        inferred_base=inferred,
    )
    return {
        "scope": scope.__dict__,
        "compare_status": compare.get("status"),
        "ahead_by": compare.get("ahead_by"),
        "behind_by": compare.get("behind_by"),
        "total_commits_reported": compare.get("total_commits"),
        "commits": commits,
        "prs": prs,
        "direct_commits": direct,
        "interval_files": [f.get("filename") for f in compare.get("files") or [] if f.get("filename")],
        "limitations": [
            "The compare endpoint's interval-level changed-file list is capped by GitHub; per-PR files are retrieved separately.",
            "Associated PR mapping is evidence of provenance, not proof that a PR caused the observed regression.",
        ],
    }


def _collect_dates(repo: str, from_date: str, to_date: str, base_branch: str | None, output: Path) -> dict[str, Any]:
    start_iso = _parse_date(from_date, end=False)
    end_iso = _parse_date(to_date, end=True)
    if start_iso > end_iso:
        raise ValueError("--from-date must be <= --to-date")
    merged = list_merged_prs(repo, from_date, to_date, base_branch)
    rows: dict[int, dict[str, Any]] = {}
    for details in merged:
        number = details.get("number")
        if isinstance(number, int):
            rows[number] = compact_pr(details)

    # Direct-commit detection is best-effort. It uses commit timestamps on the selected branch,
    # which is not identical to PR merge time, but it prevents silent loss of obvious direct pushes.
    direct: list[dict[str, Any]] = []
    commits: list[dict[str, Any]] = []
    if base_branch:
        resolve_ref(repo, base_branch)
        raw_commits = list_commits_by_date(repo, base_branch, start_iso, end_iso)
        commits = [commit_summary(c) for c in raw_commits]
        pr_numbers, direct = _map_commits_to_prs(repo, commits)
        for number, shas in pr_numbers.items():
            if number not in rows:
                details = compact_pr(pr_details(repo, number))
                details["interval_commit_shas"] = sorted(shas)
                rows[number] = details
            else:
                rows[number]["interval_commit_shas"] = sorted(shas)

    prs = [rows[n] for n in sorted(rows)]
    for pr in prs:
        (output / "prs" / f"{pr['number']}.json").write_text(json.dumps(pr, indent=2), encoding="utf-8")
    scope = Scope(
        mode="dates",
        label=f"merged PRs {from_date} → {to_date}" + (f" on {base_branch}" if base_branch else ""),
        from_date=from_date,
        to_date=to_date,
        base_branch=base_branch,
    )
    limitations = [
        "Date mode selects pull requests by GitHub merge timestamp.",
        "Provide --base-branch to additionally scan branch commits for direct/unmapped changes.",
    ]
    if base_branch:
        limitations.append("Direct-commit detection uses commit timestamps, which can differ from PR merge timestamps.")
    return {
        "scope": scope.__dict__,
        "compare_status": None,
        "commits": commits,
        "prs": prs,
        "direct_commits": direct,
        "interval_files": [],
        "limitations": limitations,
    }


def render_summary(index: dict[str, Any]) -> str:
    scope = index.get("scope") or {}
    lines = [
        "# Release / PR forensic index",
        "",
        f"- Repository: `{index['repo']}`",
        f"- Scope: **{scope.get('label', scope.get('mode', 'unknown'))}**",
        f"- Pull requests: **{len(index['prs'])}**",
        f"- Commits scanned: **{len(index['commits'])}**",
        f"- Direct/unmapped commits: **{len(index['direct_commits'])}**",
        "",
        "> Start here. Rank first; inspect selective patches second; fetch full diffs only when necessary.",
        "",
        "## Pull requests",
        "",
    ]
    for pr in index["prs"]:
        paths = [f.get("path") for f in pr.get("files", []) if f.get("path")][:10]
        lines.extend(
            [
                f"### PR #{pr['number']} — {pr['title']}",
                "",
                f"Merged: {pr.get('merged_at') or '—'}  ",
                f"Labels: {', '.join(pr.get('labels') or []) or '—'}  ",
                f"Changed files: {pr.get('changed_files', 0)} · +{pr.get('additions', 0)} / -{pr.get('deletions', 0)}  ",
                "Paths: " + (", ".join(f"`{p}`" for p in paths) if paths else "—"),
                "",
            ]
        )
    if index["direct_commits"]:
        lines.extend(["## Direct / unmapped commits", ""])
        for commit in index["direct_commits"]:
            lines.append(f"- `{str(commit['sha'])[:10]}` {commit.get('message', '')}")
        lines.append("")
    if index.get("limitations"):
        lines.extend(["## Scope notes", ""])
        lines.extend(f"- {item}" for item in index["limitations"])
    return "\n".join(lines) + "\n"


def collect(
    repo: str,
    output: Path,
    *,
    base: str | None = None,
    head: str | None = None,
    release: str | None = None,
    previous: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    base_branch: str | None = None,
) -> dict[str, Any]:
    validate_repo(repo)
    output.mkdir(parents=True, exist_ok=True)
    (output / "prs").mkdir(exist_ok=True)

    if release:
        if head or from_date or to_date:
            raise ValueError("--release cannot be combined with --head or date-window arguments")
        base_ref = previous or base
        inferred = False
        if not base_ref:
            base_ref = infer_previous_release(repo, release)
            inferred = True
        payload = _collect_range(repo, base_ref, release, output, mode="release", release=release, inferred=inferred)
    elif from_date or to_date:
        if not (from_date and to_date):
            raise ValueError("Date mode requires both --from-date and --to-date")
        if base or head or previous:
            raise ValueError("Date mode cannot be combined with --base/--head/--previous")
        payload = _collect_dates(repo, from_date, to_date, base_branch, output)
    else:
        if not (base and head):
            raise ValueError("Provide --base and --head, or --release, or --from-date/--to-date")
        payload = _collect_range(repo, base, head, output)

    index = {
        "schema_version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repo": repo,
        **payload,
    }
    (output / "release-index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")
    (output / "release-summary.md").write_text(render_summary(index), encoding="utf-8")
    return index


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect PR provenance by release/ref range, commit range, or date window."
    )
    parser.add_argument("--repo", required=True, help="OWNER/REPO")
    parser.add_argument("--output", type=Path, default=Path("release-analysis"))
    parser.add_argument("--base", help="Known-good ref/commit. With --release, this is the previous release.")
    parser.add_argument("--head", help="Known-bad ref/commit")
    parser.add_argument("--release", help="Release branch/tag/ref, e.g. release/26.10")
    parser.add_argument("--previous", help="Previous release ref. If omitted, numeric sibling refs are auto-detected.")
    parser.add_argument("--from-date", help="Start date or ISO timestamp")
    parser.add_argument("--to-date", help="End date or ISO timestamp")
    parser.add_argument("--base-branch", help="Date mode: restrict PRs and scan commits on this branch")
    return parser


def main() -> int:
    args = build_parser().parse_args()
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
        print(
            json.dumps(
                {
                    "success": True,
                    "scope": index["scope"],
                    "output": str(args.output),
                    "commits": len(index["commits"]),
                    "prs": len(index["prs"]),
                    "direct_commits": len(index["direct_commits"]),
                },
                indent=2,
            )
        )
        return 0
    except (GitHubCommandError, ValueError) as exc:
        print(json.dumps({"success": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
