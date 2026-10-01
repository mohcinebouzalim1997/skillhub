# Changelog

## 0.5.0 — 2026-10-01

- Switched the primary CCR contract from flat CSV assumptions to three-sheet XLSX result workbooks (`Details`, `Non Ref`, `Non Test`).
- Added read-only XLSX normalization/cache with structural Test-only/Ref-only signed gap derivation.
- Preserved the compact evidence contract so agents never need raw workbook rows.
- Kept CSV compatibility for generic/legacy use while documenting XLSX as the production CCR path.

## 0.3.0 — 2026-09-30

- Added native-currency-aware MTF00 Pareto selection: EUR/USD (and any other observed currency) are covered independently rather than summed.
- Added top-1/top-3/top-10, HHI/effective-contributor, cancellation, threshold-capture and 50/80/90/95% contributor-count diagnostics.
- Added selected-row secondary numeric diagnostics for MTF/EEPE/RWA gaps and ratios.
- Added robust percentage parsing for ratio fields exported as `0.25%` or parenthesized negatives.
- Calibrated dimensions and Ref/Test/Result clues to the supplied CVAR/GCVAR compare layout.
- Added aggregation-path shape diagnostics (for example `LegalEntity>Master`) and explicit selected AggregationLevel reporting without treating high-cardinality IDs as categorical patterns.

## 0.2.0 — 2026-09-30

- Calibrated to the real CCR CVAR/GCVAR compare-file structure shown by the team.
- Added real header aliases such as `Mtf00 Gap` and `EepeInEur Gap`.
- Default materiality is strict `abs(gap) > 10,000`.
- Added configurable Pareto coverage selection (90% default; 80%/other targets supported).
- Added bounded candidate caps to protect memory on huge files.
- Added contribution-aware Legal Entity/dimension pattern detection.
- Added Ref/Test pair diagnostics, `(Result)`-flag summaries and MTF00/EEPE relationship diagnostics.

## 0.1.0

- Initial large-result reduction skill.
