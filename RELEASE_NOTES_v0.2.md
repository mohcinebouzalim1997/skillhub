# Quant SkillHub v0.2.0

## CCR Release Validation: real workbook edition

- `.xlsx` is now first-class for CVAR, GCVAR, backtesting and ErrorByTrade.
- `Details`, `Non Ref`, `Non Test` are normalized with explicit presence semantics.
- Side-only rows contribute signed synthetic MTF00/EEPE gaps when explicit gaps are absent.
- Added reusable `analyze-ccr-errors` skill.
- Added ErrorByTrade result/backtesting correlation.
- Added deal-family classification: Equity DPS / Equity / FIC.
- CVAR investigation is MTF00-first, EEPE-second.
- Added deterministic MTF00↔EEPE overlap routing.
- GCVAR now performs a CVAR similarity gate and can skip redundant deep scans.
- Final agent classification is expected_dev_change / suspected_bug / inconclusive.
- Updated full workflow, stack, pack, marketplace metadata, README, project guide and operator runbook.
- Added synthetic XLSX end-to-end tests.

## Release naming

The repository uses `release/26.9`, not `release/26.09`.

## Final pilot hardening

- Added the `ccr-release-validator` coordinator as the recommended GitHub Copilot entry point today.
- Added metric-specific ErrorByTrade linkage so one error-workbook scan reports separate MTF00 and EEPE overlap.
- Updated SkillHub skill documentation to treat the three-sheet XLSX contract as primary rather than flat CSV.
- Preserved CSV compatibility internally for normalized/cache and generic workflows.
- Stack installation now includes the coordinator plus the CVAR, GCVAR and synthesis specialists.
