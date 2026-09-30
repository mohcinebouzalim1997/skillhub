from __future__ import annotations

import json
import re
import shutil
import subprocess
from typing import Any
from urllib.parse import quote

REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class GitHubCommandError(RuntimeError):
    pass


def require_gh() -> None:
    if shutil.which("gh") is None:
        raise GitHubCommandError("GitHub CLI 'gh' is not installed or is not on PATH")


def validate_repo(repo: str) -> None:
    if not REPO_RE.fullmatch(repo):
        raise ValueError("--repo must be in OWNER/REPO form")


def run_gh(args: list[str], *, expect_json: bool = False) -> Any:
    """Run GitHub CLI without a shell so refs/query text cannot become shell syntax."""
    require_gh()
    proc = subprocess.run(["gh", *args], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        message = (proc.stderr or proc.stdout).strip()
        preview = " ".join(args[:5])
        raise GitHubCommandError(f"gh {preview} failed: {message}")
    if not expect_json:
        return proc.stdout
    try:
        return json.loads(proc.stdout or "null")
    except json.JSONDecodeError as exc:
        raise GitHubCommandError("GitHub CLI returned invalid JSON") from exc


def api_json(endpoint: str) -> Any:
    return run_gh(
        ["api", endpoint, "--header", "Accept: application/vnd.github+json"],
        expect_json=True,
    )


def compare_commits(repo: str, base: str, head: str, per_page: int = 100, max_pages: int = 100) -> dict[str, Any]:
    """Compare refs and normalize commit pagination.

    GitHub returns changed files only on the first page and caps that interval-level list. We keep
    it as context only; PR file lists are retrieved independently.
    """
    validate_repo(repo)
    combined: dict[str, Any] | None = None
    seen: set[str] = set()
    commits: list[dict[str, Any]] = []
    encoded = f"{quote(base, safe='')}...{quote(head, safe='')}"
    for page in range(1, max_pages + 1):
        payload = api_json(f"repos/{repo}/compare/{encoded}?per_page={per_page}&page={page}")
        if not isinstance(payload, dict):
            raise GitHubCommandError("Unexpected compare response")
        if combined is None:
            combined = payload
        page_commits = payload.get("commits") or []
        for commit in page_commits:
            sha = commit.get("sha")
            if sha and sha not in seen:
                seen.add(sha)
                commits.append(commit)
        if len(page_commits) < per_page:
            break
    else:
        raise GitHubCommandError(f"Compare exceeded safety limit of {max_pages * per_page} commits")
    assert combined is not None
    combined["commits"] = commits
    combined["retrieved_commits"] = len(commits)
    return combined


def associated_prs(repo: str, sha: str) -> list[dict[str, Any]]:
    payload = api_json(f"repos/{repo}/commits/{sha}/pulls?per_page=100")
    return payload if isinstance(payload, list) else []


def pr_details(repo: str, number: int) -> dict[str, Any]:
    fields = (
        "number,title,body,author,labels,files,commits,mergedAt,createdAt,updatedAt,"
        "additions,deletions,changedFiles,baseRefName,headRefName,url,state,mergeCommit,"
        "reviewDecision,statusCheckRollup"
    )
    payload = run_gh(["pr", "view", str(number), "-R", repo, "--json", fields], expect_json=True)
    if not isinstance(payload, dict):
        raise GitHubCommandError(f"Unexpected PR response for #{number}")
    return payload


def list_merged_prs(repo: str, from_date: str, to_date: str, base_branch: str | None = None, limit: int = 1000) -> list[dict[str, Any]]:
    """List PRs whose *merge time* falls inside a date window."""
    query = f"merged:>={from_date} merged:<={to_date}"
    if base_branch:
        query += f" base:{base_branch}"
    fields = (
        "number,title,body,author,labels,files,commits,mergedAt,createdAt,updatedAt,"
        "additions,deletions,changedFiles,baseRefName,headRefName,url,state,mergeCommit"
    )
    payload = run_gh(
        ["pr", "list", "-R", repo, "--state", "merged", "--search", query, "--limit", str(limit), "--json", fields],
        expect_json=True,
    )
    return payload if isinstance(payload, list) else []


def list_commits_by_date(
    repo: str,
    branch: str,
    since_iso: str,
    until_iso: str,
    *,
    per_page: int = 100,
    max_pages: int = 50,
) -> list[dict[str, Any]]:
    """List commits on a branch in a timestamp window, mainly to surface direct commits."""
    commits: list[dict[str, Any]] = []
    seen: set[str] = set()
    for page in range(1, max_pages + 1):
        endpoint = (
            f"repos/{repo}/commits?sha={quote(branch, safe='')}&since={quote(since_iso, safe=':TZ-')}"
            f"&until={quote(until_iso, safe=':TZ-')}&per_page={per_page}&page={page}"
        )
        payload = api_json(endpoint)
        if not isinstance(payload, list):
            raise GitHubCommandError("Unexpected commits response")
        for commit in payload:
            sha = commit.get("sha")
            if sha and sha not in seen:
                seen.add(sha)
                commits.append(commit)
        if len(payload) < per_page:
            break
    return commits


def matching_refs(repo: str, namespace_prefix: str) -> list[str]:
    """Return matching Git refs, e.g. namespace_prefix='heads/release/'."""
    payload = api_json(f"repos/{repo}/git/matching-refs/{quote(namespace_prefix, safe='/')}")
    if not isinstance(payload, list):
        return []
    return [str(item.get("ref")) for item in payload if item.get("ref")]


def resolve_ref(repo: str, ref: str) -> dict[str, Any]:
    payload = api_json(f"repos/{repo}/commits/{quote(ref, safe='')}")
    if not isinstance(payload, dict) or not payload.get("sha"):
        raise GitHubCommandError(f"Could not resolve ref: {ref}")
    return payload


def pr_files_with_patch(repo: str, number: int, per_page: int = 100, max_pages: int = 30) -> list[dict[str, Any]]:
    """Fetch PR files with GitHub's per-file patch snippets.

    Binary files and some very large diffs may have no `patch` field. GitHub caps the endpoint to
    3000 files; this safety loop mirrors that upper bound.
    """
    files: list[dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        payload = api_json(f"repos/{repo}/pulls/{number}/files?per_page={per_page}&page={page}")
        if not isinstance(payload, list):
            raise GitHubCommandError(f"Unexpected files response for PR #{number}")
        files.extend(payload)
        if len(payload) < per_page:
            break
    return files


def pr_diff(repo: str, number: int) -> str:
    return str(run_gh(["pr", "diff", str(number), "-R", repo, "--patch", "--color", "never"], expect_json=False))


def commit_details(repo: str, sha: str) -> dict[str, Any]:
    payload = api_json(f"repos/{repo}/commits/{quote(sha, safe='')}")
    if not isinstance(payload, dict):
        raise GitHubCommandError(f"Unexpected commit response for {sha}")
    return payload
