from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from skillhub.runtime.artifacts import ensure_output_dir, file_metadata, write_json
from skillhub.runtime.ccr import classify_deal, deal_id_from_path, legal_entity_from_path, master_id_from_path
from skillhub.runtime.evidence import load_evidence, write_evidence
from skillhub.runtime.profiling import StageTimer
from skillhub.runtime.workbook import is_excel, materialize_ccr_comparison_workbook


METRICS = ("Mtf00Gap", "EepeInEurGap")


def _truth(value: Any) -> bool | None:
    text = str(value or "").strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    return None


def _first(row: dict[str, Any], *names: str) -> str:
    lower = {str(k).strip().lower(): k for k in row}
    for name in names:
        key = lower.get(name.strip().lower())
        if key is not None:
            return str(row.get(key) or "").strip()
    return ""


def _category(error_type: str, message: str) -> str:
    text = f"{error_type} {message}".lower()
    rules = [
        ("dead_trade", ["dead trade"]),
        ("unpriced_netting_set", ["nothing has been found to price", "unable to price", "price the netting set"]),
        ("mtm_failed", ["mtms failed", "mtm failed"]),
        ("missing_schedule", ["schedule not found"]),
        ("missing_rate_index", ["not managed rate indexes", "not managed rate index"]),
        ("missing_market_data", ["marketdataid", "market data", "missing data for ccr diffusion"]),
        ("strike_conversion", ["cannot convert a relative strike"]),
        ("loading", [" loading ", "loading"]),
        ("pricing", [" pricing ", "pricing"]),
    ]
    for name, needles in rules:
        if any(needle in text for needle in needles):
            return name
    return "other"


def _short(value: str, limit: int = 350) -> str:
    value = value.replace("\r", " ").replace("\n", " ").strip()
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _add_path_scope(text: str, les: set[str], deals: set[str], masters: set[str]) -> None:
    if not text:
        return
    le = legal_entity_from_path(text)
    deal = deal_id_from_path(text)
    master = master_id_from_path(text)
    if le:
        les.add(le)
    if deal:
        deals.add(deal)
    if master:
        masters.add(master)


def _scope_from_rows(rows: list[dict[str, Any]]) -> tuple[set[str], set[str], set[str]]:
    les: set[str] = set()
    deals: set[str] = set()
    masters: set[str] = set()
    for row in rows:
        for source in (row.get("identity") or {}, row.get("dimensions") or {}):
            for key, value in source.items():
                low = str(key).lower()
                text = str(value or "").strip()
                if not text:
                    continue
                if "legalentity" in low or "legal entity" in low:
                    les.add(text)
                if low in {"deal", "dealid", "tradeid"}:
                    deals.add(text)
                if "aggregation" in low or "netting" in low:
                    _add_path_scope(text, les, deals, masters)
    return les, deals, masters


def _impacted(upstream: dict[str, Any]) -> tuple[set[str], set[str], set[str]]:
    les: set[str] = set()
    deals: set[str] = set()
    masters: set[str] = set()
    for key, values in (upstream.get("impacted_dimensions") or {}).items():
        low = str(key).lower()
        for value in values or []:
            text = str(value or "").strip()
            if not text:
                continue
            if "legalentity" in low or "legal entity" in low:
                les.add(text)
            if low in {"deal", "dealid", "tradeid"}:
                deals.add(text)
            if "aggregation" in low or "netting" in low:
                _add_path_scope(text, les, deals, masters)
    r_les, r_deals, r_masters = _scope_from_rows(list(upstream.get("material_impacts") or []))
    return les | r_les, deals | r_deals, masters | r_masters


def _impacted_by_metric(upstream: dict[str, Any]) -> dict[str, tuple[set[str], set[str], set[str]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in upstream.get("material_impacts") or []:
        metric = str(row.get("metric") or "").strip()
        if metric:
            grouped.setdefault(metric, []).append(row)
    return {metric: _scope_from_rows(rows) for metric, rows in grouped.items()}


def _scope_matches(le: str, trade: str, master: str, scope: tuple[set[str], set[str], set[str]]) -> bool:
    les, deals, masters = scope
    if not les and not deals and not masters:
        return False
    return (bool(le) and le in les) or (bool(trade) and trade in deals) or (bool(master) and master in masters)


def main() -> int:
    p = argparse.ArgumentParser(description="Find ErrorByTrade asymmetries that can explain material CCR release impacts.")
    p.add_argument("--input", required=True, help="ErrorByTrade.xlsx (or normalized CSV)")
    p.add_argument("--evidence", required=True, help="Upstream CVAR/GCVAR or backtesting evidence JSON")
    p.add_argument("--output", required=True)
    p.add_argument("--max-relevant", type=int, default=2000)
    args = p.parse_args()

    timer = StageTimer()
    source = Path(args.input).expanduser().resolve()
    out = ensure_output_dir(args.output)
    upstream = load_evidence(args.evidence)
    impacted_les, impacted_deals, impacted_masters = _impacted(upstream)
    metric_scopes = _impacted_by_metric(upstream)

    # Keep one scan of the error workbook but preserve separate MTF00/EEPE linkage.
    metric_links: dict[str, dict[str, Any]] = {}
    for metric, (les, deals, masters) in metric_scopes.items():
        metric_links[metric] = {
            "requested_legal_entities": len(les),
            "requested_deals": len(deals),
            "requested_masters": len(masters),
            "linked_legal_entities": set(),
            "linked_deals": set(),
            "linked_masters": set(),
            "asymmetric_rows": 0,
            "error_categories": Counter(),
        }

    original_source = source
    workbook = None
    if is_excel(source):
        with timer.measure("xlsx_normalization"):
            workbook = materialize_ccr_comparison_workbook(source, cache_dir=out / "_cache", purpose="ccr-errors")
        source = workbook.path

    state_counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    family_counts: Counter[str] = Counter()
    legal_entity_counts: Counter[str] = Counter()
    deal_counts: Counter[str] = Counter()
    relevant: list[dict[str, Any]] = []
    rows_scanned = 0
    rows_matching_scope = 0
    asymmetric = 0
    impacted_deals_with_asymmetry: set[str] = set()
    impacted_les_with_asymmetry: set[str] = set()

    with timer.measure("error_scan"):
        with source.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                rows_scanned += 1
                netting = _first(row, "NettingSetId", "NettingSet", "AggregationLevel")
                trade = _first(row, "TradeId", "DealId", "TradeReference") or deal_id_from_path(netting) or ""
                le = legal_entity_from_path(netting) or _first(row, "LegalEntity", "GroupingCriterionId")
                master = master_id_from_path(netting) or ""
                global_scope = (impacted_les, impacted_deals, impacted_masters)
                in_scope = (not impacted_les and not impacted_deals and not impacted_masters) or _scope_matches(le, trade, master, global_scope)
                if not in_scope:
                    continue
                rows_matching_scope += 1

                presence = _first(row, "PresenceState")
                sheet = _first(row, "WorkbookSheet")
                msg_ref = _first(row, "Message (Ref)", "Message Ref")
                msg_test = _first(row, "Message (Test)", "Message Test")
                result = _truth(_first(row, "Message (Result)", "Message Result"))
                if presence == "test_only":
                    state = "introduced_in_test"
                elif presence == "ref_only":
                    state = "removed_in_test"
                elif result is False or (msg_ref and msg_test and msg_ref != msg_test):
                    state = "changed_between_ref_and_test"
                else:
                    state = "same_or_unresolved"
                is_asymmetric = state != "same_or_unresolved"

                error_type = _first(row, "ErrorType")
                message = msg_test or msg_ref
                category = _category(error_type, message)
                family = classify_deal(trade)

                if is_asymmetric:
                    asymmetric += 1
                    if trade:
                        impacted_deals_with_asymmetry.add(trade)
                    if le:
                        impacted_les_with_asymmetry.add(le)
                    for metric, scope in metric_scopes.items():
                        if not _scope_matches(le, trade, master, scope):
                            continue
                        link = metric_links[metric]
                        link["asymmetric_rows"] += 1
                        link["error_categories"][category] += 1
                        if le and le in scope[0]:
                            link["linked_legal_entities"].add(le)
                        if trade and trade in scope[1]:
                            link["linked_deals"].add(trade)
                        if master and master in scope[2]:
                            link["linked_masters"].add(master)

                state_counts[state] += 1
                category_counts[category] += 1
                family_counts[family] += 1
                if le:
                    legal_entity_counts[le] += 1
                if trade:
                    deal_counts[trade] += 1
                if len(relevant) < args.max_relevant and (is_asymmetric or len(relevant) < 100):
                    relevant.append(
                        {
                            "sheet": sheet,
                            "presence_state": presence,
                            "error_state": state,
                            "legal_entity": le or None,
                            "deal_id": trade or None,
                            "master_id": master or None,
                            "deal_family": family,
                            "netting_set": _short(netting, 500),
                            "error_type": error_type or None,
                            "category": category,
                            "analysis_index": _first(row, "AnalysisIndex") or None,
                            "message_ref": _short(msg_ref),
                            "message_test": _short(msg_test),
                            "message_result": _first(row, "Message (Result)") or None,
                        }
                    )

    deal_link_pct = 100 * len(impacted_deals_with_asymmetry & impacted_deals) / len(impacted_deals) if impacted_deals else None
    le_link_pct = 100 * len(impacted_les_with_asymmetry & impacted_les) / len(impacted_les) if impacted_les else None

    metric_linkage: dict[str, Any] = {}
    for metric, raw in metric_links.items():
        req_le = int(raw["requested_legal_entities"])
        req_deal = int(raw["requested_deals"])
        req_master = int(raw["requested_masters"])
        linked_le = len(raw["linked_legal_entities"])
        linked_deal = len(raw["linked_deals"])
        linked_master = len(raw["linked_masters"])
        metric_linkage[metric] = {
            "asymmetric_error_rows": int(raw["asymmetric_rows"]),
            "requested_legal_entities": req_le,
            "linked_legal_entities": linked_le,
            "legal_entity_link_pct": round(100 * linked_le / req_le, 2) if req_le else None,
            "requested_deals": req_deal,
            "linked_deals": linked_deal,
            "deal_link_pct": round(100 * linked_deal / req_deal, 2) if req_deal else None,
            "requested_masters": req_master,
            "linked_masters": linked_master,
            "master_link_pct": round(100 * linked_master / req_master, 2) if req_master else None,
            "error_categories": dict(raw["error_categories"].most_common(12)),
        }

    summary = {
        "rows_scanned": rows_scanned,
        "rows_matching_impacted_scope": rows_matching_scope,
        "asymmetric_error_rows": asymmetric,
        "impacted_legal_entities_requested": len(impacted_les),
        "impacted_deals_requested": len(impacted_deals),
        "impacted_masters_requested": len(impacted_masters),
        "impacted_legal_entities_with_asymmetric_error": len(impacted_les_with_asymmetry & impacted_les),
        "impacted_deals_with_asymmetric_error": len(impacted_deals_with_asymmetry & impacted_deals),
        "impacted_legal_entity_error_link_pct": round(le_link_pct, 2) if le_link_pct is not None else None,
        "impacted_deal_error_link_pct": round(deal_link_pct, 2) if deal_link_pct is not None else None,
    }
    patterns = [
        {
            "dimension": "error-state",
            "value": k,
            "count": v,
            "material_row_count": rows_matching_scope,
            "row_share_pct": round(100 * v / rows_matching_scope, 2) if rows_matching_scope else 0,
        }
        for k, v in state_counts.most_common()
    ] + [
        {
            "dimension": "error-category",
            "value": k,
            "count": v,
            "material_row_count": rows_matching_scope,
            "row_share_pct": round(100 * v / rows_matching_scope, 2) if rows_matching_scope else 0,
        }
        for k, v in category_counts.most_common(12)
    ]
    warnings: list[str] = []
    if not impacted_les and not impacted_deals and not impacted_masters:
        warnings.append("Upstream evidence contained no LegalEntity/deal/master scope; the entire error workbook was scanned as relevant.")
    if len(relevant) >= args.max_relevant:
        warnings.append(f"Relevant error detail was capped at {args.max_relevant} rows; aggregate counts remain complete.")

    evidence = {
        "schema_version": "1.0",
        "evidence_type": "ccr-error-forensics",
        "title": "CCR error asymmetry evidence",
        "source": {
            **file_metadata(original_source),
            "normalized_table": str(source) if source != original_source else None,
            "input_format": "xlsx" if workbook else "csv",
            "workbook_sheets": workbook.sheets if workbook else None,
            "workbook_cache_hit": workbook.cache_hit if workbook else None,
            "upstream_evidence": str(Path(args.evidence).resolve()),
        },
        "summary": summary,
        "metric_linkage": metric_linkage,
        "material_impacts": relevant[:100],
        "patterns": patterns,
        "impacted_dimensions": {
            "LegalEntity": sorted(impacted_les_with_asymmetry)[:100],
            "Deal": sorted(impacted_deals_with_asymmetry)[:200],
        },
        "error_state_counts": dict(state_counts),
        "error_category_counts": dict(category_counts),
        "deal_family_counts": dict(family_counts),
        "top_legal_entities": legal_entity_counts.most_common(30),
        "top_deals": deal_counts.most_common(50),
        "relevant_errors": relevant,
        "timings": timer.timings,
        "warnings": warnings,
    }
    write_evidence(out / "error_summary.json", evidence)

    with (out / "relevant_errors.csv").open("w", encoding="utf-8", newline="") as handle:
        fields = list(relevant[0]) if relevant else ["sheet", "error_state", "legal_entity", "deal_id", "category"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(relevant)

    lines = [
        "# CCR error-forensics context",
        "",
        "> Deterministic comparison of ErrorByTrade asymmetries on already-impacted Legal Entities/masters/deals. Raw workbook content is not embedded.",
        "",
        f"- Rows scanned: {rows_scanned}",
        f"- Rows matching impacted scope: {rows_matching_scope}",
        f"- Asymmetric errors: {asymmetric}",
        f"- Impacted LE with asymmetric error: {summary['impacted_legal_entities_with_asymmetric_error']}/{summary['impacted_legal_entities_requested']}",
        f"- Impacted deals with asymmetric error: {summary['impacted_deals_with_asymmetric_error']}/{summary['impacted_deals_requested']}",
        "",
        "## Metric-specific linkage",
    ]
    for metric in METRICS:
        link = metric_linkage.get(metric)
        if not link:
            continue
        lines.append(
            f"- **{metric}**: asymmetric rows={link['asymmetric_error_rows']}; "
            f"LE linked={link['linked_legal_entities']}/{link['requested_legal_entities']}; "
            f"deals linked={link['linked_deals']}/{link['requested_deals']}; "
            f"masters linked={link['linked_masters']}/{link['requested_masters']}."
        )
        if link["error_categories"]:
            lines.append("  - categories: " + ", ".join(f"{k}={v}" for k, v in link["error_categories"].items()))
    lines += ["", "## Error states"]
    lines += [f"- {k}: {v}" for k, v in state_counts.most_common()]
    lines += ["", "## Error categories"]
    lines += [f"- {k}: {v}" for k, v in category_counts.most_common(12)]
    lines += ["", "## Deal families"]
    lines += [f"- {k}: {v}" for k, v in family_counts.most_common()]
    lines += [
        "",
        "## Interpretation rule",
        "An asymmetric error on an impacted LE/master/deal is a strong explanation candidate, not automatic proof. Correlate side, metric movement, deal pattern and release code changes before calling causality.",
    ]
    (out / "agent_context.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    write_json(
        out / "run_manifest.json",
        {
            "input": file_metadata(original_source),
            "upstream_evidence": str(Path(args.evidence).resolve()),
            "artifacts": ["error_summary.json", "relevant_errors.csv", "agent_context.md"],
            "timings": timer.timings,
        },
    )
    print(json.dumps({"ok": True, "output": str(out), **summary, "metric_linkage": metric_linkage}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
