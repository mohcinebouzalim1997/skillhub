# Quant SkillHub v0.1 — CCR Release Validation Foundation

This revision changes SkillHub from a generic release-forensics demo into the foundation for a **multi-agent CCR Release Validation workflow**.

## Architectural correction

- `release-pr-forensics` remains an atomic reusable skill/tool.
- The former `release-forensics` personal agent and stack were removed.
- `ccr-release-validation` is now the higher-level workflow.
- Prepared specialized agents: CVAR validator, GCVAR validator and synthesis agent.

## CCR data plane

Added:

- `analyze-large-result-diff` skill;
- `backtesting-drilldown` skill;
- CVAR / GCVAR / backtesting profiles;
- stable evidence contract;
- timing/profiling infrastructure;
- Polars fast path with bounded-memory streaming fallback;
- benchmark harness;
- compact LLM context generation.

## Release naming

The project now consistently documents releases as:

`release/26.9`, not `release/26.09`.

Numeric sibling inference correctly treats `release/26.9` as preceding `release/26.10`.

## Documentation

`docs/project/PROJECT-GUIDE.md` is now the canonical explanation of the project and the checklist for completing the real company CCR validator.

## Real CVAR / GCVAR / backtesting calibration

The supplied compare-output screenshots and business rules are now reflected in the profiles and tests:

- CVAR and GCVAR share the same compare schema family.
- Material release gaps are `Mtf00 Gap` and `EepeInEur Gap`.
- Strict materiality is `abs(gap) > 10,000`.
- Default Pareto coverage is 90% of absolute material movement and is configurable (e.g. 80%).
- MTF00 is native-currency; EUR/USD coverage and concentration are computed separately rather than summed.
- EEPE-in-EUR remains globally additive in EUR.
- Backtesting `AggregationLevel` deal IDs are extracted from `/TRD:<DEAL_ID>`.
- Backtesting first filters to impacted Legal Entities and only then performs deal reduction.

Additional diagnostics now include:

- contributor counts required for 50/80/90/95% of material movement;
- top-1/top-3/top-10 concentration;
- HHI / effective contributor count;
- positive-vs-negative cancellation;
- threshold capture of total absolute movement;
- Ref/Test changes such as EffectiveMaturity and RiskWeightedExposureFactor;
- comparison Result flags;
- MTF/EEPE/RWA gap and ratio diagnostics;
- second-pass diagnostics only for selected backtesting deals.

## One-command preparation

`prepare-ccr-release-evidence` now prepares the complete deterministic evidence workspace from CVAR/GCVAR and matching backtesting file paths. It produces `workflow_context.md`, branch evidence JSON and PR-forensics hints; raw CSV contents are never embedded into LLM context.

Optional `--with-prs --repo OWNER/REPO` composes the generic `release-pr-forensics` skill between the supplied production and candidate refs.

See `docs/project/CCR-RELEASE-VALIDATION-RUNBOOK.md` for the exact operator flow.
