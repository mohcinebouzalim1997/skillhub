from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def _root() -> Path:
    configured = os.environ.get("SKILLHUB_ROOT")
    if configured:
        return Path(configured).resolve()
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "skillhub.config.yaml").exists() and (parent / "skills").is_dir():
            return parent
    raise SystemExit("Cannot locate SkillHub root. Run this through `skillhub run prepare-ccr-release-evidence`." )


def _run(root: Path, script: Path, args: list[str]) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root) + (os.pathsep + env.get("PYTHONPATH", "") if env.get("PYTHONPATH") else "")
    proc = subprocess.run([sys.executable, str(script), *args], cwd=Path.cwd(), env=env, text=True)
    if proc.returncode:
        raise SystemExit(proc.returncode)


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _is_material(evidence: dict[str, Any]) -> bool:
    for stats in (evidence.get("metric_statistics") or {}).values():
        if int((stats or {}).get("material_count") or 0) > 0:
            return True
    return False


def _compact_section(label: str, compare: dict[str, Any] | None, backtesting: dict[str, Any] | None) -> list[str]:
    lines = [f"## {label}"]
    if compare is None:
        lines.append("- Not supplied.")
        return lines
    lines.append(f"- Rows scanned: {compare.get('summary', {}).get('rows_scanned')}")
    for metric, stats in (compare.get("metric_statistics") or {}).items():
        lines.append(
            f"- **{metric}**: material={stats.get('material_count')}; selected={stats.get('selected_count')}; "
            f"coverage={stats.get('selected_coverage_pct')}%; threshold capture={stats.get('threshold_capture_pct_of_all_abs_movement')}%; "
            f"top1/top3/top10={stats.get('top1_share_pct')}%/{stats.get('top3_share_pct')}%/{stats.get('top10_share_pct')}%; "
            f"cancellation={stats.get('material_cancellation_pct')}%; effective contributors≈{stats.get('effective_contributors')}; "
            f"contributors 50/80/90/95%={stats.get('contributors_for_50pct')}/{stats.get('contributors_for_80pct')}/{stats.get('contributors_for_90pct')}/{stats.get('contributors_for_95pct')}"
        )
        for group, group_stats in (stats.get("coverage_groups") or {}).items():
            lines.append(
                f"  - {metric} `{group}`: material={group_stats.get('material_count')}; selected={group_stats.get('selected_count')}; "
                f"coverage={group_stats.get('selected_coverage_pct')}%; top1/top3/top10={group_stats.get('top1_share_pct')}%/{group_stats.get('top3_share_pct')}%/{group_stats.get('top10_share_pct')}%; "
                f"contributors 50/80/90/95%={group_stats.get('contributors_for_50pct')}/{group_stats.get('contributors_for_80pct')}/{group_stats.get('contributors_for_90pct')}/{group_stats.get('contributors_for_95pct')}"
            )
    impacts = compare.get("material_impacts") or []
    if impacts:
        lines.append("- Largest selected impacts:")
        for row in impacts[:8]:
            ident = row.get("identity") or {}
            dims = row.get("dimensions") or {}
            lines.append(f"  - {row.get('metric')}={row.get('value')} · {ident} · {dims}")
    patterns = compare.get("patterns") or []
    if patterns:
        lines.append("- Strong patterns:")
        for row in patterns[:5]:
            lines.append(
                f"  - {row.get('dimension')}={row.get('value')}: rows={row.get('row_share_pct')}%, "
                f"max absolute contribution={row.get('max_abs_contribution_share_pct')}%"
            )
    aggregation_shapes = compare.get("aggregation_structure_patterns") or []
    if aggregation_shapes:
        lines.append("- Aggregation shapes: " + ", ".join(
            f"{r.get('path_shape')}({r.get('share_pct')}%)" for r in aggregation_shapes[:6]
        ))
    changes = compare.get("ref_test_change_patterns") or []
    if changes:
        lines.append("- Ref/Test clues: " + ", ".join(f"{r.get('field')}({r.get('changed_pct')}%)" for r in changes[:8]))
    flags = compare.get("comparison_flag_failures") or []
    if flags:
        lines.append("- Failed compare flags: " + ", ".join(f"{r.get('column')}({r.get('non_true_pct')}%)" for r in flags[:6]))
    diagnostics = compare.get("secondary_numeric_diagnostics") or []
    if diagnostics:
        lines.append("- Secondary numeric clues: " + ", ".join(
            f"{r.get('name')}:p95|x|={r.get('p95_abs')},max|x|={r.get('max_abs')}" for r in diagnostics[:6]
        ))
    relationships = compare.get("metric_relationships") or []
    if relationships:
        lines.append("- Metric relationships: " + ", ".join(
            f"{r.get('left_metric')}↔{r.get('right_metric')}:same-sign={r.get('same_sign_pct')}%,corr={r.get('pearson_correlation')}"
            for r in relationships[:4]
        ))

    if backtesting is not None:
        lines.append(f"- Backtesting rows scanned/matched: {backtesting.get('summary', {}).get('rows_scanned')} / {backtesting.get('summary', {}).get('rows_matching_upstream_dimensions')}")
        for metric, stats in (backtesting.get("concentration") or {}).items():
            lines.append(
                f"- **Backtesting {metric}**: deals material={stats.get('material_deal_count')}; selected={stats.get('selected_count')}; "
                f"coverage={stats.get('selected_coverage_pct')}%; top1/top3/top10={stats.get('top1_share_pct')}%/{stats.get('top3_share_pct')}%/{stats.get('top10_share_pct')}%; "
                f"cancellation={stats.get('material_cancellation_pct')}%; effective contributors≈{stats.get('effective_contributors')}; "
                f"contributors 50/80/90/95%={stats.get('contributors_for_50pct')}/{stats.get('contributors_for_80pct')}/{stats.get('contributors_for_90pct')}/{stats.get('contributors_for_95pct')}"
            )
            for group, group_stats in (stats.get("coverage_groups") or {}).items():
                lines.append(
                    f"  - Backtesting {metric} `{group}`: material={group_stats.get('material_deal_count', group_stats.get('material_count'))}; "
                    f"selected={group_stats.get('selected_count')}; coverage={group_stats.get('selected_coverage_pct')}%; "
                    f"top1/top3/top10={group_stats.get('top1_share_pct')}%/{group_stats.get('top3_share_pct')}%/{group_stats.get('top10_share_pct')}%; "
                    f"contributors 50/80/90/95%={group_stats.get('contributors_for_50pct')}/{group_stats.get('contributors_for_80pct')}/{group_stats.get('contributors_for_90pct')}/{group_stats.get('contributors_for_95pct')}"
                )
        deals = backtesting.get("material_impacts") or []
        if deals:
            lines.append("- Largest deal contributors:")
            for row in deals[:8]:
                lines.append(f"  - {row.get('metric')}={row.get('value')} · {row.get('identity')} · LE={row.get('dimensions')}")
        bt_changes = backtesting.get("ref_test_change_patterns") or []
        if bt_changes:
            lines.append("- Backtesting Ref/Test clues: " + ", ".join(f"{r.get('field')}({r.get('changed_pct')}%)" for r in bt_changes[:8]))
        bt_flags = backtesting.get("comparison_flag_failures") or []
        if bt_flags:
            lines.append("- Backtesting failed compare flags: " + ", ".join(f"{r.get('column')}({r.get('non_true_pct')}%)" for r in bt_flags[:6]))
        bt_diag = backtesting.get("secondary_numeric_diagnostics") or []
        if bt_diag:
            lines.append("- Backtesting secondary numeric clues: " + ", ".join(
                f"{r.get('name')}:p95|x|={r.get('p95_abs')},max|x|={r.get('max_abs')}" for r in bt_diag[:6]
            ))
    return lines


def _hints(evidences: list[dict[str, Any]]) -> dict[str, Any]:
    terms = {"CCR", "CVAR", "GCVAR", "MTF", "MTF00", "EEPE", "exposure"}
    changed_fields: list[str] = []
    failed_flags: list[str] = []
    impacted_legal_entities: list[str] = []
    deals: list[str] = []
    for evidence in evidences:
        for row in evidence.get("ref_test_change_patterns") or []:
            field = str(row.get("field") or "").strip()
            if field:
                changed_fields.append(field)
                terms.add(field)
        for row in evidence.get("comparison_flag_failures") or []:
            col = str(row.get("column") or "").strip()
            if col:
                failed_flags.append(col)
        dims = evidence.get("impacted_dimensions") or {}
        for key, values in dims.items():
            low = str(key).lower()
            if "legalentity" in low or "legal entity" in low:
                impacted_legal_entities.extend(str(v) for v in values[:30])
            if low in {"deal", "dealid", "tradeid"}:
                deals.extend(str(v) for v in values[:50])
    query = "CCR release regression " + " ".join(sorted(terms))
    return {
        "query": query,
        "changed_fields": list(dict.fromkeys(changed_fields))[:30],
        "failed_result_flags": list(dict.fromkeys(failed_flags))[:20],
        "impacted_legal_entities": list(dict.fromkeys(impacted_legal_entities))[:50],
        "impacted_deals": list(dict.fromkeys(deals))[:100],
        "note": "These are retrieval hints for release-pr-forensics, not proof of causality.",
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Prepare compact deterministic evidence for the multi-agent CCR release-validation workflow.")
    p.add_argument("--cvar")
    p.add_argument("--cvar-backtesting")
    p.add_argument("--gcvar")
    p.add_argument("--gcvar-backtesting")
    p.add_argument("--prod-ref")
    p.add_argument("--candidate-ref")
    p.add_argument("--coverage", type=float, default=0.90)
    p.add_argument("--backend", choices=["auto", "polars", "streaming"], default="auto")
    p.add_argument("--output", required=True)
    p.add_argument("--repo", help="GitHub OWNER/REPO for optional PR forensics")
    p.add_argument("--with-prs", action="store_true")
    p.add_argument("--pr-top", type=int, default=12)
    p.add_argument("--inspect-top", type=int, default=3)
    args = p.parse_args()
    if not args.cvar and not args.gcvar:
        raise SystemExit("At least one of --cvar or --gcvar is required.")
    if args.with_prs and (not args.repo or not args.prod_ref or not args.candidate_ref):
        raise SystemExit("--with-prs requires --repo, --prod-ref and --candidate-ref.")

    root = _root()
    output = Path(args.output).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    analyze_script = root / "skills/analyze-large-result-diff/scripts/analyze.py"
    bt_script = root / "skills/backtesting-drilldown/scripts/drilldown.py"
    pr_script = root / "skills/release-pr-forensics/scripts/investigate.py"

    branches: dict[str, dict[str, Any]] = {}
    all_evidence: list[dict[str, Any]] = []
    for kind, source, bt_source in [
        ("cvar", args.cvar, args.cvar_backtesting),
        ("gcvar", args.gcvar, args.gcvar_backtesting),
    ]:
        if not source:
            continue
        compare_out = output / kind
        _run(root, analyze_script, ["--profile", kind, "--input", str(Path(source).expanduser()), "--output", str(compare_out), "--coverage", str(args.coverage), "--backend", args.backend])
        compare = _load(compare_out / "summary.json")
        all_evidence.append(compare)
        branch: dict[str, Any] = {"compare": str(compare_out / "summary.json"), "material": _is_material(compare)}
        bt = None
        if bt_source and branch["material"]:
            bt_out = output / f"{kind}-backtesting"
            _run(root, bt_script, ["--input", str(Path(bt_source).expanduser()), "--evidence", str(compare_out / "summary.json"), "--output", str(bt_out), "--coverage", str(args.coverage), "--backend", args.backend])
            bt = _load(bt_out / "backtesting_summary.json")
            all_evidence.append(bt)
            branch["backtesting"] = str(bt_out / "backtesting_summary.json")
        elif bt_source:
            branch["backtesting_skipped"] = "No material upstream impacts over threshold."
        branches[kind] = branch

    hints = _hints(all_evidence)
    (output / "pr_forensics_hints.json").write_text(json.dumps(hints, indent=2), encoding="utf-8")

    pr_result = None
    if args.with_prs:
        pr_out = output / "pr-forensics"
        _run(
            root,
            pr_script,
            [
                "--repo", args.repo,
                "--base", args.prod_ref,
                "--head", args.candidate_ref,
                "--query", hints["query"],
                "--top", str(args.pr_top),
                "--inspect-top", str(args.inspect_top),
                "--output", str(pr_out),
            ],
        )
        candidates_path = pr_out / "candidates.json"
        if candidates_path.exists():
            pr_result = _load(candidates_path)

    cvar = _load(Path(branches["cvar"]["compare"])) if "cvar" in branches else None
    cvar_bt = _load(Path(branches["cvar"]["backtesting"])) if branches.get("cvar", {}).get("backtesting") else None
    gcvar = _load(Path(branches["gcvar"]["compare"])) if "gcvar" in branches else None
    gcvar_bt = _load(Path(branches["gcvar"]["backtesting"])) if branches.get("gcvar", {}).get("backtesting") else None

    lines = [
        "# CCR Release Validation — compact workflow evidence",
        "",
        "> Generated deterministically. Raw compare/backtesting CSVs are intentionally not embedded.",
        "",
        f"- Production ref: `{args.prod_ref or 'not supplied'}`",
        f"- Candidate ref: `{args.candidate_ref or 'not supplied'}`",
        f"- Coverage target: {100 * args.coverage:.1f}% of absolute material movement per metric",
        "- Materiality: strict `abs(gap) > 10,000`; MTF00 is interpreted in row currency, EEPE-in-EUR in EUR.",
        "",
        *_compact_section("CVAR", cvar, cvar_bt),
        "",
        *_compact_section("GCVAR", gcvar, gcvar_bt),
        "",
        "## Root-cause / PR-forensics hints",
        f"- Query: `{hints['query']}`",
        f"- Changed Ref/Test fields: {', '.join(hints['changed_fields']) or 'none detected'}",
        f"- Failed result flags: {', '.join(hints['failed_result_flags']) or 'none detected'}",
        f"- Impacted Legal Entities: {', '.join(hints['impacted_legal_entities']) or 'none detected'}",
        f"- Impacted deals: {', '.join(hints['impacted_deals'][:30]) or 'none available'}",
    ]
    if pr_result is not None:
        lines.extend(["", "## Candidate PRs (retrieval relevance, not causality)"])
        for row in (pr_result.get("candidates") or [])[:10]:
            lines.append(f"- PR #{row.get('pr')} · score={row.get('relevance_score')} · {row.get('title')} · signals={row.get('signals')}")
    lines.extend([
        "",
        "## LLM instruction",
        "Explain observed impacts and patterns first. Use PR candidates only to form hypotheses. Call deeper PR diff inspection or propose a discriminating rerun before naming a confirmed culprit.",
    ])
    (output / "workflow_context.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "workflow": "ccr-release-validation",
        "production_ref": args.prod_ref,
        "candidate_ref": args.candidate_ref,
        "coverage": args.coverage,
        "branches": branches,
        "pr_forensics": str(output / "pr-forensics") if args.with_prs else None,
        "artifacts": ["workflow_context.md", "pr_forensics_hints.json"],
    }
    (output / "workflow_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "output": str(output), "context": str(output / "workflow_context.md"), "branches": branches, "prs_prefetched": bool(pr_result)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
