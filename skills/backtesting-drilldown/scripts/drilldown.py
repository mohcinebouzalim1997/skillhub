from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

from skillhub.runtime.artifacts import ensure_output_dir, file_metadata, write_json
from skillhub.runtime.config import apply_metric_coverage_override, apply_metric_threshold_overrides, load_profile
from skillhub.runtime.csv_engine import (
    detect_layout,
    enrich_selected_deals,
    filter_and_rank_deals,
    resolve_columns,
    resolve_metric_specs,
)
from skillhub.runtime.diagnostics import summarize_numeric_columns, summarize_ref_test_changes, summarize_result_flags
from skillhub.runtime.evidence import compact_agent_markdown, load_evidence, write_evidence
from skillhub.runtime.profiling import StageTimer
from skillhub.runtime.workbook import is_excel, materialize_ccr_comparison_workbook
from skillhub.runtime.ccr import summarize_deal_families, mtf_eepe_relationship


def _resolve_filters(
    columns: list[str],
    evidence: dict,
    profile: dict,
    manual_maps: list[str] | None = None,
    manual_filters: list[str] | None = None,
) -> tuple[dict[str, set[str]], dict[str, str]]:
    impacted = evidence.get("impacted_dimensions") or {}
    filters: dict[str, set[str]] = {}
    mapping: dict[str, str] = {}
    explicit_map: dict[str, str] = {}
    for raw in manual_maps or []:
        if "=" not in raw:
            raise SystemExit(f"Invalid --filter-map '{raw}'. Use LOGICAL=CSV_COLUMN")
        logical, actual = raw.split("=", 1)
        explicit_map[logical] = actual

    for logical, cfg in (profile.get("filter_dimensions") or {}).items():
        if not bool(cfg.get("use_upstream_filter", True)):
            continue
        aliases = list(cfg.get("aliases") or [])
        candidates = [explicit_map[logical]] if logical in explicit_map else aliases
        actuals = resolve_columns(columns, candidates)
        if not actuals:
            continue
        values: list[str] = []
        accepted_names = {a.lower() for a in [logical, *aliases, *actuals]}
        for evidence_name, evidence_values in impacted.items():
            if str(evidence_name).lower() in accepted_names:
                values.extend(str(v) for v in evidence_values if str(v) != "")
        if values:
            filters[actuals[0]] = set(values)
            mapping[logical] = actuals[0]

    for raw in manual_filters or []:
        if "=" not in raw:
            raise SystemExit(f"Invalid --filter '{raw}'. Use CSV_COLUMN=VALUE")
        column, value = raw.split("=", 1)
        actual = resolve_columns(columns, [column])
        if not actual:
            raise SystemExit(f"Manual filter column '{column}' is not present in backtesting CSV")
        filters.setdefault(actual[0], set()).add(value)
    return filters, mapping


def _resolve_deal_derivation(columns: list[str], profile: dict) -> dict:
    cfg = dict(profile.get("deal_id_derivation") or {})
    aliases = list(cfg.pop("source_aliases", []) or [])
    actual = resolve_columns(columns, aliases)
    if actual:
        cfg["source_column"] = actual[0]
    return cfg


def _write_deals(path: Path, rows: list[dict]) -> None:
    flattened = []
    for row in rows:
        flattened.append(
            {
                "row_number": row.get("row_number"),
                "metric": row.get("metric"),
                "value": row.get("value"),
                "gross_absolute_value": row.get("gross_absolute_value"),
                "within_deal_cancellation_pct": row.get("within_deal_cancellation_pct"),
                "rows_in_deal_group": row.get("rows_in_deal_group"),
                **{f"id.{k}": v for k, v in (row.get("identity") or {}).items()},
                **{f"dim.{k}": v for k, v in (row.get("dimensions") or {}).items()},
            }
        )
    fields = sorted({k for row in flattened for k in row}) if flattened else ["row_number", "metric", "value"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(flattened)


def main() -> int:
    p = argparse.ArgumentParser(description="Drill a huge CCR backtesting comparison down to deals implicated by upstream CVAR/GCVAR evidence.")
    p.add_argument("--input", required=True)
    p.add_argument("--evidence", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--profile", default="backtesting")
    p.add_argument("--metric", action="append", help="Explicit backtesting gap metric column; repeatable. Default profile understands real 'Mtf00 Gap'/'EepeInEur Gap' headers.")
    p.add_argument("--threshold", action="append", help="Override per-metric threshold, e.g. 'EepeInEurGap=25000'.")
    p.add_argument("--coverage", type=float, help="Override deal-level absolute-impact coverage target, e.g. 0.8 or 0.9")
    p.add_argument("--deal-column", action="append", help="Explicit deal/trade identifier column; repeatable")
    p.add_argument("--filter-map", action="append", help="Map logical upstream dimension to backtesting column, e.g. LegalEntity=LE_NAME")
    p.add_argument("--filter", action="append", help="Additional explicit backtesting filter CSV_COLUMN=VALUE")
    p.add_argument("--top-k", type=int, default=100)
    p.add_argument("--backend", choices=["auto", "polars", "streaming"], default="auto")
    p.add_argument("--delimiter")
    args = p.parse_args()

    timer = StageTimer()
    source = Path(args.input).resolve()
    out = ensure_output_dir(args.output)
    original_source = source
    workbook_materialization = None
    if is_excel(source):
        with timer.measure("xlsx_normalization"):
            workbook_materialization = materialize_ccr_comparison_workbook(
                source,
                cache_dir=out / "_cache",
                purpose="backtesting-comparison",
            )
        source = workbook_materialization.path
    upstream = load_evidence(args.evidence)
    profile = load_profile(args.profile)
    profile = apply_metric_threshold_overrides(profile, args.threshold)
    profile = apply_metric_coverage_override(profile, args.coverage)

    with timer.measure("inspect_header"):
        layout = detect_layout(source, args.delimiter)
        deal_columns = resolve_columns(layout.columns, args.deal_column or profile.get("deal_id_candidates") or [])
        if args.metric:
            explicit_profile = {
                "metrics": [
                    {
                        "name": name,
                        "aliases": [name],
                        "absolute_threshold": 10000.0,
                        "coverage_target": args.coverage if args.coverage is not None else 0.9,
                        "candidate_cap": 5000,
                        "max_selected": 500,
                    }
                    for name in args.metric
                ]
            }
            explicit_profile = apply_metric_threshold_overrides(explicit_profile, args.threshold)
            explicit_profile = apply_metric_coverage_override(explicit_profile, args.coverage)
            metric_specs, missing_metrics = resolve_metric_specs(layout.columns, explicit_profile["metrics"])
        else:
            metric_specs, missing_metrics = resolve_metric_specs(layout.columns, profile.get("metrics") or [])
        if not metric_specs:
            raise SystemExit("No configured/explicit backtesting gap metric column is present. Use --metric COLUMN.")
        filters, filter_mapping = _resolve_filters(layout.columns, upstream, profile, args.filter_map, args.filter)
        if not filters:
            raise SystemExit(
                "No impacted LegalEntity dimension from upstream evidence could be mapped into the backtesting CSV. "
                "Provide --filter/--filter-map or verify the upstream compare file contains LegalEntity."
            )
        deal_derivation = _resolve_deal_derivation(layout.columns, profile)
        if not deal_columns and not deal_derivation.get("source_column"):
            raise SystemExit(
                "No explicit deal identifier and no AggregationLevel column available for TRD: deal extraction. "
                "Provide --deal-column COLUMN."
            )

    with timer.measure("filtered_backtesting_scan"):
        result = filter_and_rank_deals(
            source,
            delimiter=layout.delimiter,
            filters=filters,
            deal_columns=deal_columns,
            metrics=metric_specs,
            deal_derivation=deal_derivation,
            top_k=args.top_k,
            backend=args.backend,
        )

    concentration = result.get("concentration") or {}
    ranked_deals: list[tuple[str, float]] = []
    seen_deals: set[str] = set()
    for row in result["deal_impacts"]:
        identity = row.get("identity") or {}
        deal = identity.get("DealId") or next(iter(identity.values()), f"row:{row.get('row_number')}")
        if str(deal) not in seen_deals:
            seen_deals.add(str(deal))
            ranked_deals.append((str(deal), abs(float(row.get("value") or 0.0))))

    selected_deals = {deal for deal, _ in ranked_deals}
    # The real compare export contains Ref/Test pairs and a few derived Gap/Ratio diagnostics.
    # Read only those columns, and only for selected deals, in a second bounded pass.
    diagnostic_columns = list(dict.fromkeys([
        *[c for c in layout.columns if re.search(r"\((?:Ref|Test|Result)\)$", c, flags=re.IGNORECASE)],
        *[str(c) for c in (profile.get("diagnostic_columns") or [])],
        *[str(spec.get("source_name") or spec.get("name")) for spec in metric_specs],
    ]))
    with timer.measure("selected_deal_enrichment"):
        diagnostic_result = enrich_selected_deals(
            source,
            delimiter=layout.delimiter,
            filters=filters,
            deal_columns=deal_columns,
            deal_derivation=deal_derivation,
            selected_deals=selected_deals,
            diagnostic_columns=diagnostic_columns,
            max_rows=5000,
            backend=args.backend,
        )
    selected_deal_rows = diagnostic_result.get("rows") or []
    deal_ref_test_changes = summarize_ref_test_changes(selected_deal_rows)
    deal_result_flag_failures = summarize_result_flags(selected_deal_rows)
    deal_secondary_numeric = summarize_numeric_columns(
        selected_deal_rows,
        list(profile.get("diagnostic_numeric_columns") or []),
    )

    deal_families = summarize_deal_families(result["deal_impacts"])

    patterns = [
        {
            "dimension": "deal-concentration",
            "value": metric,
            "count": int(stats.get("selected_count") or 0),
            "material_row_count": int(stats.get("material_deal_count") or 0),
            "row_share_pct": stats.get("top3_share_pct"),
            "metric_contribution": stats,
        }
        for metric, stats in concentration.items()
    ]
    warnings = [*(result.get("warnings") or []), *(diagnostic_result.get("warnings") or [])]
    if missing_metrics:
        warnings.append(f"Configured backtesting metrics not present and skipped: {', '.join(missing_metrics)}")
    if not deal_columns and result.get("derived_deal_column"):
        warnings.append(
            f"No dedicated deal column was found; '{result['derived_deal_column']}' was derived from AggregationLevel using the configured TRD: convention."
        )

    evidence = {
        "schema_version": "1.0",
        "evidence_type": "backtesting-drilldown",
        "title": "CCR backtesting deal-level drilldown",
        "source": {
            **file_metadata(original_source),
            "normalized_table": str(source) if source != original_source else None,
            "input_format": "xlsx" if workbook_materialization else "csv",
            "workbook_sheets": workbook_materialization.sheets if workbook_materialization else None,
            "workbook_cache_hit": workbook_materialization.cache_hit if workbook_materialization else None,
            "delimiter": layout.delimiter,
            "upstream_evidence": str(Path(args.evidence).resolve()),
        },
        "summary": {
            "backend": result.get("backend", "unknown"),
            "rows_scanned": result["rows_scanned"],
            "rows_matching_upstream_dimensions": result["rows_matching_filters"],
            "selected_deal_candidates": len(ranked_deals),
            "metrics": ", ".join(str(spec["name"]) for spec in metric_specs),
            "filters": json.dumps({k: sorted(v)[:50] for k, v in filters.items()}),
            "deal_identifier": ", ".join(deal_columns) if deal_columns else f"derived {result.get('derived_deal_column') or 'DealId'} from {deal_derivation.get('source_column')}",
        },
        "metric_policy": {
            str(spec["name"]): {
                "source_column": spec.get("source_name"),
                "absolute_threshold": spec.get("absolute_threshold"),
                "threshold_operator": ">",
                "coverage_target": spec.get("coverage_target"),
                "unit": spec.get("unit"),
            }
            for spec in metric_specs
        },
        "concentration": concentration,
        "material_impacts": result["deal_impacts"],
        "patterns": patterns,
        "ref_test_change_patterns": deal_ref_test_changes,
        "comparison_flag_failures": deal_result_flag_failures,
        "secondary_numeric_diagnostics": deal_secondary_numeric,
        "deal_family_patterns": deal_families,
        "impacted_dimensions": {
            **{k: sorted(v)[:50] for k, v in filters.items()},
            "Deal": [deal for deal, _ in ranked_deals[:50]],
        },
        "timings": timer.timings,
        "warnings": warnings,
        "filter_mapping": filter_mapping,
        "deal_derivation": deal_derivation,
    }
    evidence["mtf00_eepe_relationship"] = mtf_eepe_relationship(upstream, backtesting=evidence)
    write_evidence(out / "backtesting_summary.json", evidence)
    _write_deals(out / "deal_impacts.csv", result["deal_impacts"])
    write_json(
        out / "backtesting_patterns.json",
        {
            "ranked_deals": ranked_deals[:500],
            "concentration": concentration,
            "deal_derivation": deal_derivation,
            "ref_test_change_patterns": deal_ref_test_changes,
            "comparison_flag_failures": deal_result_flag_failures,
            "secondary_numeric_diagnostics": deal_secondary_numeric,
            "deal_family_patterns": deal_families,
        },
    )
    (out / "agent_context.md").write_text(compact_agent_markdown(evidence), encoding="utf-8")
    write_json(
        out / "run_manifest.json",
        {
            "input": file_metadata(original_source),
            "normalized_table": str(source) if source != original_source else None,
            "upstream_evidence": str(Path(args.evidence).resolve()),
            "artifacts": ["backtesting_summary.json", "deal_impacts.csv", "backtesting_patterns.json", "agent_context.md"],
            "timings": timer.timings,
        },
    )
    print(
        json.dumps(
            {
                "ok": True,
                "output": str(out),
                "rows_scanned": result["rows_scanned"],
                "rows_matching": result["rows_matching_filters"],
                "selected_deals": len(ranked_deals),
                "concentration": concentration,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
