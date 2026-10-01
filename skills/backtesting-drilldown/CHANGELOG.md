# Changelog

## 0.5.0 — 2026-10-01

- Added three-sheet XLSX backtesting normalization and cache reuse.
- Added deal-family classification: no prefix=Equity DPS, `ELI-`=Equity, other explicit prefix=FIC.
- Added MTF00↔EEPE selected-deal overlap routing and retained native-currency MTF00 separation.
- Updated the skill contract around Legal Entity-first filtering of very large backtesting workbooks.

## 0.3.0 — 2026-09-30

- Added native-currency-aware MTF00 deal concentration and 50/80/90/95% contributor-count diagnostics.
- Added a second selective pass over only chosen deals for Ref/Test, Result, RWA and ratio diagnostics.
- Preserved fast upstream Legal Entity filtering and `/TRD:<DEAL_ID>` extraction from backtesting AggregationLevel.
- Added multi-currency and selected-deal regression tests.

## 0.2.0 — 2026-09-30

- Calibrated to real CCR backtesting compare structure.
- Added `DealId` derivation from `AggregationLevel` after `TRD:`.
- Stopped exact CVAR/GCVAR AggregationLevel filtering because backtesting is deal-grained.
- Defaulted to impacted Legal Entity filtering, strict 10k materiality and 90% Pareto deal coverage.
- Added per-metric concentration and within-deal cancellation diagnostics.

## 0.1.0

- Initial backtesting drilldown skill.
