---
name: analyze-large-result-diff
description: Reduce a very large CVAR, GCVAR, risk, or regression comparison CSV into compact evidence by scanning only required gap/key columns first, selecting material impacts by threshold and Pareto coverage, enriching only selected rows, and returning patterns instead of raw data to the LLM.
---

# Analyze Large Result Diff

Use this skill whenever an agent receives a huge comparison CSV and must find only the material changes without placing the raw file in model context.

## Core rule

**Never ask the LLM to read the raw CSV.** Run this deterministic analyzer and reason over `summary.json` / `agent_context.md`.

## Real CCR compare-file defaults

The CVAR and GCVAR profiles understand both compact and real exported headers, including:

- `Mtf00 Gap` / `Mtf00Gap` / `mtf00Gap` → canonical evidence metric `Mtf00Gap`;
- `EepeInEur Gap` / `EepeInEurGap` → canonical evidence metric `EepeInEurGap`;
- `LegalEntity`;
- `AggregationLevel`;
- Ref/Test pairs such as `EffectiveMaturity (Ref)` and `EffectiveMaturity (Test)`;
- compare-result flags such as `Currency (Result)` and `CashFlowType (Result)`.

Default CCR materiality is **strict `abs(gap) > 10,000`**. A value exactly equal to 10,000 is not a material gap.

After thresholding, the default selector keeps the smallest set of the largest rows required to explain **90% of absolute material movement per metric**. Override that to 80%, for example, with `--coverage 0.8`.

CVAR and GCVAR use the same generic implementation; only profiles/configuration differ.

### Currency-aware MTF00 coverage

`Mtf00 Gap` is in the row currency (`Currency (Test)` / `Currency (Ref)`). A 10k EUR gap and a 10k USD gap are both material, but their raw amounts are **not additive**. When multiple currencies occur, the analyzer computes 80/90% Pareto coverage independently per currency and unions the selected rows. It deliberately suppresses fake cross-currency HHI/top-share/net-gross statistics.

`EepeInEur Gap` is already EUR-denominated, so its coverage is computed globally.

## Run

```powershell
skillhub run analyze-large-result-diff -- `
  --profile cvar `
  --input <cvar-comparison.csv> `
  --output <analysis-dir>
```

GCVAR:

```powershell
skillhub run analyze-large-result-diff -- `
  --profile gcvar `
  --input <gcvar-comparison.csv> `
  --output <analysis-dir>
```

Optional policy overrides:

```powershell
--coverage 0.8 `
--threshold "Mtf00 Gap=25000" `
--threshold "EepeInEur Gap=25000"
```

For maximum throughput install Polars (`pip install -e ".[fastcsv]"`). A bounded-memory Python streaming fallback remains available on locked-down machines.

## Algorithm

1. Inspect only the CSV header.
2. Resolve canonical metrics to actual file headers/aliases.
3. First pass: project identifiers/dimensions plus the two gap columns only.
4. Apply strict materiality (`|gap| > threshold`).
5. Track total absolute material movement per metric.
6. Keep bounded top candidates and retain only the largest rows required for the configured impact-coverage target.
7. Second pass: enrich only those selected rows with the other compare columns.
8. Detect patterns by both row frequency **and absolute impact contribution**.
9. Compute concentration diagnostics: top-1/top-3/top-10 shares, HHI/effective contributor count, net-vs-gross cancellation, and contributor counts required for 50/80/90/95% of material movement.
10. Summarize secondary compare diagnostics (RWA gap/ratio, EEPE gap/ratio, MTF/EEPE ratios) only on selected rows.
11. Compare Ref/Test field pairs on the selected rows to expose clues such as maturity/model/input changes.
12. Summarize `(Result)` comparison-flag failures and relationships between MTF00 and EEPE gaps.
13. Emit small structured evidence plus an LLM-ready Markdown brief.

## Outputs

- `summary.json` — canonical SkillHub evidence contract;
- `material_impacts.csv` — selected material metric impacts only;
- `patterns.json` — business concentration, Ref/Test changes, result-flag failures and metric relationships;
- `agent_context.md` — deliberately small context for an LLM;
- `run_manifest.json` — source metadata, policy and timings.

## Interpretation rules

- Positive and negative impacts are both important; absolute size controls selection.
- MTF00 and EEPE are never summed together as if they shared units.
- A Legal Entity can be important through contribution even if it appears in only a few rows.
- Ref/Test changes are clues, not proof of root cause.
- Threshold and 80/90% coverage are configuration, so release policy can evolve without changing code.
