from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from skillhub.runtime.artifacts import ensure_output_dir, file_metadata, write_json
from skillhub.runtime.config import apply_metric_coverage_override, apply_metric_threshold_overrides, load_profile
from skillhub.runtime.csv_engine import (
    detect_layout,
    detect_patterns,
    enrich_rows,
    resolve_columns,
    resolve_metric_specs,
    select_material_rows,
)
from skillhub.runtime.diagnostics import (
    summarize_aggregation_structure,
    summarize_metric_relationships,
    summarize_numeric_columns,
    summarize_ref_test_changes,
    summarize_result_flags,
)
from skillhub.runtime.evidence import compact_agent_markdown, write_evidence
from skillhub.runtime.profiling import StageTimer


def _write_material_csv(path: Path, rows: list[dict]) -> None:
    flattened = []
    for row in rows:
        identity = row.get("identity") or {}
        dimensions = row.get("dimensions") or {}
        selected_metrics = set(row.get("selected_metrics") or [])
        for metric, value in (row.get("metrics") or {}).items():
            if selected_metrics and metric not in selected_metrics:
                continue
            flattened.append(
                {
                    "row_number": row.get("row_number"),
                    "metric": metric,
                    "value": value,
                    "selection_score": row.get("selection_score"),
                    **{f"id.{k}": v for k, v in identity.items()},
                    **{f"dim.{k}": v for k, v in dimensions.items()},
                }
            )
    fields = sorted({k for row in flattened for k in row}) if flattened else ["row_number", "metric", "value"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(flattened)


def _explicit_dimension_values(enriched: list[dict[str, str]], columns: list[str]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for column in columns:
        values = [str(row.get(column, "")).strip() for row in enriched]
        values = [value for value in values if value]
        if values:
            result[column] = list(dict.fromkeys(values))[:500]
    return result


def analyze(args: argparse.Namespace) -> dict:
    timer = StageTimer()
    input_path = Path(args.input).expanduser().resolve()
    out = ensure_output_dir(args.output)
    profile = load_profile(args.profile)
    profile = apply_metric_threshold_overrides(profile, args.threshold)
    profile = apply_metric_coverage_override(profile, args.coverage)

    with timer.measure("inspect_header"):
        layout = detect_layout(input_path, args.delimiter)
        configured_metrics = [row for row in profile.get("metrics") or [] if isinstance(row, dict) and row.get("name")]
        present_metrics, missing_metrics = resolve_metric_specs(layout.columns, configured_metrics)
        if not present_metrics:
            expected = [row.get("name") for row in configured_metrics]
            raise SystemExit(f"No configured gap metric is present. Expected one of: {expected}")

        identity_candidates = [*(profile.get("identity_candidates") or []), *(args.identity or [])]
        dimension_candidates = [*(profile.get("dimension_candidates") or []), *(args.dimension or [])]
        identity_columns = resolve_columns(layout.columns, identity_candidates)
        dimension_columns = resolve_columns(layout.columns, dimension_candidates)

    with timer.measure("material_impact_scan"):
        result = select_material_rows(
            input_path,
            metrics=present_metrics,
            identity_columns=identity_columns,
            dimension_columns=dimension_columns,
            delimiter=layout.delimiter,
            top_k=int((profile.get("selection") or {}).get("top_k") or args.top_k),
            backend=args.backend,
        )

    material_rows = result["material_rows"]
    selected_numbers = {int(row["row_number"]) for row in material_rows}
    pattern_cfg = profile.get("patterns") or {}
    with timer.measure("candidate_enrichment"):
        enriched_columns, enriched = enrich_rows(
            input_path,
            selected_numbers,
            delimiter=layout.delimiter,
            max_columns=int(args.max_enrichment_columns or pattern_cfg.get("max_enrichment_columns") or 120),
            backend=args.backend,
        )

    with timer.measure("pattern_detection"):
        metric_names = [str(row["name"]) for row in present_metrics]
        source_metric_columns = {str(row.get("source_name") or row["name"]) for row in present_metrics}
        patterns, impacted_dimensions = detect_patterns(
            material_rows,
            enriched,
            metric_names,
            excluded=set([*source_metric_columns, *identity_columns]),
            preferred_dimensions=dimension_columns,
            max_cardinality=int(pattern_cfg.get("max_cardinality") or 50),
            min_row_share=float(args.pattern_min_share if args.pattern_min_share is not None else pattern_cfg.get("min_row_share") or 0.5),
            min_abs_contribution_share=float(pattern_cfg.get("min_abs_contribution_share") or 0.2),
        )
        # Always expose configured dimensions from selected rows.  The selected set is already
        # impact/coverage-reduced, so these values are safe to pass to downstream backtesting.
        for column, values in _explicit_dimension_values(enriched, dimension_columns).items():
            impacted_dimensions[column] = list(dict.fromkeys([*(impacted_dimensions.get(column) or []), *values]))[:500]
        # AggregationLevel is normally an identity (high-cardinality), not a categorical pattern
        # dimension.  Preserve the selected identifiers explicitly for the report/workflow while
        # keeping backtesting free to ignore exact master-level strings.
        aggregation_identity_columns = [c for c in identity_columns if "aggregation" in c.lower()]
        for column, values in _explicit_dimension_values(enriched, aggregation_identity_columns).items():
            impacted_dimensions[column] = list(dict.fromkeys([*(impacted_dimensions.get(column) or []), *values]))[:500]

        aggregation_structure_patterns = summarize_aggregation_structure(enriched)
        ref_test_changes = summarize_ref_test_changes(enriched)
        result_flag_failures = summarize_result_flags(enriched)
        secondary_numeric_diagnostics = summarize_numeric_columns(
            enriched,
            list(profile.get("diagnostic_numeric_columns") or []),
        )
        metric_relationships = summarize_metric_relationships(material_rows, present_metrics)

    impacts = []
    for row in material_rows:
        selected_metrics = set(row.get("selected_metrics") or [])
        for metric, value in (row.get("metrics") or {}).items():
            if selected_metrics and metric not in selected_metrics:
                continue
            impacts.append(
                {
                    "row_number": row["row_number"],
                    "metric": metric,
                    "value": value,
                    "selection_score": row.get("selection_score"),
                    "identity": row.get("identity") or {},
                    "dimensions": row.get("dimensions") or {},
                }
            )
    impacts.sort(key=lambda row: abs(float(row.get("value") or 0.0)), reverse=True)

    metric_policy = {
        str(metric["name"]): {
            "source_column": metric.get("source_name"),
            "absolute_threshold": metric.get("absolute_threshold"),
            "threshold_operator": ">",
            "coverage_target": metric.get("coverage_target"),
            "unit": metric.get("unit"),
        }
        for metric in present_metrics
    }
    summary = {
        "profile": profile.get("id", args.profile),
        "backend": result["backend"],
        "rows_scanned": result["rows_scanned"],
        "selected_material_rows": len(material_rows),
        "material_rows": len(material_rows),  # backward-compatible alias
        "selected_metric_impacts": len(impacts),
        "material_metric_impacts": len(impacts),  # backward-compatible alias
        "metrics": ", ".join(metric_names),
        "materiality_rule": "strict abs(gap) > configured threshold; then retain largest contributors until configured absolute-gap coverage is reached",
        "identity_columns": ", ".join(identity_columns) or "row number",
        "dimension_columns": ", ".join(dimension_columns) or "none configured/present",
        "mtf00_threshold_semantics": (profile.get("currency_columns") or {}).get("mtf00_threshold_semantics", "configured native unit"),
        "eepe_in_eur_threshold_semantics": (profile.get("currency_columns") or {}).get("eepe_in_eur_threshold_semantics", "EUR"),
    }
    warnings = list(result.get("warnings") or [])
    if missing_metrics:
        warnings.append(f"Configured metrics not present and skipped: {', '.join(missing_metrics)}")
    if len(enriched_columns) >= int(pattern_cfg.get("max_enrichment_columns") or 120) and len(layout.columns) > len(enriched_columns):
        warnings.append(f"Pattern enrichment was capped at {len(enriched_columns)} of {len(layout.columns)} columns.")

    evidence = {
        "schema_version": "1.0",
        "evidence_type": "large-result-diff",
        "title": f"{str(profile.get('name') or args.profile)} material impact evidence",
        "source": {
            **file_metadata(input_path),
            "delimiter": layout.delimiter,
            "columns_total": len(layout.columns),
            "columns_first_pass": list(dict.fromkeys([*identity_columns, *dimension_columns, *[str(m.get('source_name') or m['name']) for m in present_metrics]])),
        },
        "summary": summary,
        "metric_policy": metric_policy,
        "metric_statistics": result.get("metric_stats") or {},
        "material_impacts": impacts,
        "patterns": patterns,
        "impacted_dimensions": impacted_dimensions,
        "aggregation_structure_patterns": aggregation_structure_patterns,
        "ref_test_change_patterns": ref_test_changes,
        "comparison_flag_failures": result_flag_failures,
        "secondary_numeric_diagnostics": secondary_numeric_diagnostics,
        "metric_relationships": metric_relationships,
        "timings": timer.timings,
        "warnings": warnings,
    }
    write_evidence(out / "summary.json", evidence)
    write_json(
        out / "patterns.json",
        {
            "patterns": patterns,
            "impacted_dimensions": impacted_dimensions,
            "aggregation_structure_patterns": aggregation_structure_patterns,
            "ref_test_change_patterns": ref_test_changes,
            "comparison_flag_failures": result_flag_failures,
            "secondary_numeric_diagnostics": secondary_numeric_diagnostics,
            "metric_relationships": metric_relationships,
        },
    )
    _write_material_csv(out / "material_impacts.csv", material_rows)
    (out / "agent_context.md").write_text(compact_agent_markdown(evidence), encoding="utf-8")
    write_json(
        out / "run_manifest.json",
        {
            "command_profile": args.profile,
            "input": file_metadata(input_path),
            "metric_policy": metric_policy,
            "artifacts": ["summary.json", "patterns.json", "material_impacts.csv", "agent_context.md"],
            "timings": timer.timings,
        },
    )
    return evidence


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Reduce a huge result-comparison CSV into compact deterministic evidence.")
    p.add_argument("--profile", default="cvar", help="Built-in profile name (cvar/gcvar) or YAML path")
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--threshold", action="append", help="Override materiality threshold, e.g. 'EepeInEur Gap=25000'. Aliases are accepted.")
    p.add_argument("--coverage", type=float, help="Override per-metric absolute-impact coverage target, e.g. 0.8 or 0.9")
    p.add_argument("--top-k", type=int, default=50, help="Fallback top-K used only for metrics without a materiality threshold")
    p.add_argument("--backend", choices=["auto", "polars", "streaming"], default="auto")
    p.add_argument("--delimiter")
    p.add_argument("--identity", action="append", help="Additional identity/key column to preserve; repeatable")
    p.add_argument("--dimension", action="append", help="Additional categorical dimension to inspect; repeatable")
    p.add_argument("--max-enrichment-columns", type=int)
    p.add_argument("--pattern-min-share", type=float, help="Minimum material-row share for a frequency pattern, e.g. 0.5")
    return p


def main() -> int:
    args = parser().parse_args()
    evidence = analyze(args)
    print(
        json.dumps(
            {
                "ok": True,
                "output": str(Path(args.output).resolve()),
                "rows_scanned": evidence["summary"]["rows_scanned"],
                "selected_material_rows": evidence["summary"]["selected_material_rows"],
                "backend": evidence["summary"]["backend"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
