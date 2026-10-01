# Changelog

## 0.4.0 — 2026-10-01

- Rebuilt the workflow for real XLSX result/backtesting workbooks and matching three-sheet `ErrorByTrade.xlsx` inputs.
- Encoded CVAR MTF00-first → deal attribution → error correlation → EEPE-second reasoning.
- Added GCVAR-vs-CVAR signature gating to avoid redundant expensive GCVAR deep scans.
- Added compact root-cause routing, deal-family/error-category PR hints, and `expected_dev_change` / `suspected_bug` / `inconclusive` synthesis contract.

## 0.2.0 — 2026-09-30

- Added one-command CVAR + GCVAR + targeted backtesting workspace preparation using the calibrated real compare schema.
- Compact workflow context now exposes impact concentration, contributor ladders, Ref/Test clues, ratio/RWA diagnostics and deal evidence without embedding raw CSVs.
- Added optional generic `release-pr-forensics` prefetch between production and candidate refs.
- Standardized the real release naming examples (`release/26.9`, `release/26.10`).

## 0.1.0

- Initial deterministic CCR release-validation workspace preparation.
- CVAR/GCVAR compare reduction, targeted backtesting drilldown and compact workflow context.
- Optional reusable release-PR forensics prefetch.
