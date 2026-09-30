from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .artifacts import write_json

EVIDENCE_SCHEMA_VERSION = "1.0"


def validate_evidence(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != EVIDENCE_SCHEMA_VERSION:
        errors.append(f"schema_version must be {EVIDENCE_SCHEMA_VERSION}")
    for key in ("evidence_type", "source", "summary", "material_impacts", "patterns", "impacted_dimensions", "timings", "warnings"):
        if key not in payload:
            errors.append(f"missing required evidence field: {key}")
    if not isinstance(payload.get("material_impacts", []), list):
        errors.append("material_impacts must be a list")
    if not isinstance(payload.get("patterns", []), list):
        errors.append("patterns must be a list")
    if not isinstance(payload.get("warnings", []), list):
        errors.append("warnings must be a list")
    return errors


def write_evidence(path: str | Path, payload: dict[str, Any]) -> Path:
    payload = dict(payload)
    payload.setdefault("schema_version", EVIDENCE_SCHEMA_VERSION)
    errors = validate_evidence(payload)
    if errors:
        raise ValueError("Invalid evidence payload: " + "; ".join(errors))
    return write_json(path, payload)


def load_evidence(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    errors = validate_evidence(payload)
    if errors:
        raise ValueError("Invalid evidence payload: " + "; ".join(errors))
    return payload


def compact_agent_markdown(payload: dict[str, Any], *, max_impacts: int = 30, max_patterns: int = 20) -> str:
    summary = payload.get("summary") or {}
    lines = [
        f"# {payload.get('title') or payload.get('evidence_type', 'Evidence')}",
        "",
        "This is a compact deterministic evidence report. The raw source CSV is intentionally not embedded.",
        "",
        "## Summary",
    ]
    for key, value in summary.items():
        lines.append(f"- **{key}**: {value}")

    metric_stats = payload.get("metric_statistics") or {}
    concentration = payload.get("concentration") or {}
    selection_stats = metric_stats or concentration
    if selection_stats:
        lines.extend(["", "## Materiality and coverage"])
        for metric, stats in selection_stats.items():
            if not isinstance(stats, dict):
                continue
            threshold = stats.get("threshold")
            material_count = stats.get("material_count", stats.get("material_deal_count"))
            selected_count = stats.get("selected_count")
            coverage = stats.get("selected_coverage_pct")
            threshold_capture = stats.get("threshold_capture_pct_of_all_abs_movement")
            parts = []
            if threshold is not None:
                parts.append(f"strict |gap| > {threshold}")
            if material_count is not None:
                parts.append(f"material={material_count}")
            positive_count = stats.get("material_positive_count", stats.get("material_positive_deal_count"))
            negative_count = stats.get("material_negative_count", stats.get("material_negative_deal_count"))
            if positive_count is not None or negative_count is not None:
                parts.append(f"material signs +{positive_count or 0}/-{negative_count or 0}")
            if selected_count is not None:
                parts.append(f"selected={selected_count}")
            if coverage is not None:
                parts.append(f"selected coverage={coverage}%")
            if threshold_capture is not None:
                parts.append(f"threshold captures {threshold_capture}% of all absolute movement")
            net_gross = stats.get("material_net_to_gross_pct")
            if net_gross is not None:
                parts.append(f"material net/gross={net_gross}%")
            cancellation = stats.get("material_cancellation_pct")
            if cancellation is not None:
                parts.append(f"cancellation={cancellation}%")
            row_pct = stats.get("material_row_pct")
            if row_pct is not None:
                parts.append(f"material rows={row_pct}%")
            top1 = stats.get("top1_share_pct")
            top3 = stats.get("top3_share_pct")
            top10 = stats.get("top10_share_pct")
            if top1 is not None:
                parts.append(f"top1/top3/top10={top1}%/{top3}%/{top10}%")
            effective = stats.get("effective_contributors")
            if effective is not None:
                parts.append(f"effective contributors≈{effective}")
            ladder = [stats.get(f"contributors_for_{pct}pct") for pct in (50, 80, 90, 95)]
            if any(value is not None for value in ladder):
                parts.append(f"contributors for 50/80/90/95%={ladder[0]}/{ladder[1]}/{ladder[2]}/{ladder[3]}")
            lines.append(f"- **{metric}**: " + "; ".join(parts))
            coverage_groups = stats.get("coverage_groups") or {}
            if isinstance(coverage_groups, dict) and coverage_groups:
                for group, group_stats in list(coverage_groups.items())[:12]:
                    lines.append(
                        f"  - `{group}`: material={group_stats.get('material_count')}; selected={group_stats.get('selected_count')}; "
                        f"coverage={group_stats.get('selected_coverage_pct')}%; "
                        f"top1/top3/top10={group_stats.get('top1_share_pct')}%/{group_stats.get('top3_share_pct')}%/{group_stats.get('top10_share_pct')}%; "
                        f"cancellation={group_stats.get('material_cancellation_pct')}%; effective contributors≈{group_stats.get('effective_contributors')}; "
                        f"contributors 50/80/90/95%={group_stats.get('contributors_for_50pct')}/{group_stats.get('contributors_for_80pct')}/{group_stats.get('contributors_for_90pct')}/{group_stats.get('contributors_for_95pct')}"
                    )

    lines.extend(["", "## Material impacts"])
    impacts = payload.get("material_impacts") or []
    if not impacts:
        lines.append("- No material impacts selected.")
    for row in impacts[:max_impacts]:
        metric = row.get("metric", "?")
        value = row.get("value", "?")
        identity = row.get("identity") or {}
        dimensions = row.get("dimensions") or {}
        ident_text = ", ".join(f"{k}={v}" for k, v in identity.items()) or f"row={row.get('row_number','?')}"
        dim_text = ", ".join(f"{k}={v}" for k, v in dimensions.items())
        extra = f" · {dim_text}" if dim_text else ""
        lines.append(f"- `{metric}` = **{value}** · {ident_text}{extra}")
    if len(impacts) > max_impacts:
        lines.append(f"- … {len(impacts) - max_impacts} additional selected impacts retained in structured evidence.")

    lines.extend(["", "## Patterns"])
    patterns = payload.get("patterns") or []
    if not patterns:
        lines.append("- No strong shared categorical/contribution pattern detected.")
    for pattern in patterns[:max_patterns]:
        if pattern.get("dimension") == "deal-concentration":
            stats = pattern.get("metric_contribution") or {}
            lines.append(
                f"- **Deal concentration · {pattern.get('value','?')}**: "
                f"top1={stats.get('top1_share_pct')}%, top3={stats.get('top3_share_pct')}%, "
                f"top10={stats.get('top10_share_pct')}%, selected coverage={stats.get('selected_coverage_pct')}%"
            )
        else:
            share = pattern.get("row_share_pct")
            contribution = pattern.get("max_abs_contribution_share_pct")
            lines.append(
                f"- **{pattern.get('dimension','?')}={pattern.get('value','?')}**: "
                f"{pattern.get('count',0)}/{pattern.get('material_row_count',0)} selected rows ({share}%), "
                f"up to {contribution}% of selected absolute movement; "
                f"metric contribution={pattern.get('metric_contribution',{})}"
            )

    aggregation_shapes = payload.get("aggregation_structure_patterns") or []
    if aggregation_shapes:
        lines.extend(["", "## Aggregation structure on selected impacts"])
        for row in aggregation_shapes[:10]:
            lines.append(
                f"- **{row.get('path_shape')}**: {row.get('count')} selected rows ({row.get('share_pct')}%); terminal={row.get('terminal_kind')}"
            )

    changes = payload.get("ref_test_change_patterns") or []
    if changes:
        lines.extend(["", "## Ref/Test fields that changed on material rows"])
        for row in changes[:15]:
            detail = f"{row.get('changed_rows')}/{row.get('comparable_rows')} rows ({row.get('changed_pct')}%)"
            if row.get("max_abs_delta") is not None:
                detail += f", max |Test-Ref|={row.get('max_abs_delta')}"
            lines.append(f"- **{row.get('field')}**: {detail}")

    flags = payload.get("comparison_flag_failures") or []
    if flags:
        lines.extend(["", "## Comparison-result flags"])
        for row in flags[:10]:
            lines.append(f"- **{row.get('column')}**: non-TRUE on {row.get('non_true_rows')}/{row.get('rows_with_value')} rows ({row.get('non_true_pct')}%)")


    diagnostics = payload.get("secondary_numeric_diagnostics") or []
    if diagnostics:
        lines.extend(["", "## Secondary diagnostics on selected impacts"])
        for row in diagnostics[:12]:
            lines.append(
                f"- **{row.get('name')}** ({row.get('source_column')}): "
                f"nonzero={row.get('nonzero')}/{row.get('valid')}, "
                f"mean|x|={row.get('mean_abs')}, p95|x|={row.get('p95_abs')}, max|x|={row.get('max_abs')}"
            )

    relationships = payload.get("metric_relationships") or []
    if relationships:
        lines.extend(["", "## Metric relationships"])
        for row in relationships:
            lines.append(
                f"- **{row.get('left_metric')} ↔ {row.get('right_metric')}**: "
                f"rows={row.get('rows_with_both')}, both material={row.get('both_over_materiality_threshold')}, "
                f"same sign={row.get('same_sign_pct')}%, Pearson={row.get('pearson_correlation')}"
            )

    dims = payload.get("impacted_dimensions") or {}
    if dims:
        lines.extend(["", "## Impacted dimensions"])
        for name, values in dims.items():
            lines.append(f"- **{name}**: {', '.join(map(str, values[:25]))}")

    warnings = payload.get("warnings") or []
    if warnings:
        lines.extend(["", "## Warnings"])
        lines.extend(f"- {warning}" for warning in warnings[:20])

    timings = payload.get("timings") or []
    if timings:
        lines.extend(["", "## Timings"])
        for row in timings:
            lines.append(f"- {row.get('stage')}: {row.get('elapsed_seconds')} s")

    lines.extend([
        "",
        "## Agent rule",
        "Reason from this evidence. Request a deeper artifact only when needed; never ask to load the raw huge CSV into LLM context.",
    ])
    return "\n".join(lines) + "\n"
