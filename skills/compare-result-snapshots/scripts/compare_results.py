from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            raise ValueError(f"{path} has no header")
        return list(reader.fieldnames), list(reader)


def number(value: str | None) -> float | None:
    if value is None:
        return None
    text = value.strip().replace(" ", "")
    if not text:
        return None
    try:
        return float(text.replace(",", ""))
    except ValueError:
        return None


def detect_numeric(
    common: list[str], before: list[dict], after: list[dict], keys: set[str]
) -> list[str]:
    detected: list[str] = []
    for column in common:
        if column in keys:
            continue
        values = [number(row.get(column)) for row in (before[:50] + after[:50])]
        valid = [value for value in values if value is not None]
        if valid and len(valid) >= max(1, len(values) // 2):
            detected.append(column)
    return detected


def relative_pct(delta: float, base: float) -> float | None:
    if abs(base) < 1e-15:
        return None
    return 100.0 * delta / base


def key_of(row: dict, keys: list[str]) -> tuple[str, ...]:
    return tuple(row.get(key, "") for key in keys)


def finite(value: float) -> bool:
    return math.isfinite(value)


def keyed_rows(rows: list[dict], keys: list[str], label: str) -> dict[tuple[str, ...], dict]:
    output: dict[tuple[str, ...], dict] = {}
    duplicates: list[tuple[str, ...]] = []
    for row in rows:
        key = key_of(row, keys)
        if key in output:
            duplicates.append(key)
        output[key] = row
    if duplicates:
        sample = ", ".join(map(str, duplicates[:5]))
        raise ValueError(
            f"Duplicate key(s) in {label}: {sample}. Choose keys that uniquely identify rows."
        )
    return output


def compare(
    before_path: Path,
    after_path: Path,
    keys: list[str],
    metrics: list[str],
    top: int,
) -> dict:
    header_before, before = read_csv(before_path)
    header_after, after = read_csv(after_path)
    after_columns = set(header_after)
    common = [column for column in header_before if column in after_columns]
    column_changes = {
        "only_before": [column for column in header_before if column not in after_columns],
        "only_after": [column for column in header_after if column not in set(header_before)],
    }

    for key in keys:
        if key not in common:
            raise ValueError(f"Key column '{key}' is not present in both files")

    if not metrics:
        metrics = detect_numeric(common, before, after, set(keys))
    if not metrics:
        raise ValueError("No common numeric metric columns were detected; pass --metrics explicitly")
    for metric in metrics:
        if metric not in common:
            raise ValueError(f"Metric column '{metric}' is not present in both files")

    summaries: list[dict] = []
    for metric in metrics:
        before_values = [number(row.get(metric)) for row in before]
        after_values = [number(row.get(metric)) for row in after]
        before_sum = sum(v for v in before_values if v is not None and finite(v))
        after_sum = sum(v for v in after_values if v is not None and finite(v))
        delta = after_sum - before_sum
        summaries.append(
            {
                "metric": metric,
                "before_sum": before_sum,
                "after_sum": after_sum,
                "absolute_delta": delta,
                "relative_delta_pct": relative_pct(delta, before_sum),
                "before_numeric_rows": sum(v is not None for v in before_values),
                "after_numeric_rows": sum(v is not None for v in after_values),
            }
        )

    row_result = {
        "available": bool(keys),
        "keys": keys,
        "added_key_count": 0,
        "removed_key_count": 0,
        "added_keys": [],
        "removed_keys": [],
        "top_movers": [],
    }
    if keys:
        before_map = keyed_rows(before, keys, "before snapshot")
        after_map = keyed_rows(after, keys, "after snapshot")
        before_keys = set(before_map)
        after_keys = set(after_map)
        added = sorted(after_keys - before_keys)
        removed = sorted(before_keys - after_keys)
        row_result["added_key_count"] = len(added)
        row_result["removed_key_count"] = len(removed)
        row_result["added_keys"] = [dict(zip(keys, key)) for key in added[:top]]
        row_result["removed_keys"] = [dict(zip(keys, key)) for key in removed[:top]]

        movers: list[dict] = []
        for key in before_keys & after_keys:
            for metric in metrics:
                before_value = number(before_map[key].get(metric))
                after_value = number(after_map[key].get(metric))
                if before_value is None or after_value is None:
                    continue
                delta = after_value - before_value
                movers.append(
                    {
                        "key": dict(zip(keys, key)),
                        "metric": metric,
                        "before": before_value,
                        "after": after_value,
                        "absolute_delta": delta,
                        "absolute_magnitude": abs(delta),
                        "relative_delta_pct": relative_pct(delta, before_value),
                    }
                )
        movers.sort(
            key=lambda row: (
                -row["absolute_magnitude"],
                row["metric"],
                tuple(row["key"].values()),
            )
        )
        for mover in movers:
            mover.pop("absolute_magnitude", None)
        row_result["top_movers"] = movers[:top]

    summaries.sort(key=lambda row: -abs(row["absolute_delta"]))
    return {
        "schema_version": 1,
        "before": str(before_path),
        "after": str(after_path),
        "rows": {"before": len(before), "after": len(after)},
        "column_changes": column_changes,
        "metrics": summaries,
        "row_analysis": row_result,
    }


def render_md(result: dict) -> str:
    lines = [
        "# Result snapshot comparison",
        "",
        f"Before: `{result['before']}`  ",
        f"After: `{result['after']}`  ",
        f"Rows: {result['rows']['before']} → {result['rows']['after']}",
        "",
        "## Aggregate metrics",
        "",
        "| Metric | Before sum | After sum | Δ | Δ% |",
        "|---|---:|---:|---:|---:|",
    ]
    for metric in result["metrics"]:
        relative = (
            "—"
            if metric["relative_delta_pct"] is None
            else f"{metric['relative_delta_pct']:.4g}%"
        )
        lines.append(
            f"| {metric['metric']} | {metric['before_sum']:.8g} | {metric['after_sum']:.8g} | "
            f"{metric['absolute_delta']:.8g} | {relative} |"
        )

    row_analysis = result["row_analysis"]
    if row_analysis["available"]:
        lines += [
            "",
            "## Composition",
            "",
            f"Added keys: **{row_analysis['added_key_count']}** · "
            f"Removed keys: **{row_analysis['removed_key_count']}**",
            "",
            "## Largest row-level movers",
            "",
        ]
        for mover in row_analysis["top_movers"][:15]:
            lines.append(
                f"- `{mover['key']}` · **{mover['metric']}**: {mover['before']:.8g} → "
                f"{mover['after']:.8g} (Δ {mover['absolute_delta']:.8g})"
            )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare two CSV snapshots deterministically")
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--keys", default="")
    parser.add_argument("--metrics", default="")
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--output", type=Path, default=Path("metric-analysis"))
    args = parser.parse_args()
    try:
        keys = [value.strip() for value in args.keys.split(",") if value.strip()]
        metrics = [value.strip() for value in args.metrics.split(",") if value.strip()]
        result = compare(args.before, args.after, keys, metrics, max(1, args.top))
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / "comparison.json").write_text(
            json.dumps(result, indent=2), encoding="utf-8"
        )
        (args.output / "comparison-summary.md").write_text(
            render_md(result), encoding="utf-8"
        )
        print(
            json.dumps(
                {
                    "success": True,
                    "output": str(args.output),
                    "metrics": len(result["metrics"]),
                    "top_movers": len(result["row_analysis"]["top_movers"]),
                },
                indent=2,
            )
        )
        return 0
    except (OSError, ValueError, csv.Error) as exc:
        print(json.dumps({"success": False, "error": str(exc)}, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
