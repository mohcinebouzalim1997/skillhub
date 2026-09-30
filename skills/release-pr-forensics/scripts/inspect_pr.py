from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from _github import GitHubCommandError, pr_details, pr_diff, pr_files_with_patch, validate_repo

CODE_EXT = {
    ".py", ".cs", ".fs", ".java", ".kt", ".cpp", ".c", ".h", ".hpp", ".go", ".rs",
    ".ts", ".tsx", ".js", ".jsx", ".sql", ".ps1", ".bat", ".sh", ".yaml", ".yml", ".json",
    ".xml", ".toml", ".ini", ".cfg", ".config", ".props", ".targets", ".csproj", ".fsproj",
}
DOC_EXT = {".md", ".rst", ".txt", ".adoc"}
LOCK_NAMES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "uv.lock", "packages.lock.json"}
GENERATED_MARKERS = ("generated/", "/generated/", ".g.cs", ".designer.cs", "dist/", "build/", "vendor/", "third_party/", "node_modules/")
TEST_MARKERS = ("/test/", "/tests/", "/spec/", "/specs/", "test_", "_test.", ".tests/")
CONFIG_MARKERS = ("config", "settings", "appsettings", "parameters", "featureflag", "feature_flag")
RISK_TERMS = (
    "boundary", "date", "calendar", "timezone", "aggregation", "formula", "pricing", "exposure",
    "eepe", "epe", "pfe", "cva", "xva", "mtf", "firstpassage", "first-passage", "threshold",
    "default", "fallback", "cache", "concurrency", "thread", "parallel", "round", "sign", "unit",
    "currency", "fx", "discount", "interpolation", "calibration", "simulation", "monte", "path",
)


def _terms(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9_.-]+", text.lower()) if len(t) > 2}


def _classify(path: str) -> str:
    low = path.lower().replace("\\", "/")
    name = low.rsplit("/", 1)[-1]
    suffix = Path(name).suffix.lower()
    if name in LOCK_NAMES:
        return "lockfile"
    if any(marker in low for marker in GENERATED_MARKERS):
        return "generated/vendor"
    if any(marker in low for marker in TEST_MARKERS):
        return "test"
    if suffix in DOC_EXT or low.startswith("docs/") or "/docs/" in low:
        return "docs"
    if suffix in CODE_EXT or any(marker in low for marker in CONFIG_MARKERS):
        return "code/config"
    return "other"


def _score_file(file: dict[str, Any], query: str, path_hints: list[str], include_tests: bool, include_docs: bool) -> tuple[int, list[str]]:
    path = str(file.get("filename") or file.get("path") or "")
    patch = str(file.get("patch") or "")
    low = path.lower()
    query_terms = _terms(query)
    reasons: list[str] = []
    score = 0
    kind = _classify(path)

    path_matches = sorted(t for t in query_terms if t in low)
    patch_lower = patch.lower()[:20000]
    patch_matches = sorted(t for t in query_terms if t in patch_lower)
    hint_matches = [hint for hint in path_hints if hint.lower() in low]
    risk_hits = [term for term in RISK_TERMS if term in low or term in patch_lower]

    if path_matches:
        score += 9 + 2 * len(path_matches)
        reasons.append("path matches query: " + ", ".join(path_matches[:6]))
    if patch_matches:
        score += 5 + min(10, len(patch_matches))
        reasons.append("patch matches query: " + ", ".join(patch_matches[:6]))
    if hint_matches:
        score += 12 * len(hint_matches)
        reasons.append("path hint: " + ", ".join(hint_matches))
    if risk_hits:
        score += min(10, 2 * len(risk_hits))
        reasons.append("risk-sensitive logic: " + ", ".join(risk_hits[:6]))
    if kind == "code/config":
        score += 5
        reasons.append("production/config candidate")
    elif kind == "test":
        score += 0 if include_tests else -8
        reasons.append("test file")
    elif kind == "docs":
        score += 0 if include_docs else -12
        reasons.append("documentation")
    elif kind in {"lockfile", "generated/vendor"}:
        score -= 15
        reasons.append(kind)
    else:
        score += 1

    churn = int(file.get("changes") or 0)
    if churn:
        score += min(4, max(0, churn // 100))
    if not patch:
        score -= 2
        reasons.append("no textual patch returned by GitHub")
    return score, reasons


def select_patches(
    files: list[dict[str, Any]],
    query: str,
    path_hints: list[str],
    *,
    max_patch_chars: int = 60_000,
    include_tests: bool = False,
    include_docs: bool = False,
) -> dict[str, Any]:
    scored: list[dict[str, Any]] = []
    for file in files:
        score, reasons = _score_file(file, query, path_hints, include_tests, include_docs)
        row = dict(file)
        row["forensic_score"] = score
        row["selection_reasons"] = reasons
        row["classification"] = _classify(str(file.get("filename") or file.get("path") or ""))
        scored.append(row)
    scored.sort(key=lambda row: (-int(row["forensic_score"]), str(row.get("filename") or "")))

    selected: list[dict[str, Any]] = []
    omitted: list[dict[str, Any]] = []
    used = 0
    for row in scored:
        patch = str(row.get("patch") or "")
        kind = row["classification"]
        forced_low_info = (kind == "test" and not include_tests) or (kind == "docs" and not include_docs) or kind in {"lockfile", "generated/vendor"}
        if not patch:
            omitted.append({**row, "omit_reason": "no textual patch"})
            continue
        if forced_low_info and int(row["forensic_score"]) < 10:
            omitted.append({**row, "omit_reason": f"low-information {kind}"})
            continue
        # Keep at least the strongest file even if one patch exceeds the nominal budget; truncate later.
        remaining = max_patch_chars - used
        if selected and remaining <= 0:
            omitted.append({**row, "omit_reason": "patch budget exhausted"})
            continue
        captured = patch[: max(remaining, 0)]
        truncated = len(captured) < len(patch)
        if not captured and selected:
            omitted.append({**row, "omit_reason": "patch budget exhausted"})
            continue
        selected.append({**row, "patch": captured, "patch_truncated": truncated})
        used += len(captured)

    return {
        "strategy": "smart-selective-patches",
        "max_patch_chars": max_patch_chars,
        "selected": selected,
        "omitted": omitted,
        "selected_patch_chars": used,
        "full_diff_recommended": bool(
            not selected
            or any(item.get("patch_truncated") for item in selected)
            or sum(1 for item in omitted if item.get("omit_reason") == "no textual patch") > 0
        ),
    }


def render_selected_patches(number: int, plan: dict[str, Any]) -> str:
    lines = [
        f"# PR #{number} — selected forensic patches",
        "",
        "> These are selectively chosen patches, not the full PR diff. See `diff-plan.json` for omissions.",
        "",
    ]
    for item in plan["selected"]:
        path = item.get("filename") or item.get("path")
        lines.extend(
            [
                f"## `{path}`",
                "",
                f"Score: **{item['forensic_score']}** · {', '.join(item.get('selection_reasons') or [])}",
                "",
                "```diff",
                str(item.get("patch") or ""),
                "```",
                "",
            ]
        )
        if item.get("patch_truncated"):
            lines.append("_Patch truncated to respect the context budget._\n")
    return "\n".join(lines)


def inspect(
    repo: str,
    number: int,
    output: Path,
    *,
    diff_mode: str = "smart",
    query: str = "",
    path_hints: list[str] | None = None,
    max_patch_chars: int = 60_000,
    include_tests: bool = False,
    include_docs: bool = False,
) -> dict[str, Any]:
    validate_repo(repo)
    output.mkdir(parents=True, exist_ok=True)
    details = pr_details(repo, number)
    (output / "pr.json").write_text(json.dumps(details, indent=2), encoding="utf-8")

    result: dict[str, Any] = {"success": True, "pr": number, "output": str(output), "diff_mode": diff_mode}
    if diff_mode == "none":
        return result
    if diff_mode == "full":
        diff = pr_diff(repo, number)
        (output / "pr.diff").write_text(diff, encoding="utf-8")
        result["full_diff_bytes"] = len(diff.encode("utf-8"))
        return result

    files = pr_files_with_patch(repo, number)
    plan = select_patches(
        files,
        query,
        path_hints or [],
        max_patch_chars=max_patch_chars,
        include_tests=include_tests,
        include_docs=include_docs,
    )
    serializable_plan = {
        **plan,
        "selected": [{k: v for k, v in row.items() if k != "patch"} for row in plan["selected"]],
        "omitted": [{k: v for k, v in row.items() if k != "patch"} for row in plan["omitted"]],
    }
    (output / "diff-plan.json").write_text(json.dumps(serializable_plan, indent=2), encoding="utf-8")
    (output / "selected-patches.md").write_text(render_selected_patches(number, plan), encoding="utf-8")
    result.update(
        {
            "files_total": len(files),
            "selected_files": len(plan["selected"]),
            "omitted_files": len(plan["omitted"]),
            "selected_patch_chars": plan["selected_patch_chars"],
            "full_diff_recommended": plan["full_diff_recommended"],
        }
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect a PR using metadata, smart patches, or a full diff")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--pr", required=True, type=int)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--diff-mode", choices=("smart", "full", "none"), default="smart")
    parser.add_argument("--query", default="")
    parser.add_argument("--path-hint", action="append", default=[])
    parser.add_argument("--max-patch-chars", type=int, default=60_000)
    parser.add_argument("--include-tests", action="store_true")
    parser.add_argument("--include-docs", action="store_true")
    args = parser.parse_args()
    try:
        result = inspect(
            args.repo,
            args.pr,
            args.output,
            diff_mode=args.diff_mode,
            query=args.query,
            path_hints=args.path_hint,
            max_patch_chars=max(5_000, args.max_patch_chars),
            include_tests=args.include_tests,
            include_docs=args.include_docs,
        )
        print(json.dumps(result, indent=2))
        return 0
    except (GitHubCommandError, ValueError) as exc:
        print(json.dumps({"success": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
