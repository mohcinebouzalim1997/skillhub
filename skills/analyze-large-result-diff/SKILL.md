---
name: analyze-large-result-diff
description: Reduce a very large three-sheet CCR result workbook (CVAR/GCVAR) or compatible CSV into compact evidence by normalizing Details, Non Ref and Non Test, selecting material MTF00/EEPE impacts by strict threshold and Pareto coverage, enriching only selected impacts, and keeping raw rows out of LLM context.
---

# Analyze Large Result Diff

Use this skill whenever an agent must understand a large CVAR/GCVAR comparison without asking the LLM to read `CcrMetrics.xlsx` / `CcrMetrics_Gcvar.xlsx` directly.

## Core rule

**The workbook is a deterministic-tool input, never normal LLM context.** The tool emits `summary.json` and `agent_context.md`; agents reason over those compact artifacts.

## CCR workbook contract

The production compare workbooks are Excel files with three semantic sheets:

- `Details` — aggregation levels present in both Ref/production and Test/candidate;
- `Non Ref` — present only in Test/candidate;
- `Non Test` — present only in Ref/production.

The tool streams all three sheets into one cached normalized table. It adds:

- `WorkbookSheet`;
- `PresenceState = matched | test_only | ref_only`;
- `IsStructuralChange`.

For side-only rows, when an explicit gap is absent, the tool derives a signed structural gap:

- Test-only / `Non Ref` => `+Test` value;
- Ref-only / `Non Test` => `-Ref` value.

This means additions/removals participate in materiality and Pareto coverage rather than disappearing from analysis.

CSV remains supported for backward compatibility and testing, but XLSX is the primary CCR input.

## Real CCR defaults

The CVAR and GCVAR profiles resolve real compare headers such as:

- `LegalEntity`;
- `AggregationLevel`;
- `Mtf00 (Ref)` / `Mtf00 (Test)` / `Mtf00 Gap`;
- `EepeInEur (Ref)` / `EepeInEur (Test)` / `EepeInEur Gap`;
- `Eepe`, `Rwa`, ratios, `EffectiveMaturity`, `RiskWeightedExposureFactor`;
- `(Result)` flags such as currency/cash-flow comparisons.

Primary materiality is deliberately narrow:

- strict `abs(Mtf00 Gap) > 10,000` in the row currency;
- strict `abs(EepeInEur Gap) > 10,000 EUR`.

Exactly `10,000` is **not** material.

After thresholding, the default selector keeps the smallest set of the largest contributors required to explain **90% of absolute material movement**. Use `--coverage 0.8` for 80%.

### Currency-aware MTF00

`Mtf00 Gap` is native-currency. EUR and USD values must never be added into a fake common total. Pareto coverage and concentration are computed independently per observed currency and the selected rows are unioned.

`EepeInEur Gap` is EUR-normalized and can be analyzed globally.

## Run

CVAR:

```powershell
skillhub run analyze-large-result-diff -- `
  --profile cvar `
  --input "C:\jobs\CcrMetrics.xlsx" `
  --coverage 0.90 `
  --output "C:\work\release\cvar"
```

GCVAR:

```powershell
skillhub run analyze-large-result-diff -- `
  --profile gcvar `
  --input "C:\jobs\CcrMetrics_Gcvar.xlsx" `
  --coverage 0.90 `
  --output "C:\work\release\gcvar"
```

Optional policy overrides:

```powershell
--coverage 0.8 `
--threshold "Mtf00 Gap=25000" `
--threshold "EepeInEur Gap=25000"
```

For the high-throughput normalized-table scan install the CCR extra (`pip install -e ".[ccr]"`), which enables Polars. Excel ingestion itself uses `openpyxl` in read-only mode and is cached, so repeated investigations avoid re-reading the workbook.

## Algorithm

1. Validate the three-sheet workbook contract.
2. Stream `Details`, `Non Ref`, and `Non Test` once into a cached normalized table.
3. Preserve structural side-only rows and derive missing signed gaps.
4. Resolve canonical metrics and real header aliases.
5. First analytical pass: project only identifiers/dimensions plus material gap columns.
6. Apply strict `|gap| > threshold`.
7. Measure total/gross/net/positive/negative material movement.
8. Select the largest contributors required for the configured Pareto coverage.
9. Compute top-1/top-3/top-10 shares, HHI/effective contributor count, cancellation, and contributor counts for 50/80/90/95% coverage.
10. Second analytical pass: enrich only selected rows with Ref/Test/Result/ratio/RWA/maturity diagnostics.
11. Detect Legal Entity, aggregation-shape, structural-sheet and Ref/Test-change patterns by frequency and impact contribution.
12. Emit compact structured evidence plus an LLM-ready Markdown brief.

The tool computes MTF00 and EEPE evidence in the same efficient scan, but the **agent reasoning order is MTF00 first, then EEPE**.

## Outputs

- `summary.json` — canonical SkillHub evidence contract;
- `material_impacts.csv` — only selected material contributors;
- `patterns.json` — concentration, structural rows, Ref/Test changes and result-flag clues;
- `agent_context.md` — deliberately compact LLM context;
- `run_manifest.json` — source/workbook/cache metadata and timings.

## Interpretation rules

- Positive and negative impacts both matter; absolute size controls contributor selection.
- MTF00 and EEPE are never summed together.
- MTF00 amounts from different native currencies are never summed together.
- `Non Ref` / `Non Test` are first-class structural changes, not noise.
- A Legal Entity can be important through contribution even if it occurs in few rows.
- Ref/Test changes are clues, not proof of root cause.
- EEPE overlap with MTF00 is a routing clue only: other MTFs are not visible in this result workbook.
