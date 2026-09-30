from __future__ import annotations

import argparse
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STOP = {
    "the", "a", "an", "and", "or", "of", "to", "for", "in", "on", "with", "is", "are", "was", "were",
    "this", "that", "after", "before", "from", "it", "only", "release", "build", "error", "issue", "problem",
    "metric", "jump", "change", "changed",
}
DOC_MARKERS = ("docs/", "documentation/", ".md")
TEST_MARKERS = ("test/", "tests/", "spec/", "specs/", "test_", "_test.")
GENERATED_MARKERS = ("generated/", "vendor/", "third_party/", "node_modules/", ".designer.cs", ".g.cs")
PROD_EXT = (".py", ".cs", ".cpp", ".c", ".h", ".java", ".kt", ".fs", ".go", ".rs", ".ts", ".tsx", ".js", ".sql", ".ps1")
CONFIG_EXT = (".yaml", ".yml", ".json", ".toml", ".ini", ".config", ".props", ".targets", ".xml")
HIGH_RISK = {
    "boundary", "threshold", "formula", "algorithm", "date", "calendar", "timezone", "aggregation", "default",
    "fallback", "cache", "parallel", "concurrency", "sign", "unit", "currency", "interpolation", "calibration",
    "simulation", "monte", "pricing", "exposure", "discount", "rounding", "serialization", "schema",
}


def terms(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9_./-]+", text.lower()) if len(t) > 2 and t not in STOP}


def text_matches(query: set[str], text: str) -> set[str]:
    low = text.lower()
    return {t for t in query if t in low}


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def rank(index: dict[str, Any], query_text: str, path_hints: list[str], top: int, first_bad_date: str | None = None) -> dict[str, Any]:
    query = terms(query_text + " " + " ".join(path_hints))
    bad_dt = _parse_dt(first_bad_date)
    rows: list[dict[str, Any]] = []
    for pr in index.get("prs", []):
        title = pr.get("title") or ""
        body = pr.get("body") or ""
        labels = " ".join(pr.get("labels") or [])
        paths = [f.get("path") or f.get("filename") or "" for f in pr.get("files") or []]
        joined = " ".join([title, body, labels, *paths]).lower()
        m_title = text_matches(query, title)
        m_body = text_matches(query, body)
        m_labels = text_matches(query, labels)
        m_paths = set().union(*(text_matches(query, path) for path in paths)) if paths else set()
        hint_hits = {hint for hint in path_hints if any(hint.lower() in path.lower() for path in paths)}
        risk_hits = sorted(term for term in HIGH_RISK if term in joined)

        score = 5 * len(m_title) + 2 * len(m_body) + 4 * len(m_labels) + 6 * len(m_paths) + 8 * len(hint_hits)
        prod = [path for path in paths if path.lower().endswith(PROD_EXT) and not any(x in path.lower() for x in TEST_MARKERS)]
        configs = [path for path in paths if path.lower().endswith(CONFIG_EXT)]
        docs_only = bool(paths) and all(any(x in path.lower() for x in DOC_MARKERS) for path in paths)
        tests_only = bool(paths) and all(any(x in path.lower() for x in TEST_MARKERS) for path in paths)
        generated_only = bool(paths) and all(any(x in path.lower() for x in GENERATED_MARKERS) for path in paths)

        if prod:
            score += min(5, 1 + int(math.log2(len(prod) + 1)))
        if configs:
            score += min(4, len(configs))
        if risk_hits:
            score += min(8, len(risk_hits))
        if docs_only:
            score -= 8
        if tests_only and not ({"test", "tests"} & query):
            score -= 5
        if generated_only:
            score -= 8

        proximity_days: float | None = None
        merged_dt = _parse_dt(pr.get("merged_at"))
        if bad_dt and merged_dt:
            proximity_days = (bad_dt - merged_dt).total_seconds() / 86400
            if 0 <= proximity_days <= 14:
                score += max(1, 5 - int(proximity_days // 3))
            elif proximity_days < 0:
                score -= 4

        reasons: list[str] = []
        if m_title:
            reasons.append("title matches: " + ", ".join(sorted(m_title)))
        if m_paths:
            reasons.append("changed paths match: " + ", ".join(sorted(m_paths)))
        if m_labels:
            reasons.append("labels match: " + ", ".join(sorted(m_labels)))
        if m_body:
            reasons.append("PR body matches: " + ", ".join(sorted(m_body)))
        if hint_hits:
            reasons.append("path hints hit: " + ", ".join(sorted(hint_hits)))
        if prod:
            reasons.append(f"touches {len(prod)} production-code file(s)")
        if configs:
            reasons.append(f"touches {len(configs)} config/schema file(s)")
        if risk_hits:
            reasons.append("risk-sensitive terms: " + ", ".join(risk_hits[:8]))
        if proximity_days is not None and 0 <= proximity_days <= 14:
            reasons.append(f"merged {proximity_days:.1f} day(s) before first bad observation")
        if docs_only:
            reasons.append("docs-only penalty")
        if tests_only:
            reasons.append("tests-only penalty")
        if generated_only:
            reasons.append("generated/vendor-only penalty")

        rows.append(
            {
                "pr": pr.get("number"),
                "title": title,
                "relevance_score": score,
                "signals": reasons,
                "matched_terms": sorted(m_title | m_body | m_labels | m_paths),
                "sample_paths": paths[:15],
                "changed_files": pr.get("changed_files", len(paths)),
                "additions": pr.get("additions", 0),
                "deletions": pr.get("deletions", 0),
                "merged_at": pr.get("merged_at"),
                "url": pr.get("url"),
            }
        )
    rows.sort(key=lambda row: (-int(row["relevance_score"]), int(row["pr"] or 0)))

    direct: list[dict[str, Any]] = []
    for commit in index.get("direct_commits", []):
        matched = text_matches(query, commit.get("message") or "")
        direct.append(
            {
                "sha": commit.get("sha"),
                "message": commit.get("message"),
                "relevance_score": 4 * len(matched),
                "matched_terms": sorted(matched),
            }
        )
    direct.sort(key=lambda row: -int(row["relevance_score"]))
    return {
        "schema_version": 2,
        "query": query_text,
        "query_terms": sorted(query),
        "first_bad_date": first_bad_date,
        "note": "Scores are retrieval relevance, not probability of causation.",
        "candidates": rows[:top],
        "direct_commit_candidates": direct[:top],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Rank PRs using deterministic lexical/path/risk signals")
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--path-hint", action="append", default=[])
    parser.add_argument("--first-bad-date")
    parser.add_argument("--top", type=int, default=12)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    data = json.loads(args.index.read_text(encoding="utf-8"))
    result = rank(data, args.query, args.path_hint, max(1, args.top), args.first_bad_date)
    text = json.dumps(result, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
