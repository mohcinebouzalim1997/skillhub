from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from skillhub.runtime.ccr import branch_signature_similarity, mtf_eepe_relationship


def _root() -> Path:
    configured = os.environ.get("SKILLHUB_ROOT")
    if configured:
        return Path(configured).resolve()
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "skillhub.config.yaml").exists() and (parent / "skills").is_dir():
            return parent
    raise SystemExit("Cannot locate SkillHub root. Run this through `skillhub run prepare-ccr-release-evidence`.")


def _run(root: Path, script: Path, args: list[str]) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root) + (os.pathsep + env.get("PYTHONPATH", "") if env.get("PYTHONPATH") else "")
    proc = subprocess.run([sys.executable, str(script), *args], cwd=Path.cwd(), env=env, text=True)
    if proc.returncode:
        raise SystemExit(proc.returncode)


def _load(path: Path | str | None) -> dict[str, Any] | None:
    if not path:
        return None
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _is_material(evidence: dict[str, Any] | None) -> bool:
    if not evidence:
        return False
    for stats in (evidence.get("metric_statistics") or {}).values():
        if int((stats or {}).get("material_count") or 0) > 0:
            return True
    return False


def _metric_lines(label: str, evidence: dict[str, Any], metric: str) -> list[str]:
    stats = (evidence.get("metric_statistics") or {}).get(metric) or {}
    impacts = [row for row in (evidence.get("material_impacts") or []) if row.get("metric") == metric]
    lines = [f"### {label} · {metric}"]
    if not stats or not int(stats.get("material_count") or 0):
        lines.append("- No material impact over the strict 10k threshold.")
        return lines
    lines.append(
        f"- Material={stats.get('material_count')}; selected={stats.get('selected_count')}; "
        f"coverage={stats.get('selected_coverage_pct')}%; threshold captures={stats.get('threshold_capture_pct_of_all_abs_movement')}% of absolute movement."
    )
    lines.append(
        f"- Concentration top1/top3/top10={stats.get('top1_share_pct')}%/{stats.get('top3_share_pct')}%/{stats.get('top10_share_pct')}%; "
        f"contributors for 50/80/90/95%={stats.get('contributors_for_50pct')}/{stats.get('contributors_for_80pct')}/{stats.get('contributors_for_90pct')}/{stats.get('contributors_for_95pct')}; "
        f"cancellation={stats.get('material_cancellation_pct')}%."
    )
    for group, gs in (stats.get("coverage_groups") or {}).items():
        lines.append(
            f"  - `{group}`: material={gs.get('material_count')}; selected={gs.get('selected_count')}; coverage={gs.get('selected_coverage_pct')}%; "
            f"contributors 50/80/90/95%={gs.get('contributors_for_50pct')}/{gs.get('contributors_for_80pct')}/{gs.get('contributors_for_90pct')}/{gs.get('contributors_for_95pct')}"
        )
    if impacts:
        lines.append("- Largest selected impacts:")
        for row in impacts[:8]:
            lines.append(f"  - {row.get('value')} · {row.get('identity')} · {row.get('dimensions')}")
    return lines


def _backtesting_lines(label: str, bt: dict[str, Any] | None, metric: str) -> list[str]:
    lines = [f"#### {label} backtesting · {metric}"]
    if bt is None:
        lines.append("- Not run / not supplied.")
        return lines
    stats = (bt.get("concentration") or {}).get(metric) or {}
    if not stats or not int(stats.get("material_deal_count") or 0):
        lines.append("- No material deal-level impact over threshold on the filtered Legal Entities.")
        return lines
    lines.append(
        f"- Material deals={stats.get('material_deal_count')}; selected={stats.get('selected_count')}; coverage={stats.get('selected_coverage_pct')}%; "
        f"top1/top3/top10={stats.get('top1_share_pct')}%/{stats.get('top3_share_pct')}%/{stats.get('top10_share_pct')}%."
    )
    rows = [r for r in (bt.get("material_impacts") or []) if r.get("metric") == metric]
    for row in rows[:10]:
        lines.append(f"  - {row.get('value')} · {row.get('identity')} · LE={row.get('dimensions')}")
    families = [r for r in (bt.get("deal_family_patterns") or []) if r.get("metric") == metric]
    if families:
        lines.append("- Deal-family mix: " + ", ".join(f"{r.get('deal_family')}={r.get('selected_abs_share_pct')}%" for r in families))
    return lines


def _error_lines(title: str, evidence: dict[str, Any] | None, metric: str | None = None) -> list[str]:
    suffix = f" · {metric}" if metric else ""
    lines = [f"#### {title}{suffix}"]
    if evidence is None:
        lines.append("- Not run / not supplied.")
        return lines
    s = evidence.get("summary") or {}
    lines.append(
        f"- Asymmetric errors={s.get('asymmetric_error_rows')}; impacted LEs linked={s.get('impacted_legal_entities_with_asymmetric_error')}/{s.get('impacted_legal_entities_requested')}; "
        f"impacted deals linked={s.get('impacted_deals_with_asymmetric_error')}/{s.get('impacted_deals_requested')}."
    )
    if metric:
        link = (evidence.get("metric_linkage") or {}).get(metric) or {}
        if link:
            lines.append(
                f"- Metric scope: asymmetric rows={link.get('asymmetric_error_rows')}; "
                f"LE linked={link.get('linked_legal_entities')}/{link.get('requested_legal_entities')}; "
                f"deals linked={link.get('linked_deals')}/{link.get('requested_deals')}; "
                f"masters linked={link.get('linked_masters')}/{link.get('requested_masters')}."
            )
            categories = link.get("error_categories") or {}
            if categories:
                lines.append("- Metric-linked error categories: " + ", ".join(f"{k}={v}" for k, v in list(categories.items())[:8]))
    cats = evidence.get("error_category_counts") or {}
    states = evidence.get("error_state_counts") or {}
    if states:
        lines.append("- Error states: " + ", ".join(f"{k}={v}" for k, v in list(states.items())[:8]))
    if cats:
        lines.append("- Overall error categories: " + ", ".join(f"{k}={v}" for k, v in sorted(cats.items(), key=lambda x: x[1], reverse=True)[:8]))
    return lines


def _hints(evidences: list[dict[str, Any]]) -> dict[str, Any]:
    terms = {"CCR", "CVAR", "GCVAR", "MTF", "MTF00", "EEPE", "exposure"}
    changed_fields: list[str] = []
    failed_flags: list[str] = []
    impacted_legal_entities: list[str] = []
    deals: list[str] = []
    error_categories: list[str] = []
    deal_families: list[str] = []
    for evidence in evidences:
        for row in evidence.get("ref_test_change_patterns") or []:
            field = str(row.get("field") or "").strip()
            if field:
                changed_fields.append(field); terms.add(field)
        for row in evidence.get("comparison_flag_failures") or []:
            col = str(row.get("column") or "").strip()
            if col:
                failed_flags.append(col)
        for row in evidence.get("deal_family_patterns") or []:
            family = str(row.get("deal_family") or "").strip()
            if family:
                deal_families.append(family); terms.add(family)
        for category, count in (evidence.get("error_category_counts") or {}).items():
            if int(count or 0) > 0:
                error_categories.append(str(category)); terms.add(str(category))
        dims = evidence.get("impacted_dimensions") or {}
        for key, values in dims.items():
            low = str(key).lower()
            if "legalentity" in low or "legal entity" in low:
                impacted_legal_entities.extend(str(v) for v in values[:50])
            if low in {"deal", "dealid", "tradeid"}:
                deals.extend(str(v) for v in values[:100])
    query = "CCR release regression " + " ".join(sorted(terms))
    return {
        "query": query,
        "changed_fields": list(dict.fromkeys(changed_fields))[:30],
        "failed_result_flags": list(dict.fromkeys(failed_flags))[:20],
        "error_categories": list(dict.fromkeys(error_categories))[:20],
        "deal_families": list(dict.fromkeys(deal_families))[:10],
        "impacted_legal_entities": list(dict.fromkeys(impacted_legal_entities))[:100],
        "impacted_deals": list(dict.fromkeys(deals))[:200],
        "note": "Retrieval hints for release-pr-forensics, never proof of causality.",
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Prepare compact XLSX-aware evidence for the CCR release-validation multi-agent workflow.")
    p.add_argument("--cvar", help="CcrMetrics.xlsx")
    p.add_argument("--cvar-backtesting", help="CVAR backtesting result workbook")
    p.add_argument("--cvar-errors", help="CVAR ErrorByTrade.xlsx")
    p.add_argument("--cvar-backtesting-errors", help="CVAR backtesting ErrorByTrade.xlsx")
    p.add_argument("--gcvar", help="CcrMetrics_Gcvar.xlsx")
    p.add_argument("--gcvar-backtesting", help="GCVAR backtesting result workbook")
    p.add_argument("--gcvar-errors", help="GCVAR ErrorByTrade.xlsx")
    p.add_argument("--gcvar-backtesting-errors", help="GCVAR backtesting ErrorByTrade.xlsx")
    p.add_argument("--prod-ref")
    p.add_argument("--candidate-ref")
    p.add_argument("--coverage", type=float, default=0.90)
    p.add_argument("--backend", choices=["auto", "polars", "streaming"], default="auto")
    p.add_argument("--gcvar-deep", choices=["auto", "always", "never"], default="auto", help="Auto skips redundant GCVAR backtesting/error drilldown when result signature mirrors CVAR.")
    p.add_argument("--output", required=True)
    p.add_argument("--repo", help="GitHub OWNER/REPO for optional PR forensics")
    p.add_argument("--with-prs", action="store_true")
    p.add_argument("--pr-top", type=int, default=12)
    p.add_argument("--inspect-top", type=int, default=3)
    args = p.parse_args()
    workflow_started = time.perf_counter()
    if not args.cvar and not args.gcvar:
        raise SystemExit("At least one of --cvar or --gcvar is required.")
    if args.with_prs and (not args.repo or not args.prod_ref or not args.candidate_ref):
        raise SystemExit("--with-prs requires --repo, --prod-ref and --candidate-ref.")

    root = _root()
    output = Path(args.output).expanduser().resolve(); output.mkdir(parents=True, exist_ok=True)
    analyze_script = root / "skills/analyze-large-result-diff/scripts/analyze.py"
    bt_script = root / "skills/backtesting-drilldown/scripts/drilldown.py"
    error_script = root / "skills/analyze-ccr-errors/scripts/analyze_errors.py"
    pr_script = root / "skills/release-pr-forensics/scripts/investigate.py"

    branches: dict[str, dict[str, Any]] = {}
    all_evidence: list[dict[str, Any]] = []
    cvar_compare: dict[str, Any] | None = None
    gcvar_similarity: dict[str, Any] | None = None

    branch_inputs = {
        "cvar": (args.cvar, args.cvar_backtesting, args.cvar_errors, args.cvar_backtesting_errors),
        "gcvar": (args.gcvar, args.gcvar_backtesting, args.gcvar_errors, args.gcvar_backtesting_errors),
    }

    for kind in ("cvar", "gcvar"):
        source, bt_source, error_source, bt_error_source = branch_inputs[kind]
        if not source:
            continue
        compare_out = output / kind
        _run(root, analyze_script, ["--profile", kind, "--input", str(Path(source).expanduser()), "--output", str(compare_out), "--coverage", str(args.coverage), "--backend", args.backend])
        compare = _load(compare_out / "summary.json") or {}
        all_evidence.append(compare)
        branch: dict[str, Any] = {"compare": str(compare_out / "summary.json"), "material": _is_material(compare)}
        if kind == "cvar":
            cvar_compare = compare
        elif cvar_compare:
            gcvar_similarity = branch_signature_similarity(cvar_compare, compare)
            branch["cvar_similarity"] = gcvar_similarity

        deep = branch["material"]
        if kind == "gcvar":
            if args.gcvar_deep == "never":
                deep = False; branch["deep_drilldown_skipped"] = "--gcvar-deep never"
            elif args.gcvar_deep == "auto" and gcvar_similarity and gcvar_similarity.get("same_issue_likely"):
                deep = False
                branch["deep_drilldown_skipped"] = "GCVAR result signature strongly mirrors CVAR; reuse CVAR root-cause path unless independent confirmation is requested."
            elif args.gcvar_deep == "always":
                deep = branch["material"]

        bt = None
        if bt_source and deep:
            bt_out = output / f"{kind}-backtesting"
            _run(root, bt_script, ["--input", str(Path(bt_source).expanduser()), "--evidence", str(compare_out / "summary.json"), "--output", str(bt_out), "--coverage", str(args.coverage), "--backend", args.backend])
            bt = _load(bt_out / "backtesting_summary.json")
            if bt:
                all_evidence.append(bt); branch["backtesting"] = str(bt_out / "backtesting_summary.json")
        elif bt_source and branch["material"] and "deep_drilldown_skipped" not in branch:
            branch["backtesting_skipped"] = "No deep drilldown required."
        elif bt_source and not branch["material"]:
            branch["backtesting_skipped"] = "No material upstream impacts over threshold."

        err = None
        if error_source and deep:
            err_out = output / f"{kind}-errors"
            _run(root, error_script, ["--input", str(Path(error_source).expanduser()), "--evidence", str(compare_out / "summary.json"), "--output", str(err_out)])
            err = _load(err_out / "error_summary.json")
            if err:
                all_evidence.append(err); branch["errors"] = str(err_out / "error_summary.json")

        bt_err = None
        if bt_error_source and bt and deep:
            bt_err_out = output / f"{kind}-backtesting-errors"
            _run(root, error_script, ["--input", str(Path(bt_error_source).expanduser()), "--evidence", str(output / f"{kind}-backtesting" / "backtesting_summary.json"), "--output", str(bt_err_out)])
            bt_err = _load(bt_err_out / "error_summary.json")
            if bt_err:
                all_evidence.append(bt_err); branch["backtesting_errors"] = str(bt_err_out / "error_summary.json")

        relation = mtf_eepe_relationship(compare, backtesting=bt) if compare else {}
        branch["mtf00_eepe_relationship"] = relation
        branches[kind] = branch

    hints = _hints(all_evidence)
    (output / "pr_forensics_hints.json").write_text(json.dumps(hints, indent=2), encoding="utf-8")

    pr_result = None
    if args.with_prs:
        pr_out = output / "pr-forensics"
        _run(root, pr_script, ["--repo", args.repo, "--base", args.prod_ref, "--head", args.candidate_ref, "--query", hints["query"], "--top", str(args.pr_top), "--inspect-top", str(args.inspect_top), "--output", str(pr_out)])
        pr_result = _load(pr_out / "candidates.json")

    def branch_evidence(kind: str, key: str) -> dict[str, Any] | None:
        return _load(branches.get(kind, {}).get(key))

    cvar = branch_evidence("cvar", "compare"); cvar_bt = branch_evidence("cvar", "backtesting")
    cvar_err = branch_evidence("cvar", "errors"); cvar_bt_err = branch_evidence("cvar", "backtesting_errors")
    gcvar = branch_evidence("gcvar", "compare"); gcvar_bt = branch_evidence("gcvar", "backtesting")
    gcvar_err = branch_evidence("gcvar", "errors"); gcvar_bt_err = branch_evidence("gcvar", "backtesting_errors")

    lines = [
        "# CCR Release Validation — compact workflow evidence",
        "",
        "> Generated deterministically from local XLSX/CSV files. Raw compare/backtesting CSVs are intentionally not embedded; raw XLSX workbooks are also never embedded in LLM context.",
        "",
        f"- Production ref: `{args.prod_ref or 'not supplied'}`",
        f"- Candidate ref: `{args.candidate_ref or 'not supplied'}`",
        f"- Coverage target: {100 * args.coverage:.1f}% of absolute material movement per metric",
        "- Materiality: strict `abs(gap) > 10,000`; MTF00 is interpreted in row currency, EEPE-in-EUR in EUR.",
        "- Workbook semantics: `Details`=matched Ref/Test; `Non Ref`=Test-only; `Non Test`=Ref-only. Side-only rows are converted into signed structural impacts.",
        "",
        "# CVAR — investigate MTF00 first",
    ]
    if cvar:
        lines += _metric_lines("CVAR", cvar, "Mtf00Gap")
        lines += _backtesting_lines("CVAR", cvar_bt, "Mtf00Gap")
        lines += _error_lines("CVAR result errors", cvar_err, "Mtf00Gap")
        lines += _error_lines("CVAR backtesting errors", cvar_bt_err, "Mtf00Gap")
        lines += ["", "## CVAR — then EEPE"]
        lines += _metric_lines("CVAR", cvar, "EepeInEurGap")
        lines += _backtesting_lines("CVAR", cvar_bt, "EepeInEurGap")
        lines += _error_lines("CVAR result errors", cvar_err, "EepeInEurGap")
        lines += _error_lines("CVAR backtesting errors", cvar_bt_err, "EepeInEurGap")
        rel = branches.get("cvar", {}).get("mtf00_eepe_relationship") or {}
        lines += [
            f"- MTF00↔EEPE routing classification: **{rel.get('classification')}**",
            f"- EEPE absolute share on MTF00-selected rows: {rel.get('eepe_abs_share_on_mtf00_selected_rows_pct')}%",
            f"- EEPE absolute share on MTF00-selected deals: {rel.get('eepe_abs_share_on_mtf00_selected_deals_pct')}%",
            "- Absence of MTF00 overlap does NOT rule out an MTF-driven EEPE change because other MTFs are not visible in this compare output.",
        ]
    else:
        lines.append("- CVAR not supplied.")

    lines += ["", "# GCVAR — first check whether CVAR already explains the signature"]
    if gcvar:
        if gcvar_similarity:
            lines.append(
                f"- CVAR/GCVAR signature similarity={gcvar_similarity.get('score')} (LE Jaccard={gcvar_similarity.get('legal_entity_jaccard')}); "
                f"same issue likely={gcvar_similarity.get('same_issue_likely')}."
            )
        if branches.get("gcvar", {}).get("deep_drilldown_skipped"):
            lines.append(f"- Deep GCVAR drilldown skipped for performance: {branches['gcvar']['deep_drilldown_skipped']}")
        lines += _metric_lines("GCVAR", gcvar, "Mtf00Gap")
        lines += _backtesting_lines("GCVAR", gcvar_bt, "Mtf00Gap")
        lines += _error_lines("GCVAR result errors", gcvar_err, "Mtf00Gap")
        lines += _error_lines("GCVAR backtesting errors", gcvar_bt_err, "Mtf00Gap")
        lines += ["", "## GCVAR — EEPE"]
        lines += _metric_lines("GCVAR", gcvar, "EepeInEurGap")
        lines += _backtesting_lines("GCVAR", gcvar_bt, "EepeInEurGap")
        lines += _error_lines("GCVAR result errors", gcvar_err, "EepeInEurGap")
        lines += _error_lines("GCVAR backtesting errors", gcvar_bt_err, "EepeInEurGap")
        rel = branches.get("gcvar", {}).get("mtf00_eepe_relationship") or {}
        lines += [f"- MTF00↔EEPE routing classification: **{rel.get('classification')}**"]
    else:
        lines.append("- GCVAR not supplied.")

    lines += [
        "",
        "# Root-cause / PR-forensics hints",
        f"- Query: `{hints['query']}`",
        f"- Changed Ref/Test fields: {', '.join(hints['changed_fields']) or 'none detected'}",
        f"- Error categories: {', '.join(hints['error_categories']) or 'none detected'}",
        f"- Deal families: {', '.join(hints['deal_families']) or 'none detected'}",
        f"- Impacted Legal Entities: {', '.join(hints['impacted_legal_entities'][:40]) or 'none detected'}",
        f"- Impacted deals: {', '.join(hints['impacted_deals'][:40]) or 'none available'}",
    ]
    workflow_elapsed = round(time.perf_counter() - workflow_started, 6)
    lines += ["", "# Deterministic runtime", f"- Total pre-LLM workflow time: {workflow_elapsed} s"]
    if pr_result:
        lines += ["", "## Candidate PRs — relevance only, not causality"]
        for row in (pr_result.get("candidates") or [])[:10]:
            lines.append(f"- PR #{row.get('pr')} · score={row.get('relevance_score')} · {row.get('title')} · signals={row.get('signals')}")
    lines += [
        "",
        "# LLM synthesis contract",
        "1. Explain MTF00 impacts first: size → LE → deals → deal family → errors → code candidates.",
        "2. Explain EEPE second and explicitly decide whether its pattern is strongly/partially/not explained by the MTF00 signature. Remember unseen MTFs can still drive EEPE.",
        "3. For GCVAR, reuse the CVAR explanation when the deterministic similarity gate says the issue is mirrored; do not repeat expensive drilldowns unless evidence conflicts.",
        "4. Search PRs only after data/error patterns are established. A candidate PR is not a culprit until its diff matches the mechanism and a discriminating test/reproduction supports it.",
        "5. Final classification per material issue: `expected_dev_change`, `suspected_bug`, or `inconclusive`. If expected, justify the intended code behavior and why the observed impact follows. If unsure, say inconclusive.",
    ]
    (output / "workflow_context.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    routing = {
        "analysis_order": ["cvar.mtf00", "cvar.eepe", "gcvar.same-issue-precheck", "gcvar.mtf00", "gcvar.eepe", "errors", "pr-forensics", "synthesis"],
        "cvar_mtf00_eepe": branches.get("cvar", {}).get("mtf00_eepe_relationship"),
        "gcvar_mtf00_eepe": branches.get("gcvar", {}).get("mtf00_eepe_relationship"),
        "gcvar_vs_cvar": gcvar_similarity,
    }
    (output / "root_cause_routing.json").write_text(json.dumps(routing, indent=2), encoding="utf-8")
    manifest = {
        "schema_version": 2,
        "workflow": "ccr-release-validation",
        "production_ref": args.prod_ref,
        "candidate_ref": args.candidate_ref,
        "coverage": args.coverage,
        "elapsed_seconds": workflow_elapsed,
        "branches": branches,
        "routing": "root_cause_routing.json",
        "pr_forensics": str(output / "pr-forensics") if args.with_prs else None,
        "artifacts": ["workflow_context.md", "workflow_manifest.json", "root_cause_routing.json", "pr_forensics_hints.json"],
    }
    (output / "workflow_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "output": str(output), "context": str(output / "workflow_context.md"), "branches": branches, "gcvar_similarity": gcvar_similarity, "prs_prefetched": bool(pr_result), "elapsed_seconds": workflow_elapsed}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
