from __future__ import annotations

import csv
import heapq
import math
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

try:
    import polars as pl  # type: ignore
except ImportError:  # pragma: no cover - depends on workstation extras
    pl = None


@dataclass(frozen=True)
class CsvLayout:
    columns: list[str]
    delimiter: str


def detect_layout(path: str | Path, delimiter: str | None = None) -> CsvLayout:
    p = Path(path)
    with p.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        sample = handle.read(64 * 1024)
    chosen = delimiter
    if not chosen:
        try:
            chosen = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
        except csv.Error:
            chosen = ","
    reader = csv.reader(sample.splitlines(), delimiter=chosen)
    try:
        header = next(reader)
    except StopIteration:
        header = []
    return CsvLayout([str(v).strip() for v in header], chosen)


def resolve_columns(columns: Iterable[str], candidates: Iterable[str]) -> list[str]:
    actual = list(columns)
    lower = {name.lower(): name for name in actual}
    result: list[str] = []
    for candidate in candidates:
        found = lower.get(str(candidate).strip().lower())
        if found and found not in result:
            result.append(found)
    return result


def resolve_metric_specs(columns: Iterable[str], configured: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    """Resolve stable logical metric names to the actual CSV headers.

    Profiles can therefore use a canonical name such as ``Mtf00Gap`` while accepting real
    compare-job headers such as ``Mtf00 Gap``.  Evidence always uses the canonical name so
    agents are isolated from cosmetic schema variations.
    """
    actual = list(columns)
    lower = {name.lower(): name for name in actual}
    resolved: list[dict[str, Any]] = []
    missing: list[str] = []
    for raw in configured:
        if not isinstance(raw, dict) or not raw.get("name"):
            continue
        canonical = str(raw["name"])
        candidates = [canonical, *(raw.get("aliases") or [])]
        source_name = None
        for candidate in candidates:
            source_name = lower.get(str(candidate).strip().lower())
            if source_name:
                break
        if source_name is None:
            missing.append(canonical)
            continue
        spec = dict(raw)
        spec["name"] = canonical
        spec["source_name"] = source_name
        group_candidates = [
            *(spec.get("coverage_group_by_aliases") or []),
            *([spec.get("coverage_group_by")] if spec.get("coverage_group_by") else []),
        ]
        for candidate in group_candidates:
            actual_group = lower.get(str(candidate).strip().lower())
            if actual_group:
                spec["coverage_group_by_source"] = actual_group
                break
        resolved.append(spec)
    return resolved, missing


def _number(raw: Any) -> float | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    # Excel exports occasionally use parentheses for negatives.
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]
    text = text.replace("\u00a0", "").replace(" ", "")
    is_percent = text.endswith("%")
    if is_percent:
        text = text[:-1]
    try:
        value = float(text)
    except ValueError:
        return None
    if is_percent:
        value /= 100.0
    return value if math.isfinite(value) else None


def _push_top(heap: list[tuple[float, int, dict[str, Any]]], k: int, score: float, sequence: int, row: dict[str, Any]) -> None:
    if k <= 0:
        return
    item = (score, sequence, row)
    if len(heap) < k:
        heapq.heappush(heap, item)
    elif score > heap[0][0]:
        heapq.heapreplace(heap, item)


def _policy(spec: dict[str, Any], top_k: int) -> dict[str, Any]:
    threshold = float(spec.get("absolute_threshold") or 0.0)
    coverage = float(spec.get("coverage_target") or 1.0)
    coverage = max(0.000001, min(1.0, coverage))
    candidate_cap = int(spec.get("candidate_cap") or max(int(spec.get("top_k") or top_k), 5000 if threshold > 0 else top_k))
    max_selected = int(spec.get("max_selected") or candidate_cap)
    return {
        "threshold": threshold,
        "coverage": coverage,
        "candidate_cap": max(candidate_cap, 1),
        "max_selected": max(max_selected, 1),
        "top_k": int(spec.get("top_k") or top_k),
    }


def _coverage_contributor_counts(scores: list[float], total_abs: float) -> dict[str, int | None]:
    """How many largest contributors are required to explain common absolute-impact shares.

    ``scores`` must be descending absolute contributions. ``None`` means the retained
    candidate window was not large enough to reach that share.
    """
    result: dict[str, int | None] = {}
    running = 0.0
    thresholds = ((50, 0.50), (80, 0.80), (90, 0.90), (95, 0.95))
    reached: dict[int, int] = {}
    if total_abs <= 0:
        return {f"contributors_for_{pct}pct": 0 for pct, _ in thresholds}
    for index, score in enumerate(scores, start=1):
        running += float(score)
        for pct, target in thresholds:
            if pct not in reached and running + 1e-12 >= total_abs * target:
                reached[pct] = index
    for pct, _ in thresholds:
        result[f"contributors_for_{pct}pct"] = reached.get(pct)
    return result


def _select_metric_candidates(
    ordered: list[tuple[float, int, dict[str, Any]]],
    *,
    policy: dict[str, Any],
    material_abs_sum: float,
    material_count: int,
) -> tuple[list[tuple[float, int, dict[str, Any]]], dict[str, Any], list[str]]:
    warnings: list[str] = []
    threshold = float(policy["threshold"])
    if threshold <= 0:
        chosen = ordered[: int(policy["top_k"])]
        selected_abs = sum(score for score, _, _ in chosen)
        stats = {
            "selection_mode": "top-k",
            "threshold": None,
            "coverage_target_pct": None,
            "material_count": material_count,
            "material_abs_sum": material_abs_sum,
            "selected_count": len(chosen),
            "selected_abs_sum": selected_abs,
            "selected_coverage_pct": None,
        }
        stats.update(_coverage_contributor_counts([score for score, _, _ in ordered], material_abs_sum))
        return chosen, stats, warnings

    target = material_abs_sum * float(policy["coverage"])
    max_selected = int(policy["max_selected"])
    chosen: list[tuple[float, int, dict[str, Any]]] = []
    selected_abs = 0.0
    for item in ordered[:max_selected]:
        chosen.append(item)
        selected_abs += item[0]
        if selected_abs + 1e-12 >= target:
            break

    coverage_pct = 100.0 * selected_abs / material_abs_sum if material_abs_sum else 100.0
    cap_exhausted = material_count > len(ordered)
    selection_limit_exhausted = bool(ordered) and len(chosen) >= max_selected and selected_abs + 1e-12 < target
    if cap_exhausted and selected_abs + 1e-12 < target:
        warnings.append(
            f"Candidate cap retained the largest {len(ordered)} of {material_count} material rows; "
            f"coverage target {100*policy['coverage']:.1f}% was not reached."
        )
    if selection_limit_exhausted:
        warnings.append(
            f"Selection limit {max_selected} was reached before the {100*policy['coverage']:.1f}% coverage target."
        )
    stats = {
        "selection_mode": "threshold+coverage",
        "threshold": threshold,
        "threshold_operator": ">",
        "coverage_target_pct": round(100 * float(policy["coverage"]), 2),
        "material_count": material_count,
        "material_abs_sum": material_abs_sum,
        "selected_count": len(chosen),
        "selected_abs_sum": selected_abs,
        "selected_coverage_pct": round(coverage_pct, 2),
        "candidate_cap": int(policy["candidate_cap"]),
        "candidate_cap_exhausted": cap_exhausted,
        "max_selected": max_selected,
        "selection_limit_exhausted": selection_limit_exhausted,
    }
    stats.update(_coverage_contributor_counts([score for score, _, _ in ordered], material_abs_sum))
    return chosen, stats, warnings


def streaming_select_material(
    path: str | Path,
    *,
    metrics: list[dict[str, Any]],
    identity_columns: list[str],
    dimension_columns: list[str],
    delimiter: str,
    top_k: int,
) -> dict[str, Any]:
    """Bounded-memory material-impact selection.

    For configured business thresholds, a row is material only when ``abs(gap) > threshold``.
    The selector then keeps the smallest set of the largest material impacts needed to explain
    the configured share (90% by default in the CCR profiles). Candidate heaps keep memory
    bounded even when the CSV has millions of rows.
    """
    metric_names = [str(m["name"]) for m in metrics]
    specs = {str(m["name"]): m for m in metrics}
    policies = {name: _policy(specs[name], top_k) for name in metric_names}
    heaps: dict[str, dict[str, list[tuple[float, int, dict[str, Any]]]]] = {name: {} for name in metric_names}
    coverage_group_stats: dict[str, dict[str, dict[str, float | int]]] = {name: {} for name in metric_names}
    metric_stats: dict[str, dict[str, float | int | None | str]] = {
        name: {
            "source_column": str(specs[name].get("source_name") or name),
            "valid": 0,
            "null_or_invalid": 0,
            "positive": 0,
            "negative": 0,
            "sum": 0.0,
            "abs_sum": 0.0,
            "min": None,
            "max": None,
            "material_count": 0,
            "material_positive_count": 0,
            "material_negative_count": 0,
            "material_positive_abs_sum": 0.0,
            "material_negative_abs_sum": 0.0,
            "material_signed_sum": 0.0,
            "material_abs_sum": 0.0,
            "material_abs_square_sum": 0.0,
        }
        for name in metric_names
    }
    rows_scanned = 0
    malformed_rows = 0
    p = Path(path)
    with p.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        reader = csv.reader(handle, delimiter=delimiter)
        try:
            header = [str(v).strip() for v in next(reader)]
        except StopIteration:
            return {"backend": "python-streaming", "rows_scanned": 0, "metric_stats": metric_stats, "material_rows": [], "warnings": ["Input CSV is empty."]}
        index = {name: i for i, name in enumerate(header)}
        metric_idx = {
            name: index[str(specs[name].get("source_name") or name)]
            for name in metric_names
            if str(specs[name].get("source_name") or name) in index
        }
        group_idx = {
            name: index[str(specs[name].get("coverage_group_by_source"))]
            for name in metric_names
            if specs[name].get("coverage_group_by_source") and str(specs[name].get("coverage_group_by_source")) in index
        }
        id_idx = {name: index[name] for name in identity_columns if name in index}
        dim_idx = {name: index[name] for name in dimension_columns if name in index}
        max_needed = max([*metric_idx.values(), *group_idx.values(), *id_idx.values(), *dim_idx.values()] or [0])

        for row_number, row in enumerate(reader, start=2):
            rows_scanned += 1
            if len(row) <= max_needed:
                malformed_rows += 1
                continue
            parsed_metrics: dict[str, float] = {}
            candidate_metrics: list[tuple[str, str, float, int]] = []
            for name in metric_names:
                idx = metric_idx.get(name)
                value = _number(row[idx]) if idx is not None else None
                stats = metric_stats[name]
                if value is None:
                    stats["null_or_invalid"] = int(stats["null_or_invalid"] or 0) + 1
                    continue
                parsed_metrics[name] = value
                stats["valid"] = int(stats["valid"] or 0) + 1
                stats["positive"] = int(stats["positive"] or 0) + int(value > 0)
                stats["negative"] = int(stats["negative"] or 0) + int(value < 0)
                stats["sum"] = float(stats["sum"] or 0.0) + value
                stats["abs_sum"] = float(stats["abs_sum"] or 0.0) + abs(value)
                stats["min"] = value if stats["min"] is None else min(float(stats["min"]), value)
                stats["max"] = value if stats["max"] is None else max(float(stats["max"]), value)

                policy = policies[name]
                score = abs(value)
                threshold = float(policy["threshold"])
                group_source = str(specs[name].get("coverage_group_by_source") or "")
                group_key = str(row[group_idx[name]]).strip() if name in group_idx else "__all__"
                if not group_key:
                    group_key = "<missing>" if group_source else "__all__"
                if threshold > 0:
                    # Business rule from the CCR compare process: "over 10k" is strict, not >=.
                    if score > threshold:
                        stats["material_count"] = int(stats["material_count"] or 0) + 1
                        stats["material_positive_count"] = int(stats["material_positive_count"] or 0) + int(value > 0)
                        stats["material_negative_count"] = int(stats["material_negative_count"] or 0) + int(value < 0)
                        stats["material_positive_abs_sum"] = float(stats["material_positive_abs_sum"] or 0.0) + (score if value > 0 else 0.0)
                        stats["material_negative_abs_sum"] = float(stats["material_negative_abs_sum"] or 0.0) + (score if value < 0 else 0.0)
                        stats["material_signed_sum"] = float(stats["material_signed_sum"] or 0.0) + value
                        stats["material_abs_sum"] = float(stats["material_abs_sum"] or 0.0) + score
                        stats["material_abs_square_sum"] = float(stats["material_abs_square_sum"] or 0.0) + score * score
                        group_stats = coverage_group_stats[name].setdefault(group_key, {"material_count": 0, "material_abs_sum": 0.0, "material_signed_sum": 0.0, "material_abs_square_sum": 0.0})
                        group_stats["material_count"] = int(group_stats["material_count"] or 0) + 1
                        group_stats["material_abs_sum"] = float(group_stats["material_abs_sum"] or 0.0) + score
                        group_stats["material_signed_sum"] = float(group_stats["material_signed_sum"] or 0.0) + value
                        group_stats["material_abs_square_sum"] = float(group_stats["material_abs_square_sum"] or 0.0) + score * score
                        heap = heaps[name].setdefault(group_key, [])
                        cap = int(policy["candidate_cap"])
                        if len(heap) < cap or score > heap[0][0]:
                            candidate_metrics.append((name, group_key, score, cap))
                else:
                    stats["material_count"] = int(stats["material_count"] or 0) + 1
                    stats["material_positive_count"] = int(stats["material_positive_count"] or 0) + int(value > 0)
                    stats["material_negative_count"] = int(stats["material_negative_count"] or 0) + int(value < 0)
                    stats["material_positive_abs_sum"] = float(stats["material_positive_abs_sum"] or 0.0) + (score if value > 0 else 0.0)
                    stats["material_negative_abs_sum"] = float(stats["material_negative_abs_sum"] or 0.0) + (score if value < 0 else 0.0)
                    stats["material_signed_sum"] = float(stats["material_signed_sum"] or 0.0) + value
                    stats["material_abs_sum"] = float(stats["material_abs_sum"] or 0.0) + score
                    stats["material_abs_square_sum"] = float(stats["material_abs_square_sum"] or 0.0) + score * score
                    group_stats = coverage_group_stats[name].setdefault(group_key, {"material_count": 0, "material_abs_sum": 0.0, "material_signed_sum": 0.0, "material_abs_square_sum": 0.0})
                    group_stats["material_count"] = int(group_stats["material_count"] or 0) + 1
                    group_stats["material_abs_sum"] = float(group_stats["material_abs_sum"] or 0.0) + score
                    group_stats["material_signed_sum"] = float(group_stats["material_signed_sum"] or 0.0) + value
                    group_stats["material_abs_square_sum"] = float(group_stats["material_abs_square_sum"] or 0.0) + score * score
                    heap = heaps[name].setdefault(group_key, [])
                    cap = int(policy["top_k"])
                    if len(heap) < cap or score > heap[0][0]:
                        candidate_metrics.append((name, group_key, score, cap))

            if not candidate_metrics:
                continue
            payload = {
                "row_number": row_number,
                "identity": {name: row[idx] for name, idx in id_idx.items() if row[idx] != ""},
                "dimensions": {name: row[idx] for name, idx in dim_idx.items() if row[idx] != ""},
                "metrics": parsed_metrics,
                "selected_metrics": [],
            }
            for name, group_key, score, cap in candidate_metrics:
                _push_top(heaps[name].setdefault(group_key, []), cap, score, row_number, payload)

    selected_by_row: dict[int, dict[str, Any]] = {}
    warnings: list[str] = []
    for name in metric_names:
        stats = metric_stats[name]
        metric_warnings: list[str] = []
        chosen: list[tuple[float, int, dict[str, Any]]] = []
        group_selection: dict[str, dict[str, Any]] = {}
        for group_key, heap in heaps[name].items():
            ordered_group = sorted(heap, key=lambda item: (-item[0], item[1]))
            group_stats = coverage_group_stats[name].get(group_key) or {}
            group_chosen, group_selection_stats, group_warnings = _select_metric_candidates(
                ordered_group,
                policy=policies[name],
                material_abs_sum=float(group_stats.get("material_abs_sum") or 0.0),
                material_count=int(group_stats.get("material_count") or 0),
            )
            group_scores = [score for score, _, _ in ordered_group]
            group_abs = float(group_stats.get("material_abs_sum") or 0.0)
            group_signed = float(group_stats.get("material_signed_sum") or 0.0)
            group_sq = float(group_stats.get("material_abs_square_sum") or 0.0)
            group_selection_stats.update({
                "top1_share_pct": round(100 * sum(group_scores[:1]) / group_abs, 2) if group_abs else 0.0,
                "top3_share_pct": round(100 * sum(group_scores[:3]) / group_abs, 2) if group_abs else 0.0,
                "top10_share_pct": round(100 * sum(group_scores[:10]) / group_abs, 2) if group_abs else 0.0,
                "material_cancellation_pct": round(100 * max(0.0, 1 - abs(group_signed) / group_abs), 2) if group_abs else 0.0,
                "material_hhi": round(group_sq / (group_abs * group_abs), 8) if group_abs else 0.0,
                "effective_contributors": round((group_abs * group_abs) / group_sq, 2) if group_sq > 0 else 0.0,
            })
            group_selection[group_key] = group_selection_stats
            chosen.extend(group_chosen)
            metric_warnings.extend(f"{group_key}: {warning}" for warning in group_warnings)
        chosen.sort(key=lambda item: (-item[0], item[1]))
        if len(group_selection) == 1 and "__all__" in group_selection:
            stats.update(group_selection["__all__"])
        else:
            coverages = [float(v.get("selected_coverage_pct") or 0.0) for v in group_selection.values()]
            stats.update({
                "selection_mode": "threshold+coverage-by-group",
                "coverage_group_by": specs[name].get("coverage_group_by_source"),
                "coverage_groups": group_selection,
                "selected_count": len(chosen),
                "selected_coverage_pct": round(min(coverages), 2) if coverages else None,
                "coverage_aggregation": "minimum per-group coverage (native units are not summed across groups)",
            })
        ordered = sorted([item for heap in heaps[name].values() for item in heap], key=lambda item: (-item[0], item[1]))
        total_abs = float(stats.get("abs_sum") or 0.0)
        material_abs = float(stats.get("material_abs_sum") or 0.0)
        stats["threshold_capture_pct_of_all_abs_movement"] = round(100 * material_abs / total_abs, 2) if total_abs else 0.0
        stats["subthreshold_abs_sum"] = max(0.0, total_abs - material_abs)
        total_signed = float(stats.get("sum") or 0.0)
        material_signed = float(stats.get("material_signed_sum") or 0.0)
        stats["subthreshold_signed_sum"] = total_signed - material_signed
        stats["all_net_to_gross_pct"] = round(100 * abs(total_signed) / total_abs, 2) if total_abs else 0.0
        stats["material_net_to_gross_pct"] = round(100 * abs(material_signed) / material_abs, 2) if material_abs else 0.0
        stats["material_cancellation_pct"] = round(100 * max(0.0, 1 - abs(material_signed) / material_abs), 2) if material_abs else 0.0
        valid_count = int(stats.get("valid") or 0)
        stats["material_row_pct"] = round(100 * int(stats.get("material_count") or 0) / valid_count, 4) if valid_count else 0.0
        scores = [score for score, _, _ in ordered]
        stats["top1_share_pct"] = round(100 * sum(scores[:1]) / material_abs, 2) if material_abs else 0.0
        stats["top3_share_pct"] = round(100 * sum(scores[:3]) / material_abs, 2) if material_abs else 0.0
        stats["top10_share_pct"] = round(100 * sum(scores[:10]) / material_abs, 2) if material_abs else 0.0
        square_sum = float(stats.get("material_abs_square_sum") or 0.0)
        hhi = square_sum / (material_abs * material_abs) if material_abs else 0.0
        stats["material_hhi"] = round(hhi, 8)
        stats["effective_contributors"] = round(1.0 / hhi, 2) if hhi > 0 else 0.0
        if len(group_selection) > 1 or (group_selection and "__all__" not in group_selection):
            # Native-currency MTF00 amounts are not economically additive across currencies.
            for field in (
                "threshold_capture_pct_of_all_abs_movement",
                "all_net_to_gross_pct",
                "material_net_to_gross_pct",
                "material_cancellation_pct",
                "subthreshold_abs_sum",
                "subthreshold_signed_sum",
                "top1_share_pct",
                "top3_share_pct",
                "top10_share_pct",
                "material_hhi",
                "effective_contributors",
            ):
                stats[field] = None
            stats["native_amounts_additive"] = False
            stats["multi_unit_note"] = "Coverage/concentration is reported per currency group; raw native amounts are not summed across currencies."
        for warning in metric_warnings:
            warnings.append(f"{name}: {warning}")
        for score, row_number, row in chosen:
            selected = selected_by_row.setdefault(row_number, dict(row))
            selected.setdefault("selected_metrics", [])
            if name not in selected["selected_metrics"]:
                selected["selected_metrics"].append(name)
            threshold = float(policies[name]["threshold"])
            normalized = score / threshold if threshold > 0 else score
            selected["selection_score"] = max(float(selected.get("selection_score") or 0.0), normalized)

    material = sorted(selected_by_row.values(), key=lambda row: (-float(row.get("selection_score") or 0.0), int(row["row_number"])))
    if malformed_rows:
        warnings.append(f"Skipped {malformed_rows} malformed/short CSV rows that did not contain required column positions.")
    return {"backend": "python-streaming", "rows_scanned": rows_scanned, "metric_stats": metric_stats, "material_rows": material, "warnings": warnings}


def polars_select_material(
    path: str | Path,
    *,
    metrics: list[dict[str, Any]],
    identity_columns: list[str],
    dimension_columns: list[str],
    delimiter: str,
    top_k: int,
) -> dict[str, Any]:
    if pl is None:
        raise RuntimeError("Polars is not installed")

    metric_names = [str(m["name"]) for m in metrics]
    specs = {str(m["name"]): m for m in metrics}
    policies = {name: _policy(specs[name], top_k) for name in metric_names}
    source_names = [str(specs[name].get("source_name") or name) for name in metric_names]

    raw = pl.scan_csv(str(path), separator=delimiter, ignore_errors=True, infer_schema_length=10_000).with_row_index("__row_index", offset=2)
    schema_names = set(raw.collect_schema().names())
    ids = [c for c in identity_columns if c in schema_names]
    dims = [c for c in dimension_columns if c in schema_names]
    sources = [c for c in source_names if c in schema_names]
    group_sources = [
        str(specs[name].get("coverage_group_by_source"))
        for name in metric_names
        if specs[name].get("coverage_group_by_source") and str(specs[name].get("coverage_group_by_source")) in schema_names
    ]
    lf = raw.select(["__row_index", *list(dict.fromkeys([*ids, *dims, *sources, *group_sources]))])
    casts = []
    for name in metric_names:
        source = str(specs[name].get("source_name") or name)
        if source in schema_names:
            casts.append(pl.col(source).cast(pl.Float64, strict=False).alias(name))
    if casts:
        lf = lf.with_columns(casts)
    lf = lf.select(list(dict.fromkeys(["__row_index", *ids, *dims, *group_sources, *[name for name in metric_names if name in lf.collect_schema().names()]])))
    present = [name for name in metric_names if name in lf.collect_schema().names()]

    rows_scanned = int(lf.select(pl.len()).collect(engine="streaming").item())
    exprs = []
    for name in present:
        finite = pl.col(name).is_finite()
        clean = pl.when(finite).then(pl.col(name)).otherwise(None)
        policy = policies[name]
        threshold = float(policy["threshold"])
        exprs.extend([
            finite.sum().alias(f"{name}__valid"),
            (finite & (pl.col(name) > 0)).sum().alias(f"{name}__positive"),
            (finite & (pl.col(name) < 0)).sum().alias(f"{name}__negative"),
            clean.sum().alias(f"{name}__sum"),
            clean.abs().sum().alias(f"{name}__abs_sum"),
            clean.min().alias(f"{name}__min"),
            clean.max().alias(f"{name}__max"),
        ])
        if threshold > 0:
            material = finite & (pl.col(name).abs() > threshold)
            exprs.extend([
                material.sum().alias(f"{name}__material_count"),
                (material & (pl.col(name) > 0)).sum().alias(f"{name}__material_positive_count"),
                (material & (pl.col(name) < 0)).sum().alias(f"{name}__material_negative_count"),
                pl.when(material & (pl.col(name) > 0)).then(pl.col(name).abs()).otherwise(0.0).sum().alias(f"{name}__material_positive_abs_sum"),
                pl.when(material & (pl.col(name) < 0)).then(pl.col(name).abs()).otherwise(0.0).sum().alias(f"{name}__material_negative_abs_sum"),
                pl.when(material).then(pl.col(name)).otherwise(0.0).sum().alias(f"{name}__material_signed_sum"),
                pl.when(material).then(pl.col(name).abs()).otherwise(0.0).sum().alias(f"{name}__material_abs_sum"),
                pl.when(material).then(pl.col(name).abs().pow(2)).otherwise(0.0).sum().alias(f"{name}__material_abs_square_sum"),
            ])
        else:
            exprs.extend([
                finite.sum().alias(f"{name}__material_count"),
                (finite & (pl.col(name) > 0)).sum().alias(f"{name}__material_positive_count"),
                (finite & (pl.col(name) < 0)).sum().alias(f"{name}__material_negative_count"),
                pl.when(finite & (pl.col(name) > 0)).then(pl.col(name).abs()).otherwise(0.0).sum().alias(f"{name}__material_positive_abs_sum"),
                pl.when(finite & (pl.col(name) < 0)).then(pl.col(name).abs()).otherwise(0.0).sum().alias(f"{name}__material_negative_abs_sum"),
                clean.sum().alias(f"{name}__material_signed_sum"),
                clean.abs().sum().alias(f"{name}__material_abs_sum"),
                clean.abs().pow(2).sum().alias(f"{name}__material_abs_square_sum"),
            ])
    stats_row = lf.select(exprs).collect(engine="streaming").to_dicts()[0] if exprs else {}

    metric_stats: dict[str, dict[str, Any]] = {}
    candidate_rows: dict[str, dict[str, list[tuple[float, int, dict[str, Any]]]]] = {}
    group_stats_by_metric: dict[str, dict[str, dict[str, Any]]] = {}
    for name in present:
        valid = int(stats_row.get(f"{name}__valid") or 0)
        policy = policies[name]
        threshold = float(policy["threshold"])
        metric_stats[name] = {
            "source_column": str(specs[name].get("source_name") or name),
            "valid": valid,
            "null_or_invalid": max(0, rows_scanned - valid),
            "positive": int(stats_row.get(f"{name}__positive") or 0),
            "negative": int(stats_row.get(f"{name}__negative") or 0),
            "sum": float(stats_row.get(f"{name}__sum") or 0.0),
            "abs_sum": float(stats_row.get(f"{name}__abs_sum") or 0.0),
            "min": stats_row.get(f"{name}__min"),
            "max": stats_row.get(f"{name}__max"),
            "material_count": int(stats_row.get(f"{name}__material_count") or 0),
            "material_positive_count": int(stats_row.get(f"{name}__material_positive_count") or 0),
            "material_negative_count": int(stats_row.get(f"{name}__material_negative_count") or 0),
            "material_positive_abs_sum": float(stats_row.get(f"{name}__material_positive_abs_sum") or 0.0),
            "material_negative_abs_sum": float(stats_row.get(f"{name}__material_negative_abs_sum") or 0.0),
            "material_signed_sum": float(stats_row.get(f"{name}__material_signed_sum") or 0.0),
            "material_abs_sum": float(stats_row.get(f"{name}__material_abs_sum") or 0.0),
            "material_abs_square_sum": float(stats_row.get(f"{name}__material_abs_square_sum") or 0.0),
        }
        finite = pl.col(name).is_finite()
        if threshold > 0:
            candidate_lf = lf.filter(finite & (pl.col(name).abs() > threshold))
            cap = int(policy["candidate_cap"])
        else:
            candidate_lf = lf.filter(finite)
            cap = int(policy["top_k"])
        candidate_rows[name] = {}
        group_stats_by_metric[name] = {}
        if cap <= 0:
            continue

        group_source = str(specs[name].get("coverage_group_by_source") or "")
        if group_source and group_source in candidate_lf.collect_schema().names():
            grouped_stats = (
                candidate_lf
                .with_columns(pl.col(group_source).cast(pl.String).fill_null("<missing>").alias("__coverage_group"))
                .group_by("__coverage_group")
                .agg([
                    pl.len().alias("material_count"),
                    pl.col(name).abs().sum().alias("material_abs_sum"),
                    pl.col(name).sum().alias("material_signed_sum"),
                    pl.col(name).abs().pow(2).sum().alias("material_abs_square_sum"),
                ])
                .collect(engine="streaming")
            )
            for row in grouped_stats.to_dicts():
                key = str(row.get("__coverage_group") or "<missing>")
                group_stats_by_metric[name][key] = {
                    "material_count": int(row.get("material_count") or 0),
                    "material_abs_sum": float(row.get("material_abs_sum") or 0.0),
                    "material_signed_sum": float(row.get("material_signed_sum") or 0.0),
                    "material_abs_square_sum": float(row.get("material_abs_square_sum") or 0.0),
                }
            top = (
                candidate_lf
                .with_columns(pl.col(group_source).cast(pl.String).fill_null("<missing>").alias("__coverage_group"))
                .sort(pl.col(name).abs(), descending=True)
                .group_by("__coverage_group", maintain_order=True)
                .head(cap)
                .collect(engine="streaming")
            )
        else:
            group_stats_by_metric[name]["__all__"] = {
                "material_count": int(metric_stats[name].get("material_count") or 0),
                "material_abs_sum": float(metric_stats[name].get("material_abs_sum") or 0.0),
                "material_signed_sum": float(metric_stats[name].get("material_signed_sum") or 0.0),
                "material_abs_square_sum": float(metric_stats[name].get("material_abs_square_sum") or 0.0),
            }
            top = candidate_lf.top_k(cap, by=pl.col(name).abs()).collect(engine="streaming")

        for raw_row in top.to_dicts():
            row_number = int(raw_row["__row_index"])
            value = float(raw_row.get(name) or 0.0)
            group_key = str(raw_row.get("__coverage_group") or "__all__")
            payload = {
                "row_number": row_number,
                "identity": {c: raw_row.get(c) for c in ids if raw_row.get(c) is not None},
                "dimensions": {c: raw_row.get(c) for c in dims if raw_row.get(c) is not None},
                "metrics": {m: raw_row.get(m) for m in present if raw_row.get(m) is not None},
                "selected_metrics": [],
            }
            candidate_rows[name].setdefault(group_key, []).append((abs(value), row_number, payload))
        for key in list(candidate_rows[name]):
            candidate_rows[name][key].sort(key=lambda item: (-item[0], item[1]))

    selected_by_row: dict[int, dict[str, Any]] = {}
    warnings: list[str] = []
    for name in present:
        stats = metric_stats[name]
        chosen: list[tuple[float, int, dict[str, Any]]] = []
        metric_warnings: list[str] = []
        group_selection: dict[str, dict[str, Any]] = {}
        for group_key, rows in candidate_rows[name].items():
            group_stats = group_stats_by_metric[name].get(group_key) or {}
            group_chosen, selection_stats, group_warnings = _select_metric_candidates(
                rows,
                policy=policies[name],
                material_abs_sum=float(group_stats.get("material_abs_sum") or 0.0),
                material_count=int(group_stats.get("material_count") or 0),
            )
            group_scores = [score for score, _, _ in rows]
            group_abs = float(group_stats.get("material_abs_sum") or 0.0)
            group_signed = float(group_stats.get("material_signed_sum") or 0.0)
            group_sq = float(group_stats.get("material_abs_square_sum") or 0.0)
            selection_stats.update({
                "top1_share_pct": round(100 * sum(group_scores[:1]) / group_abs, 2) if group_abs else 0.0,
                "top3_share_pct": round(100 * sum(group_scores[:3]) / group_abs, 2) if group_abs else 0.0,
                "top10_share_pct": round(100 * sum(group_scores[:10]) / group_abs, 2) if group_abs else 0.0,
                "material_cancellation_pct": round(100 * max(0.0, 1 - abs(group_signed) / group_abs), 2) if group_abs else 0.0,
                "material_hhi": round(group_sq / (group_abs * group_abs), 8) if group_abs else 0.0,
                "effective_contributors": round((group_abs * group_abs) / group_sq, 2) if group_sq > 0 else 0.0,
            })
            group_selection[group_key] = selection_stats
            chosen.extend(group_chosen)
            metric_warnings.extend(f"{group_key}: {warning}" for warning in group_warnings)
        chosen.sort(key=lambda item: (-item[0], item[1]))
        if len(group_selection) == 1 and "__all__" in group_selection:
            stats.update(group_selection["__all__"])
        else:
            coverages = [float(v.get("selected_coverage_pct") or 0.0) for v in group_selection.values()]
            stats.update({
                "selection_mode": "threshold+coverage-by-group",
                "coverage_group_by": specs[name].get("coverage_group_by_source"),
                "coverage_groups": group_selection,
                "selected_count": len(chosen),
                "selected_coverage_pct": round(min(coverages), 2) if coverages else None,
                "coverage_aggregation": "minimum per-group coverage (native units are not summed across groups)",
            })
        total_abs = float(stats.get("abs_sum") or 0.0)
        material_abs = float(stats.get("material_abs_sum") or 0.0)
        stats["threshold_capture_pct_of_all_abs_movement"] = round(100 * material_abs / total_abs, 2) if total_abs else 0.0
        stats["subthreshold_abs_sum"] = max(0.0, total_abs - material_abs)
        total_signed = float(stats.get("sum") or 0.0)
        material_signed = float(stats.get("material_signed_sum") or 0.0)
        stats["subthreshold_signed_sum"] = total_signed - material_signed
        stats["all_net_to_gross_pct"] = round(100 * abs(total_signed) / total_abs, 2) if total_abs else 0.0
        stats["material_net_to_gross_pct"] = round(100 * abs(material_signed) / material_abs, 2) if material_abs else 0.0
        stats["material_cancellation_pct"] = round(100 * max(0.0, 1 - abs(material_signed) / material_abs), 2) if material_abs else 0.0
        valid_count = int(stats.get("valid") or 0)
        stats["material_row_pct"] = round(100 * int(stats.get("material_count") or 0) / valid_count, 4) if valid_count else 0.0
        scores = [score for rows in candidate_rows[name].values() for score, _, _ in rows]
        scores.sort(reverse=True)
        stats["top1_share_pct"] = round(100 * sum(scores[:1]) / material_abs, 2) if material_abs else 0.0
        stats["top3_share_pct"] = round(100 * sum(scores[:3]) / material_abs, 2) if material_abs else 0.0
        stats["top10_share_pct"] = round(100 * sum(scores[:10]) / material_abs, 2) if material_abs else 0.0
        square_sum = float(stats.get("material_abs_square_sum") or 0.0)
        hhi = square_sum / (material_abs * material_abs) if material_abs else 0.0
        stats["material_hhi"] = round(hhi, 8)
        stats["effective_contributors"] = round(1.0 / hhi, 2) if hhi > 0 else 0.0
        if len(group_selection) > 1 or (group_selection and "__all__" not in group_selection):
            for field in (
                "threshold_capture_pct_of_all_abs_movement",
                "all_net_to_gross_pct",
                "material_net_to_gross_pct",
                "material_cancellation_pct",
                "subthreshold_abs_sum",
                "subthreshold_signed_sum",
                "top1_share_pct",
                "top3_share_pct",
                "top10_share_pct",
                "material_hhi",
                "effective_contributors",
            ):
                stats[field] = None
            stats["native_amounts_additive"] = False
            stats["multi_unit_note"] = "Coverage/concentration is reported per currency group; raw native amounts are not summed across currencies."
        for warning in metric_warnings:
            warnings.append(f"{name}: {warning}")
        for score, row_number, row in chosen:
            selected = selected_by_row.setdefault(row_number, dict(row))
            selected.setdefault("selected_metrics", [])
            if name not in selected["selected_metrics"]:
                selected["selected_metrics"].append(name)
            threshold = float(policies[name]["threshold"])
            normalized = score / threshold if threshold > 0 else score
            selected["selection_score"] = max(float(selected.get("selection_score") or 0.0), normalized)

    material = sorted(selected_by_row.values(), key=lambda row: (-float(row.get("selection_score") or 0.0), int(row["row_number"])))
    return {"backend": "polars", "rows_scanned": rows_scanned, "metric_stats": metric_stats, "material_rows": material, "warnings": warnings}


def select_material_rows(
    path: str | Path,
    *,
    metrics: list[dict[str, Any]],
    identity_columns: list[str],
    dimension_columns: list[str],
    delimiter: str,
    top_k: int = 50,
    backend: str = "auto",
) -> dict[str, Any]:
    if backend not in {"auto", "polars", "streaming"}:
        raise ValueError("backend must be auto, polars, or streaming")
    if backend in {"auto", "polars"} and pl is not None:
        return polars_select_material(path, metrics=metrics, identity_columns=identity_columns, dimension_columns=dimension_columns, delimiter=delimiter, top_k=top_k)
    if backend == "polars" and pl is None:
        raise RuntimeError("Polars backend requested but polars is not installed. Install quant-skillhub[fastcsv] or polars.")
    result = streaming_select_material(path, metrics=metrics, identity_columns=identity_columns, dimension_columns=dimension_columns, delimiter=delimiter, top_k=top_k)
    if pl is None:
        result["warnings"].append("Polars is not installed; used the lower-throughput bounded-memory Python streaming backend.")
    return result


def enrich_rows(path: str | Path, row_numbers: set[int], *, delimiter: str, max_columns: int = 120, backend: str = "auto") -> tuple[list[str], list[dict[str, str]]]:
    """Read only selected rows while scanning the source once. Prefer Polars when available."""
    if backend in {"auto", "polars"} and pl is not None and row_numbers:
        lf = pl.scan_csv(str(path), separator=delimiter, ignore_errors=True, infer_schema_length=10_000).with_row_index("__row_number", offset=2)
        fields = [c for c in lf.collect_schema().names() if c != "__row_number"][:max_columns]
        frame = (
            lf.filter(pl.col("__row_number").is_in(sorted(row_numbers)))
            .select(["__row_number", *fields])
            .collect(engine="streaming")
        )
        rows = []
        for raw in frame.to_dicts():
            rows.append({k: "" if v is None else str(v) for k, v in raw.items()})
        return fields, rows
    if backend == "polars" and pl is None:
        raise RuntimeError("Polars backend requested but polars is not installed")
    result: list[dict[str, str]] = []
    with Path(path).open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        fieldnames = list(reader.fieldnames or [])[:max_columns]
        for row_number, row in enumerate(reader, start=2):
            if row_number in row_numbers:
                result.append({"__row_number": str(row_number), **{name: row.get(name, "") for name in fieldnames}})
    return fieldnames, result


def detect_patterns(
    material_rows: list[dict[str, Any]],
    enriched_rows: list[dict[str, str]],
    metric_names: list[str],
    excluded: set[str],
    *,
    preferred_dimensions: list[str] | None = None,
    max_cardinality: int = 50,
    min_row_share: float = 0.5,
    min_abs_contribution_share: float = 0.2,
) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    """Detect both frequent and economically concentrated categorical patterns.

    A value can be interesting even when it occurs in few rows if it explains a large share of
    absolute movement.  That matters in CCR where one Legal Entity can dominate the release
    impact with only a handful of aggregation rows.
    """
    if not material_rows or not enriched_rows:
        return [], {}
    metrics_by_row = {int(row["row_number"]): row.get("metrics") or {} for row in material_rows}
    columns = [c for c in enriched_rows[0] if c != "__row_number"]
    patterns: list[dict[str, Any]] = []
    impacted: dict[str, list[str]] = {}
    total = len(enriched_rows)
    preferred = set(preferred_dimensions or [])
    metric_abs_totals = {
        name: sum(abs(float(values.get(name) or 0.0)) for values in metrics_by_row.values())
        for name in metric_names
    }

    for column in columns:
        if column in excluded:
            continue
        groups: dict[str, list[int]] = defaultdict(list)
        for row in enriched_rows:
            value = str(row.get(column, "")).strip()
            if not value:
                continue
            groups[value].append(int(row.get("__row_number", 0)))
        if not groups or len(groups) > max_cardinality or len(groups) == total:
            continue
        if len(groups) == 1 and column not in preferred:
            continue

        candidates: list[dict[str, Any]] = []
        for value, row_numbers in groups.items():
            contribution: dict[str, Any] = {}
            max_abs_share = 0.0
            for name in metric_names:
                group_sum = sum(float(metrics_by_row.get(rn, {}).get(name) or 0.0) for rn in row_numbers)
                group_abs = sum(abs(float(metrics_by_row.get(rn, {}).get(name) or 0.0)) for rn in row_numbers)
                total_sum = sum(float(values.get(name) or 0.0) for values in metrics_by_row.values())
                total_abs = metric_abs_totals[name]
                abs_share = 100 * group_abs / total_abs if total_abs else 0.0
                max_abs_share = max(max_abs_share, abs_share)
                contribution[name] = {
                    "sum": round(group_sum, 10),
                    "share_of_signed_selected_pct": round(100 * group_sum / total_sum, 2) if total_sum else None,
                    "share_of_absolute_selected_pct": round(abs_share, 2),
                }
            row_share = len(row_numbers) / total
            candidates.append({
                "dimension": column,
                "value": value,
                "count": len(row_numbers),
                "material_row_count": total,
                "row_share_pct": round(100 * row_share, 2),
                "max_abs_contribution_share_pct": round(max_abs_share, 2),
                "metric_contribution": contribution,
            })

        candidates.sort(key=lambda row: (-float(row["max_abs_contribution_share_pct"]), -float(row["row_share_pct"]), str(row["value"])))
        impacted[column] = [str(row["value"]) for row in candidates[:500]]
        for row in candidates[:10]:
            if (
                float(row["row_share_pct"]) / 100 >= min_row_share
                or float(row["max_abs_contribution_share_pct"]) / 100 >= min_abs_contribution_share
                or column in preferred and len(candidates) <= 5
            ):
                patterns.append(row)

    patterns.sort(key=lambda row: (-float(row.get("max_abs_contribution_share_pct") or 0.0), -float(row.get("row_share_pct") or 0.0), str(row.get("dimension"))))
    return patterns, impacted


def _derive_deal_value(raw: str, *, regex: str, fallback_to_source: bool) -> str | None:
    text = str(raw or "").strip()
    if not text:
        return None
    match = re.search(regex, text)
    if match:
        return str(match.group(1)).strip()
    return text if fallback_to_source else None


def _finalize_deal_metric(
    rows: list[tuple[float, dict[str, Any], dict[str, float]]],
    *,
    spec: dict[str, Any],
    total_all_abs: float,
    top_k: int,
) -> tuple[list[tuple[float, dict[str, Any], dict[str, float]]], dict[str, Any], list[str]]:
    policy = _policy(spec, top_k)
    threshold = float(policy["threshold"])
    material = [item for item in rows if threshold <= 0 or item[0] > threshold]
    material.sort(key=lambda item: item[0], reverse=True)
    material_abs = sum(item[0] for item in material)
    material_signed = sum(float(item[2].get("sum") or 0.0) for item in material)
    material_positive = [item for item in material if float(item[2].get("sum") or 0.0) > 0]
    material_negative = [item for item in material if float(item[2].get("sum") or 0.0) < 0]
    candidate_cap = int(policy["candidate_cap"])
    capped = material[:candidate_cap]
    simple = [(score, i, {"group": group, "acc": acc}) for i, (score, group, acc) in enumerate(capped)]
    chosen_simple, selection, warnings = _select_metric_candidates(
        simple,
        policy=policy,
        material_abs_sum=material_abs,
        material_count=len(material),
    )
    chosen = [(score, item["group"], item["acc"]) for score, _, item in chosen_simple]
    total_all_signed = sum(float(item[2].get("sum") or 0.0) for item in rows)
    selection.update({
        "deal_count_all": len(rows),
        "absolute_net_total_all_deals": total_all_abs,
        "signed_total_all_deals": total_all_signed,
        "material_deal_count": len(material),
        "material_positive_deal_count": len(material_positive),
        "material_negative_deal_count": len(material_negative),
        "material_positive_abs_total": sum(item[0] for item in material_positive),
        "material_negative_abs_total": sum(item[0] for item in material_negative),
        "material_signed_total": material_signed,
        "material_abs_total": material_abs,
        "subthreshold_abs_total": max(0.0, total_all_abs - material_abs),
        "subthreshold_signed_total": total_all_signed - material_signed,
        "threshold_capture_pct_of_all_abs_movement": round(100 * material_abs / total_all_abs, 2) if total_all_abs else 0.0,
        "all_net_to_gross_pct": round(100 * abs(total_all_signed) / total_all_abs, 2) if total_all_abs else 0.0,
        "material_net_to_gross_pct": round(100 * abs(material_signed) / material_abs, 2) if material_abs else 0.0,
        "material_cancellation_pct": round(100 * max(0.0, 1 - abs(material_signed) / material_abs), 2) if material_abs else 0.0,
        "material_hhi": round(sum(score * score for score, _, _ in material) / (material_abs * material_abs), 8) if material_abs else 0.0,
        "effective_contributors": round((material_abs * material_abs) / sum(score * score for score, _, _ in material), 2) if material_abs and sum(score * score for score, _, _ in material) else 0.0,
    })
    denom = material_abs
    scores = [score for score, _, _ in material]
    selection.update({
        "top1_share_pct": round(100 * sum(scores[:1]) / denom, 2) if denom else 0.0,
        "top3_share_pct": round(100 * sum(scores[:3]) / denom, 2) if denom else 0.0,
        "top10_share_pct": round(100 * sum(scores[:10]) / denom, 2) if denom else 0.0,
    })
    selection.update(_coverage_contributor_counts(scores, denom))
    return chosen, selection, warnings


def filter_and_rank_deals(
    path: str | Path,
    *,
    delimiter: str,
    filters: dict[str, set[str]],
    deal_columns: list[str],
    metrics: list[dict[str, Any]],
    deal_derivation: dict[str, Any] | None = None,
    top_k: int = 100,
    backend: str = "auto",
) -> dict[str, Any]:
    """Filter early, aggregate by deal, then keep only material deal contributors.

    Metrics may declare ``coverage_group_by_source``. This is used by CCR MTF00 to keep
    native-currency Pareto coverage separate (EUR, USD, ...), while EUR-normalized EEPE is
    still aggregated globally. Deal IDs can be derived from ``AggregationLevel`` via TRD:.
    """
    metric_names = [str(m["name"]) for m in metrics]
    specs = {str(m["name"]): m for m in metrics}
    derivation = dict(deal_derivation or {})
    derivation_source = str(derivation.get("source_column") or "")
    derivation_regex = str(derivation.get("regex") or r"(?:^|/)TRD:([^/]+)")
    derived_name = str(derivation.get("output_name") or "DealId")
    fallback_to_source = bool(derivation.get("fallback_to_source", True))

    def _combine_grouped_selection(
        metric: str,
        grouped_rows: dict[str, list[tuple[float, dict[str, Any], dict[str, float]]]],
    ) -> tuple[list[tuple[float, dict[str, Any], dict[str, float]]], dict[str, Any], list[str]]:
        spec = specs[metric]
        if set(grouped_rows) == {"__all__"}:
            rows = grouped_rows["__all__"]
            total_abs = sum(score for score, _, _ in rows)
            return _finalize_deal_metric(rows, spec=spec, total_all_abs=total_abs, top_k=top_k)

        selected: list[tuple[float, dict[str, Any], dict[str, float]]] = []
        group_stats: dict[str, Any] = {}
        warnings: list[str] = []
        for group_key, rows in sorted(grouped_rows.items()):
            total_abs = sum(score for score, _, _ in rows)
            chosen, stats, local_warnings = _finalize_deal_metric(rows, spec=spec, total_all_abs=total_abs, top_k=top_k)
            group_stats[group_key] = stats
            selected.extend(chosen)
            warnings.extend(f"{group_key}: {w}" for w in local_warnings)
        selected.sort(key=lambda item: item[0], reverse=True)
        coverages = [float(v.get("selected_coverage_pct") or 0.0) for v in group_stats.values()]
        summary = {
            "selection_mode": "threshold+coverage-by-group",
            "coverage_group_by": spec.get("coverage_group_by_source"),
            "coverage_groups": group_stats,
            "selected_count": len(selected),
            "selected_coverage_pct": round(min(coverages), 2) if coverages else None,
            "coverage_aggregation": "minimum per-group coverage (native units are not summed across groups)",
            "native_amounts_additive": False,
            "material_deal_count": sum(int(v.get("material_deal_count") or 0) for v in group_stats.values()),
            "material_positive_deal_count": sum(int(v.get("material_positive_deal_count") or 0) for v in group_stats.values()),
            "material_negative_deal_count": sum(int(v.get("material_negative_deal_count") or 0) for v in group_stats.values()),
            "top1_share_pct": None,
            "top3_share_pct": None,
            "top10_share_pct": None,
            "material_cancellation_pct": None,
            "material_hhi": None,
            "effective_contributors": None,
            "threshold_capture_pct_of_all_abs_movement": None,
            "multi_unit_note": "Coverage/concentration is reported per currency group; raw native amounts are not summed across currencies.",
        }
        return selected, summary, warnings

    if backend in {"auto", "polars"} and pl is not None:
        raw = pl.scan_csv(str(path), separator=delimiter, ignore_errors=True, infer_schema_length=10_000).with_row_index("__row_number", offset=2)
        schema = set(raw.collect_schema().names())
        present_filters = {c: allowed for c, allowed in filters.items() if c in schema and allowed}
        present_deals = [c for c in deal_columns if c in schema]
        source_metrics = [str(specs[name].get("source_name") or name) for name in metric_names]
        coverage_sources = [
            str(specs[name].get("coverage_group_by_source"))
            for name in metric_names
            if specs[name].get("coverage_group_by_source") and str(specs[name].get("coverage_group_by_source")) in schema
        ]
        selected = list(dict.fromkeys([*present_deals, *present_filters.keys(), *source_metrics, *coverage_sources, *([derivation_source] if derivation_source in schema else [])]))
        lf = raw.select(["__row_number", *[c for c in selected if c in schema]])
        casts = []
        for name in metric_names:
            source = str(specs[name].get("source_name") or name)
            if source in schema:
                casts.append(pl.col(source).cast(pl.Float64, strict=False).alias(name))
        if casts:
            lf = lf.with_columns(casts)

        if not present_deals and derivation_source in schema:
            extracted = pl.col(derivation_source).cast(pl.String).str.extract(derivation_regex, group_index=1)
            if fallback_to_source:
                extracted = extracted.fill_null(pl.col(derivation_source).cast(pl.String))
            lf = lf.with_columns(extracted.alias(derived_name))
            present_deals = [derived_name]

        predicate = None
        for column, allowed in present_filters.items():
            expr = pl.col(column).cast(pl.String).is_in(sorted(allowed))
            predicate = expr if predicate is None else (predicate & expr)
        matched_lf = lf.filter(predicate) if predicate is not None else lf
        matched_count = int(matched_lf.select(pl.len()).collect(engine="streaming").item())
        scanned = int(raw.select(pl.len()).collect(engine="streaming").item())
        present_metrics = [name for name in metric_names if name in matched_lf.collect_schema().names()]

        impacts: list[dict[str, Any]] = []
        concentration: dict[str, dict[str, Any]] = {}
        warnings: list[str] = []
        for metric in present_metrics:
            group_source = str(specs[metric].get("coverage_group_by_source") or "")
            use_group = bool(group_source and group_source in matched_lf.collect_schema().names())
            group_columns = list(dict.fromkeys([*present_deals, *present_filters.keys(), *([group_source] if use_group else [])]))
            if not group_columns:
                group_columns = ["__row_number"]
            finite = pl.col(metric).is_finite()
            metric_lf = matched_lf.filter(finite)
            grouped = metric_lf.group_by(group_columns).agg([
                pl.col(metric).sum().alias("__sum"),
                pl.col(metric).abs().sum().alias("__gross_abs"),
                pl.len().alias("__rows"),
            ])
            frame = grouped.collect(engine="streaming")
            grouped_rows: dict[str, list[tuple[float, dict[str, Any], dict[str, float]]]] = defaultdict(list)
            for raw_row in frame.to_dicts():
                identity = {c: raw_row.get(c) for c in present_deals if raw_row.get(c) is not None}
                dims = {c: raw_row.get(c) for c in present_filters if raw_row.get(c) is not None}
                if use_group and raw_row.get(group_source) is not None:
                    dims[group_source] = raw_row.get(group_source)
                acc = {"sum": float(raw_row.get("__sum") or 0.0), "gross_abs": float(raw_row.get("__gross_abs") or 0.0)}
                group = {"row_number": raw_row.get("__row_number"), "identity": identity, "dimensions": dims, "rows": int(raw_row.get("__rows") or 0)}
                key = str(raw_row.get(group_source) or "<missing>") if use_group else "__all__"
                grouped_rows[key].append((abs(acc["sum"]), group, acc))

            chosen, stats, metric_warnings = _combine_grouped_selection(metric, grouped_rows)
            concentration[metric] = stats
            warnings.extend(f"{metric}: {w}" for w in metric_warnings)
            for _, group, acc in chosen:
                gross = float(acc["gross_abs"] or 0.0)
                net = float(acc["sum"] or 0.0)
                cancellation_pct = round(100 * max(0.0, 1 - abs(net) / gross), 2) if gross else 0.0
                impacts.append({
                    "row_number": group["row_number"],
                    "metric": metric,
                    "value": net,
                    "gross_absolute_value": gross,
                    "within_deal_cancellation_pct": cancellation_pct,
                    "rows_in_deal_group": group["rows"],
                    "identity": group["identity"],
                    "dimensions": group["dimensions"],
                })
        impacts.sort(key=lambda row: abs(float(row.get("value") or 0.0)), reverse=True)
        return {
            "backend": "polars",
            "rows_scanned": scanned,
            "rows_matching_filters": matched_count,
            "deal_impacts": impacts,
            "concentration": concentration,
            "warnings": warnings,
            "derived_deal_column": derived_name if not deal_columns and derivation_source in schema else None,
        }

    if backend == "polars" and pl is None:
        raise RuntimeError("Polars backend requested but polars is not installed")

    scanned = matched = 0
    metric_groups: dict[str, dict[tuple[Any, ...], dict[str, Any]]] = {name: {} for name in metric_names}
    warnings: list[str] = []
    with Path(path).open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        actual_metric_sources = {name: str(specs[name].get("source_name") or name) for name in metric_names}
        for row_number, row in enumerate(reader, start=2):
            scanned += 1
            if any(allowed and str(row.get(column, "")) not in allowed for column, allowed in filters.items()):
                continue
            matched += 1
            identity = {c: row.get(c) for c in deal_columns if row.get(c) not in (None, "")}
            if not identity and derivation_source:
                deal = _derive_deal_value(row.get(derivation_source, ""), regex=derivation_regex, fallback_to_source=fallback_to_source)
                if deal:
                    identity[derived_name] = deal
            dims_base = {k: row.get(k) for k in filters if row.get(k) not in (None, "")}
            key_values = tuple(identity.get(c, "") for c in sorted(identity)) if identity else (row_number,)
            for metric in metric_names:
                value = _number(row.get(actual_metric_sources[metric]))
                if value is None:
                    continue
                group_source = str(specs[metric].get("coverage_group_by_source") or "")
                coverage_group = str(row.get(group_source, "") or "<missing>") if group_source else "__all__"
                dims = dict(dims_base)
                if group_source:
                    dims[group_source] = coverage_group
                key = (*key_values, *tuple(dims_base.get(c, "") for c in filters), *( [coverage_group] if group_source else [] ))
                group = metric_groups[metric].setdefault(
                    key,
                    {"row_number": row_number if not identity else None, "identity": dict(identity), "dimensions": dims, "rows": 0, "acc": {"sum": 0.0, "gross_abs": 0.0}, "coverage_group": coverage_group},
                )
                group["rows"] += 1
                group["acc"]["sum"] += value
                group["acc"]["gross_abs"] += abs(value)

    impacts: list[dict[str, Any]] = []
    concentration: dict[str, dict[str, Any]] = {}
    for metric in metric_names:
        grouped_rows: dict[str, list[tuple[float, dict[str, Any], dict[str, float]]]] = defaultdict(list)
        for group in metric_groups[metric].values():
            acc = group["acc"]
            grouped_rows[str(group.get("coverage_group") or "__all__")].append((abs(float(acc["sum"])), group, acc))
        chosen, stats, metric_warnings = _combine_grouped_selection(metric, grouped_rows)
        concentration[metric] = stats
        warnings.extend(f"{metric}: {w}" for w in metric_warnings)
        for _, group, acc in chosen:
            gross = float(acc["gross_abs"] or 0.0)
            net = float(acc["sum"] or 0.0)
            cancellation_pct = round(100 * max(0.0, 1 - abs(net) / gross), 2) if gross else 0.0
            impacts.append({
                "row_number": group["row_number"],
                "metric": metric,
                "value": net,
                "gross_absolute_value": gross,
                "within_deal_cancellation_pct": cancellation_pct,
                "rows_in_deal_group": group["rows"],
                "identity": group["identity"],
                "dimensions": group["dimensions"],
            })
    impacts.sort(key=lambda row: abs(float(row.get("value") or 0.0)), reverse=True)
    return {
        "backend": "python-streaming",
        "rows_scanned": scanned,
        "rows_matching_filters": matched,
        "deal_impacts": impacts,
        "concentration": concentration,
        "warnings": warnings,
        "derived_deal_column": derived_name if derivation_source and not deal_columns else None,
    }


def enrich_selected_deals(
    path: str | Path,
    *,
    delimiter: str,
    filters: dict[str, set[str]],
    deal_columns: list[str],
    deal_derivation: dict[str, Any] | None,
    selected_deals: set[str],
    diagnostic_columns: list[str],
    max_rows: int = 5000,
    backend: str = "auto",
) -> dict[str, Any]:
    """Read only diagnostic columns for already-selected backtesting deals.

    This is intentionally a second, narrow pass: keeping diagnostics for every deal during the
    first pass would destroy bounded-memory behavior. With Polars, column projection keeps the
    pass cheap; the Python fallback remains streaming and bounded by ``max_rows``.
    """
    if not selected_deals:
        return {"backend": "none", "rows": [], "warnings": []}

    derivation = dict(deal_derivation or {})
    derivation_source = str(derivation.get("source_column") or "")
    derivation_regex = str(derivation.get("regex") or r"(?:^|/)TRD:([^/]+)")
    derived_name = str(derivation.get("output_name") or "DealId")
    fallback_to_source = bool(derivation.get("fallback_to_source", True))

    if backend in {"auto", "polars"} and pl is not None:
        raw = pl.scan_csv(str(path), separator=delimiter, ignore_errors=True, infer_schema_length=10_000).with_row_index("__row_number", offset=2)
        schema = set(raw.collect_schema().names())
        present_filters = {c: allowed for c, allowed in filters.items() if c in schema and allowed}
        present_deals = [c for c in deal_columns if c in schema]
        selected_cols = [c for c in diagnostic_columns if c in schema]
        needed = list(dict.fromkeys([*present_deals, *present_filters.keys(), *selected_cols, *([derivation_source] if derivation_source in schema else [])]))
        lf = raw.select(["__row_number", *needed])
        if present_deals:
            deal_expr = pl.col(present_deals[0]).cast(pl.String)
        elif derivation_source in schema:
            deal_expr = pl.col(derivation_source).cast(pl.String).str.extract(derivation_regex, group_index=1)
            if fallback_to_source:
                deal_expr = deal_expr.fill_null(pl.col(derivation_source).cast(pl.String))
        else:
            return {"backend": "polars", "rows": [], "warnings": ["Could not resolve a deal identifier for diagnostic enrichment."]}
        lf = lf.with_columns(deal_expr.alias("__deal_id"))
        predicate = pl.col("__deal_id").is_in(sorted(selected_deals))
        for column, allowed in present_filters.items():
            predicate = predicate & pl.col(column).cast(pl.String).is_in(sorted(allowed))
        frame = lf.filter(predicate).head(max_rows + 1).collect(engine="streaming")
        rows = frame.to_dicts()
        truncated = len(rows) > max_rows
        rows = rows[:max_rows]
        warnings = [f"Selected-deal diagnostic enrichment was capped at {max_rows} rows."] if truncated else []
        return {
            "backend": "polars",
            "rows": [{k: "" if v is None else str(v) for k, v in row.items()} for row in rows],
            "warnings": warnings,
        }

    if backend == "polars" and pl is None:
        raise RuntimeError("Polars backend requested but polars is not installed")

    result: list[dict[str, str]] = []
    truncated = False
    with Path(path).open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        fieldnames = set(reader.fieldnames or [])
        actual_diag = [c for c in diagnostic_columns if c in fieldnames]
        for row_number, row in enumerate(reader, start=2):
            if any(allowed and str(row.get(column, "")) not in allowed for column, allowed in filters.items()):
                continue
            deal = None
            for column in deal_columns:
                value = str(row.get(column, "") or "").strip()
                if value:
                    deal = value
                    break
            if deal is None and derivation_source:
                deal = _derive_deal_value(row.get(derivation_source, ""), regex=derivation_regex, fallback_to_source=fallback_to_source)
            if not deal or str(deal) not in selected_deals:
                continue
            if len(result) >= max_rows:
                truncated = True
                break
            result.append(
                {
                    "__row_number": str(row_number),
                    "__deal_id": str(deal),
                    **{column: str(row.get(column, "") or "") for column in actual_diag},
                }
            )
    warnings = [f"Selected-deal diagnostic enrichment was capped at {max_rows} rows."] if truncated else []
    return {"backend": "python-streaming", "rows": result, "warnings": warnings}
