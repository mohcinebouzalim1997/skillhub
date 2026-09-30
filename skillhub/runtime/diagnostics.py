from __future__ import annotations

import math
import re
from statistics import mean, median
from typing import Any


def _number(raw: Any) -> float | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
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


def summarize_ref_test_changes(enriched_rows: list[dict[str, str]], *, max_pairs: int = 30, ignore_fields: set[str] | None = None) -> list[dict[str, Any]]:
    """Summarize Ref/Test column-pair changes on the already-selected material rows.

    This lets the LLM see useful clues such as "EffectiveMaturity changed in 92% of the
    material rows" without reading the full compare CSV.
    """
    if not enriched_rows:
        return []
    ignored = {v.lower() for v in (ignore_fields or {"Mtf00", "EepeInEur"})}
    columns = [c for c in enriched_rows[0] if c != "__row_number"]
    by_lower = {c.lower(): c for c in columns}
    pairs: list[tuple[str, str, str]] = []
    for ref in columns:
        match = re.match(r"^(.*?)\s*\(Ref\)$", ref, flags=re.IGNORECASE)
        if not match:
            continue
        base = match.group(1).strip()
        if base.lower() in ignored:
            continue
        test = by_lower.get(f"{base} (Test)".lower())
        if test:
            pairs.append((base, ref, test))

    diagnostics: list[dict[str, Any]] = []
    for base, ref, test in pairs:
        comparable = changed = numeric_pairs = 0
        ref_missing = test_missing = 0
        deltas: list[float] = []
        changed_examples: list[dict[str, Any]] = []
        for row in enriched_rows:
            left_raw = str(row.get(ref, "")).strip()
            right_raw = str(row.get(test, "")).strip()
            if not left_raw:
                ref_missing += 1
            if not right_raw:
                test_missing += 1
            if not left_raw and not right_raw:
                continue
            comparable += 1
            left = _number(left_raw)
            right = _number(right_raw)
            if left is not None and right is not None:
                numeric_pairs += 1
                delta = right - left
                deltas.append(delta)
                is_changed = not math.isclose(left, right, rel_tol=1e-10, abs_tol=1e-12)
            else:
                is_changed = left_raw != right_raw
            if is_changed:
                changed += 1
                if len(changed_examples) < 3:
                    changed_examples.append({"row_number": row.get("__row_number"), "ref": left_raw, "test": right_raw})

        if changed == 0:
            continue
        item: dict[str, Any] = {
            "field": base,
            "ref_column": ref,
            "test_column": test,
            "comparable_rows": comparable,
            "changed_rows": changed,
            "changed_pct": round(100 * changed / comparable, 2) if comparable else 0.0,
            "ref_missing": ref_missing,
            "test_missing": test_missing,
            "examples": changed_examples,
        }
        if numeric_pairs and deltas:
            item.update({
                "numeric_pairs": numeric_pairs,
                "mean_delta_test_minus_ref": round(mean(deltas), 10),
                "median_delta_test_minus_ref": round(median(deltas), 10),
                "mean_abs_delta": round(mean(abs(v) for v in deltas), 10),
                "max_abs_delta": round(max(abs(v) for v in deltas), 10),
            })
        diagnostics.append(item)

    diagnostics.sort(key=lambda row: (-float(row.get("changed_pct") or 0.0), -float(row.get("max_abs_delta") or 0.0), str(row.get("field"))))
    return diagnostics[:max_pairs]


def summarize_result_flags(enriched_rows: list[dict[str, str]], *, max_columns: int = 20) -> list[dict[str, Any]]:
    """Summarize compare-job ``(Result)`` columns, keeping only non-trivial failures."""
    if not enriched_rows:
        return []
    columns = [c for c in enriched_rows[0] if c != "__row_number" and re.search(r"\(Result\)$", c, flags=re.IGNORECASE)]
    trueish = {"true", "1", "yes", "ok", "equal", "match", "matched"}
    rows: list[dict[str, Any]] = []
    for column in columns:
        values = [str(row.get(column, "")).strip() for row in enriched_rows]
        values = [v for v in values if v != ""]
        if not values:
            continue
        non_true = [v for v in values if v.lower() not in trueish]
        if not non_true:
            continue
        counts: dict[str, int] = {}
        for value in non_true:
            counts[value] = counts.get(value, 0) + 1
        rows.append({
            "column": column,
            "rows_with_value": len(values),
            "non_true_rows": len(non_true),
            "non_true_pct": round(100 * len(non_true) / len(values), 2),
            "top_non_true_values": sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:5],
        })
    rows.sort(key=lambda row: (-float(row["non_true_pct"]), str(row["column"])))
    return rows[:max_columns]


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2 or len(xs) != len(ys):
        return None
    mx, my = mean(xs), mean(ys)
    sx = sum((x - mx) ** 2 for x in xs)
    sy = sum((y - my) ** 2 for y in ys)
    if sx <= 0 or sy <= 0:
        return None
    covariance = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    return covariance / math.sqrt(sx * sy)


def summarize_metric_relationships(material_rows: list[dict[str, Any]], metric_specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Describe whether selected CCR gap metrics move together on the same material rows."""
    specs = {str(spec["name"]): spec for spec in metric_specs}
    names = list(specs)
    relationships: list[dict[str, Any]] = []
    for i, left_name in enumerate(names):
        for right_name in names[i + 1 :]:
            xs: list[float] = []
            ys: list[float] = []
            same_sign = sign_pairs = both_material = selected_together = 0
            left_threshold = float(specs[left_name].get("absolute_threshold") or 0.0)
            right_threshold = float(specs[right_name].get("absolute_threshold") or 0.0)
            for row in material_rows:
                metrics = row.get("metrics") or {}
                if left_name not in metrics or right_name not in metrics:
                    continue
                x = float(metrics[left_name])
                y = float(metrics[right_name])
                if not (math.isfinite(x) and math.isfinite(y)):
                    continue
                xs.append(x)
                ys.append(y)
                if x != 0 and y != 0:
                    sign_pairs += 1
                    same_sign += int((x > 0) == (y > 0))
                if abs(x) > left_threshold and abs(y) > right_threshold:
                    both_material += 1
                selected = set(row.get("selected_metrics") or [])
                selected_together += int(left_name in selected and right_name in selected)
            if not xs:
                continue
            corr = _pearson(xs, ys)
            relationships.append({
                "left_metric": left_name,
                "right_metric": right_name,
                "rows_with_both": len(xs),
                "both_over_materiality_threshold": both_material,
                "selected_for_both_metrics": selected_together,
                "same_sign_pct": round(100 * same_sign / sign_pairs, 2) if sign_pairs else None,
                "pearson_correlation": round(corr, 4) if corr is not None else None,
            })
    return relationships


def summarize_numeric_columns(
    enriched_rows: list[dict[str, str]],
    configured: list[dict[str, Any]],
    *,
    max_columns: int = 20,
    max_examples: int = 3,
) -> list[dict[str, Any]]:
    """Summarize selected numeric diagnostic columns without exposing raw rows.

    The CCR compare export already contains useful derived diagnostics such as RWA gap and
    MTF/EEPE ratios.  These are not primary materiality metrics, but they are valuable clues
    once a row has already been selected by MTF00/EEPE materiality.
    """
    if not enriched_rows or not configured:
        return []

    columns = [c for c in enriched_rows[0] if c != "__row_number"]
    lower = {c.lower(): c for c in columns}
    summaries: list[dict[str, Any]] = []
    for spec in configured:
        if not isinstance(spec, dict) or not spec.get("name"):
            continue
        canonical = str(spec["name"])
        source = None
        for candidate in [canonical, *(spec.get("aliases") or [])]:
            source = lower.get(str(candidate).strip().lower())
            if source:
                break
        if not source:
            continue

        values: list[tuple[float, str | None]] = []
        invalid = 0
        for row in enriched_rows:
            raw = row.get(source)
            if raw in (None, ""):
                continue
            value = _number(raw)
            if value is None:
                invalid += 1
                continue
            values.append((value, row.get("__row_number")))
        if not values:
            continue

        nums = [v for v, _ in values]
        abs_sorted = sorted(abs(v) for v in nums)

        def pct(p: float) -> float:
            if not abs_sorted:
                return 0.0
            idx = min(len(abs_sorted) - 1, max(0, int(round((len(abs_sorted) - 1) * p))))
            return abs_sorted[idx]

        top = sorted(values, key=lambda item: abs(item[0]), reverse=True)[:max_examples]
        summaries.append(
            {
                "name": canonical,
                "source_column": source,
                "valid": len(nums),
                "invalid": invalid,
                "nonzero": sum(1 for v in nums if v != 0),
                "positive": sum(1 for v in nums if v > 0),
                "negative": sum(1 for v in nums if v < 0),
                "mean": round(mean(nums), 10),
                "median": round(median(nums), 10),
                "mean_abs": round(mean(abs(v) for v in nums), 10),
                "p90_abs": round(pct(0.90), 10),
                "p95_abs": round(pct(0.95), 10),
                "max_abs": round(max(abs(v) for v in nums), 10),
                "examples": [
                    {"row_number": row_number, "value": value}
                    for value, row_number in top
                ],
            }
        )

    summaries.sort(key=lambda row: (-float(row.get("max_abs") or 0.0), str(row.get("name"))))
    return summaries[:max_columns]


def summarize_aggregation_structure(
    enriched_rows: list[dict[str, str]],
    *,
    column_candidates: tuple[str, ...] = ("AggregationLevel", "AggregationLevelName", "AggregationId"),
    max_patterns: int = 12,
) -> list[dict[str, Any]]:
    """Summarize the *shape* of hierarchical aggregation identifiers without exposing all IDs.

    Examples such as ``/LegalEntity:10/Master:123`` and ``/LegalEntity:10/TRD:ABC`` become
    ``LegalEntity>Master`` and ``LegalEntity>TRD``.  This is useful release evidence because
    it tells the agent which aggregation grain is affected while avoiding high-cardinality
    identifier spam.
    """
    if not enriched_rows:
        return []
    lower = {str(c).lower(): str(c) for c in enriched_rows[0] if c != "__row_number"}
    source = next((lower.get(candidate.lower()) for candidate in column_candidates if lower.get(candidate.lower())), None)
    if not source:
        return []
    counts: dict[str, int] = {}
    rows_with_value = 0
    for row in enriched_rows:
        raw = str(row.get(source, "") or "").strip()
        if not raw:
            continue
        rows_with_value += 1
        keys: list[str] = []
        for segment in raw.strip("/").split("/"):
            if not segment:
                continue
            key = segment.split(":", 1)[0].strip()
            if key:
                keys.append(key)
        shape = ">".join(keys) if keys else "unstructured"
        counts[shape] = counts.get(shape, 0) + 1
    if not rows_with_value:
        return []
    items = [
        {
            "column": source,
            "path_shape": shape,
            "terminal_kind": shape.split(">")[-1] if shape else "unstructured",
            "count": count,
            "share_pct": round(100 * count / rows_with_value, 2),
        }
        for shape, count in counts.items()
    ]
    items.sort(key=lambda item: (-int(item["count"]), str(item["path_shape"])))
    return items[:max_patterns]
