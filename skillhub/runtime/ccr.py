from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from typing import Any, Iterable


LEGAL_ENTITY_RE = re.compile(r"(?:^|/)LegalEntity:([^/]+)", re.IGNORECASE)
TRD_RE = re.compile(r"(?:^|/)TRD:([^/]+)", re.IGNORECASE)
MASTER_RE = re.compile(r"(?:^|/)Master:([^/]+)", re.IGNORECASE)
PREFIX_RE = re.compile(r"^([A-Za-z]+)-")


def legal_entity_from_path(value: Any) -> str | None:
    match = LEGAL_ENTITY_RE.search(str(value or ""))
    return match.group(1) if match else None


def deal_id_from_path(value: Any) -> str | None:
    match = TRD_RE.search(str(value or ""))
    return match.group(1) if match else None


def master_id_from_path(value: Any) -> str | None:
    match = MASTER_RE.search(str(value or ""))
    return match.group(1) if match else None


def classify_deal(deal_id: Any) -> str:
    """Classify the desk family using the convention supplied by the CCR team.

    * no prefix => Equity DPS
    * ELI-      => Equity
    * any other explicit prefix => FIC
    """
    text = str(deal_id or "").strip()
    if not text:
        return "unknown"
    match = PREFIX_RE.match(text)
    if not match:
        return "equity_dps"
    if match.group(1).upper() == "ELI":
        return "equity"
    return "fic"


def _impact_rows(evidence: dict[str, Any], metric: str) -> list[dict[str, Any]]:
    return [row for row in (evidence.get("material_impacts") or []) if str(row.get("metric")) == metric]


def _identity_value(row: dict[str, Any], names: Iterable[str]) -> str | None:
    identity = row.get("identity") or {}
    dims = row.get("dimensions") or {}
    for name in names:
        for source in (identity, dims):
            if name in source and str(source[name]).strip():
                return str(source[name]).strip()
    return None


def mtf_eepe_relationship(evidence: dict[str, Any], *, backtesting: dict[str, Any] | None = None) -> dict[str, Any]:
    """Quantify overlap without pretending MTF00 is the only possible EEPE driver."""
    mtf = _impact_rows(evidence, "Mtf00Gap")
    eepe = _impact_rows(evidence, "EepeInEurGap")
    mtf_rows = {
        _identity_value(row, ["AggregationLevel", "RowId", "DealId", "Deal"]) or f"row:{row.get('row_number')}"
        for row in mtf
    }
    eepe_total = sum(abs(float(row.get("value") or 0.0)) for row in eepe)
    shared_eepe = 0.0
    shared_rows = 0
    for row in eepe:
        key = _identity_value(row, ["AggregationLevel", "RowId", "DealId", "Deal"]) or f"row:{row.get('row_number')}"
        if key in mtf_rows:
            shared_rows += 1
            shared_eepe += abs(float(row.get("value") or 0.0))
    row_coverage = 100.0 * shared_eepe / eepe_total if eepe_total else 0.0

    deal_coverage = None
    shared_deals: list[str] = []
    if backtesting:
        impacts = backtesting.get("material_impacts") or []
        mtf_deals = {
            _identity_value(row, ["DealId", "Deal"]) for row in impacts if row.get("metric") == "Mtf00Gap"
        }
        mtf_deals.discard(None)
        eepe_deals = [row for row in impacts if row.get("metric") == "EepeInEurGap"]
        total = sum(abs(float(row.get("value") or 0.0)) for row in eepe_deals)
        shared = 0.0
        for row in eepe_deals:
            deal = _identity_value(row, ["DealId", "Deal"])
            if deal and deal in mtf_deals:
                shared += abs(float(row.get("value") or 0.0))
                shared_deals.append(deal)
        deal_coverage = 100.0 * shared / total if total else 0.0

    signal = max(row_coverage, deal_coverage or 0.0)
    if signal >= 70:
        classification = "strong_mtf00_overlap"
    elif signal >= 30:
        classification = "partial_mtf00_overlap"
    else:
        classification = "weak_or_no_mtf00_overlap"
    return {
        "classification": classification,
        "selected_eepe_rows": len(eepe),
        "selected_mtf00_rows": len(mtf),
        "eepe_abs_share_on_mtf00_selected_rows_pct": round(row_coverage, 2),
        "eepe_abs_share_on_mtf00_selected_deals_pct": round(deal_coverage, 2) if deal_coverage is not None else None,
        "shared_selected_rows": shared_rows,
        "shared_deals": list(dict.fromkeys(shared_deals))[:100],
        "interpretation_rule": (
            "Overlap is a routing clue, not proof. EEPE may be driven by MTF00, by other MTFs not visible in this compare file, "
            "or by non-MTF model/data changes."
        ),
    }


def branch_signature_similarity(cvar: dict[str, Any], gcvar: dict[str, Any]) -> dict[str, Any]:
    """Cheap GCVAR precheck so we do not repeat expensive drilldowns for a mirrored CVAR issue."""
    c_dims = cvar.get("impacted_dimensions") or {}
    g_dims = gcvar.get("impacted_dimensions") or {}

    def values(dims: dict[str, Any], token: str) -> set[str]:
        out: set[str] = set()
        for key, vals in dims.items():
            if token in str(key).lower():
                out.update(str(v) for v in vals or [] if str(v))
        return out

    c_le, g_le = values(c_dims, "legalentity"), values(g_dims, "legalentity")
    if not c_le:
        c_le = values(c_dims, "legal entity")
    if not g_le:
        g_le = values(g_dims, "legal entity")
    union = c_le | g_le
    le_jaccard = len(c_le & g_le) / len(union) if union else 0.0

    per_metric: dict[str, Any] = {}
    metric_scores: list[float] = []
    for metric in ("Mtf00Gap", "EepeInEurGap"):
        c_rows = _impact_rows(cvar, metric)
        g_rows = _impact_rows(gcvar, metric)
        c_keys = {_identity_value(r, ["AggregationLevel"]) for r in c_rows}
        g_keys = {_identity_value(r, ["AggregationLevel"]) for r in g_rows}
        c_keys.discard(None); g_keys.discard(None)
        key_union = c_keys | g_keys
        key_j = len(c_keys & g_keys) / len(key_union) if key_union else 0.0
        c_net = sum(float(r.get("value") or 0.0) for r in c_rows)
        g_net = sum(float(r.get("value") or 0.0) for r in g_rows)
        same_sign = (c_net == 0 and g_net == 0) or (c_net * g_net > 0)
        score = 0.7 * key_j + 0.3 * (1.0 if same_sign else 0.0)
        per_metric[metric] = {"aggregation_jaccard": round(key_j, 4), "same_net_direction": same_sign, "score": round(score, 4)}
        if c_rows or g_rows:
            metric_scores.append(score)
    metric_score = sum(metric_scores) / len(metric_scores) if metric_scores else 0.0
    score = 0.55 * le_jaccard + 0.45 * metric_score
    return {
        "score": round(score, 4),
        "legal_entity_jaccard": round(le_jaccard, 4),
        "per_metric": per_metric,
        "same_issue_likely": score >= 0.75 and le_jaccard >= 0.6,
        "rule": "Heuristic routing optimization only; a skipped GCVAR deep drilldown can be forced when independent confirmation is required.",
    }


def summarize_deal_families(deal_impacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_metric: dict[str, Counter[str]] = defaultdict(Counter)
    abs_by_metric: dict[str, defaultdict[str, float]] = defaultdict(lambda: defaultdict(float))
    for row in deal_impacts:
        metric = str(row.get("metric") or "unknown")
        identity = row.get("identity") or {}
        deal = identity.get("DealId") or identity.get("Deal") or next(iter(identity.values()), None)
        family = classify_deal(deal)
        by_metric[metric][family] += 1
        abs_by_metric[metric][family] += abs(float(row.get("value") or 0.0))
    output: list[dict[str, Any]] = []
    for metric, counts in by_metric.items():
        total_abs = sum(abs_by_metric[metric].values())
        for family, count in counts.most_common():
            output.append({
                "metric": metric,
                "deal_family": family,
                "selected_deals": count,
                "selected_abs_movement": round(abs_by_metric[metric][family], 8),
                "selected_abs_share_pct": round(100 * abs_by_metric[metric][family] / total_abs, 2) if total_abs else 0.0,
            })
    return output
