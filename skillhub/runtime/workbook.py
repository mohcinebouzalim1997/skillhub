from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


EXCEL_SUFFIXES = {".xlsx", ".xlsm"}


@dataclass(frozen=True)
class MaterializedTable:
    path: Path
    source_path: Path
    format: str
    cache_hit: bool
    rows: int
    columns: int
    sheets: dict[str, int]
    elapsed_seconds: float


def is_excel(path: str | Path) -> bool:
    return Path(path).suffix.lower() in EXCEL_SUFFIXES


def _cache_key(path: Path, *, purpose: str, sheet_names: Iterable[str]) -> str:
    stat = path.stat()
    raw = json.dumps(
        {
            "path": str(path.resolve()),
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "purpose": purpose,
            "sheets": list(sheet_names),
            "schema": 3,
        },
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:20]


def _excel_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float) and not math.isfinite(value):
        return ""
    return value


def _header(values: Iterable[Any]) -> list[str]:
    result: list[str] = []
    seen: dict[str, int] = {}
    for index, value in enumerate(values, start=1):
        name = str(value).strip() if value is not None else ""
        if not name:
            name = f"Column{index}"
        count = seen.get(name, 0)
        seen[name] = count + 1
        if count:
            name = f"{name}__{count + 1}"
        result.append(name)
    return result


def _find_header(headers: list[str], candidates: Iterable[str]) -> str | None:
    lower = {h.strip().lower(): h for h in headers}
    for candidate in candidates:
        found = lower.get(str(candidate).strip().lower())
        if found:
            return found
    return None


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    text = str(value).strip()
    if not text:
        return None
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]
    text = text.replace("\u00a0", "").replace(" ", "")
    if text.endswith("%"):
        text = text[:-1]
        scale = 0.01
    else:
        scale = 1.0
    try:
        number = float(text) * scale
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _derived_gap(
    row: dict[str, Any],
    headers: list[str],
    *,
    gap_aliases: list[str],
    ref_aliases: list[str],
    test_aliases: list[str],
    presence_state: str,
) -> float | None:
    gap_col = _find_header(headers, gap_aliases)
    if gap_col:
        existing = _num(row.get(gap_col))
        if existing is not None:
            return existing
    ref_col = _find_header(headers, ref_aliases)
    test_col = _find_header(headers, test_aliases)
    ref_value = _num(row.get(ref_col)) if ref_col else None
    test_value = _num(row.get(test_col)) if test_col else None
    if presence_state == "test_only":
        if test_value is not None:
            return test_value
        if ref_value is not None:
            return ref_value
    if presence_state == "ref_only":
        if ref_value is not None:
            return -ref_value
        if test_value is not None:
            return -test_value
    if ref_value is not None and test_value is not None:
        return test_value - ref_value
    return None


def _load_openpyxl():
    try:
        from openpyxl import load_workbook  # type: ignore
    except ImportError as exc:  # pragma: no cover - workstation dependency
        raise RuntimeError(
            "Excel input requires openpyxl. Install SkillHub CCR extras with: pip install -e \".[ccr]\""
        ) from exc
    return load_workbook


def workbook_sheet_names(path: str | Path) -> list[str]:
    source = Path(path).expanduser().resolve()
    load_workbook = _load_openpyxl()
    wb = load_workbook(source, read_only=True, data_only=True, keep_links=False)
    try:
        return list(wb.sheetnames)
    finally:
        wb.close()


def materialize_ccr_comparison_workbook(
    path: str | Path,
    *,
    cache_dir: str | Path,
    purpose: str = "ccr-comparison",
    sheet_roles: dict[str, str] | None = None,
) -> MaterializedTable:
    """Convert a CCR comparison workbook into one cached normalized CSV.

    The compare jobs use three sheets:
      * Details  -> present in reference and test
      * Non Ref  -> present only in test/candidate
      * Non Test -> present only in reference/production

    Side-only rows are assigned signed synthetic gaps when explicit gap columns are absent:
    Test-only => +Test value, Ref-only => -Ref value. This makes materiality/coverage include
    additions/removals without asking the LLM to inspect side sheets separately.
    """
    source = Path(path).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(source)
    if not is_excel(source):
        return MaterializedTable(source, source, "csv", True, 0, 0, {}, 0.0)

    roles = sheet_roles or {"Details": "matched", "Non Ref": "test_only", "Non Test": "ref_only"}
    cache_root = Path(cache_dir).expanduser().resolve()
    cache_root.mkdir(parents=True, exist_ok=True)
    key = _cache_key(source, purpose=purpose, sheet_names=roles)
    csv_path = cache_root / f"{source.stem}.{key}.normalized.csv"
    meta_path = cache_root / f"{source.stem}.{key}.meta.json"
    if csv_path.exists() and meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            return MaterializedTable(
                csv_path,
                source,
                "xlsx-normalized-csv",
                True,
                int(meta.get("rows", 0)),
                int(meta.get("columns", 0)),
                dict(meta.get("sheets") or {}),
                float(meta.get("elapsed_seconds", 0.0)),
            )
        except Exception:
            pass

    started = time.perf_counter()
    load_workbook = _load_openpyxl()
    wb = load_workbook(source, read_only=True, data_only=True, keep_links=False)
    try:
        available = set(wb.sheetnames)
        missing = [name for name in roles if name not in available]
        if missing:
            raise ValueError(f"Workbook {source.name} is missing required sheets: {', '.join(missing)}")

        # Read only headers first so we can create one stable union schema.
        headers_by_sheet: dict[str, list[str]] = {}
        union_headers: list[str] = []
        for sheet_name in roles:
            ws = wb[sheet_name]
            iterator = ws.iter_rows(min_row=1, max_row=1, values_only=True)
            try:
                headers = _header(next(iterator))
            except StopIteration:
                headers = []
            headers_by_sheet[sheet_name] = headers
            for header in headers:
                if header not in union_headers:
                    union_headers.append(header)

        synthetic = ["WorkbookSheet", "PresenceState", "IsStructuralChange"]
        for name in synthetic:
            if name not in union_headers:
                union_headers.append(name)
        for name in ("Mtf00 Gap", "EepeInEur Gap"):
            if name not in union_headers:
                union_headers.append(name)

        sheet_counts: dict[str, int] = {name: 0 for name in roles}
        total_rows = 0
        temp = csv_path.with_suffix(csv_path.suffix + ".tmp")
        with temp.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=union_headers, extrasaction="ignore")
            writer.writeheader()
            for sheet_name, presence_state in roles.items():
                ws = wb[sheet_name]
                headers = headers_by_sheet[sheet_name]
                for values in ws.iter_rows(min_row=2, values_only=True):
                    if not values or all(v is None or str(v).strip() == "" for v in values):
                        continue
                    row = {headers[i]: _excel_value(values[i]) if i < len(values) else "" for i in range(len(headers))}
                    row["WorkbookSheet"] = sheet_name
                    row["PresenceState"] = presence_state
                    row["IsStructuralChange"] = "TRUE" if presence_state != "matched" else "FALSE"
                    # Preserve the native MTF currency on side-only rows. The analysis profile
                    # groups MTF00 coverage by Currency (Test) first, so copy the surviving side
                    # across only when its peer is blank; this never changes matched rows.
                    c_ref = _find_header(headers, ["Currency (Ref)", "Currency Ref", "Currency"])
                    c_test = _find_header(headers, ["Currency (Test)", "Currency Test", "Currency"])
                    if c_ref and c_test:
                        if presence_state == "ref_only" and not str(row.get(c_test) or "").strip():
                            row[c_test] = row.get(c_ref, "")
                        elif presence_state == "test_only" and not str(row.get(c_ref) or "").strip():
                            row[c_ref] = row.get(c_test, "")
                    row["Mtf00 Gap"] = _derived_gap(
                        row,
                        headers,
                        gap_aliases=["Mtf00 Gap", "Mtf00Gap", "mtf00Gap"],
                        ref_aliases=["Mtf00 (Ref)", "Mtf00 Ref", "Mtf00"],
                        test_aliases=["Mtf00 (Test)", "Mtf00 Test", "Mtf00"],
                        presence_state=presence_state,
                    )
                    row["EepeInEur Gap"] = _derived_gap(
                        row,
                        headers,
                        gap_aliases=["EepeInEur Gap", "EepeInEurGap", "eepeInEurGap"],
                        ref_aliases=["EepeInEur (Ref)", "EepeInEur Ref", "EepeInEur"],
                        test_aliases=["EepeInEur (Test)", "EepeInEur Test", "EepeInEur"],
                        presence_state=presence_state,
                    )
                    writer.writerow(row)
                    total_rows += 1
                    sheet_counts[sheet_name] += 1
        os.replace(temp, csv_path)
        elapsed = round(time.perf_counter() - started, 6)
        meta = {
            "source": str(source),
            "rows": total_rows,
            "columns": len(union_headers),
            "sheets": sheet_counts,
            "elapsed_seconds": elapsed,
            "roles": roles,
        }
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return MaterializedTable(csv_path, source, "xlsx-normalized-csv", False, total_rows, len(union_headers), sheet_counts, elapsed)
    finally:
        wb.close()
