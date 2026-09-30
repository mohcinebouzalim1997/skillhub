# Changelog

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
