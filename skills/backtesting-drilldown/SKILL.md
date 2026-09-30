---
name: backtesting-drilldown
description: Use compact upstream CVAR or GCVAR evidence to filter a much larger CCR backtesting comparison CSV early, derive DealId from the TRD segment of AggregationLevel when necessary, rank material deal contributors by Pareto coverage, and return only compact evidence.
---

# Backtesting Drilldown

Use this skill **after** `analyze-large-result-diff` has narrowed a CVAR/GCVAR regression to impacted business dimensions.

## Real CCR backtesting structure

The compare file has essentially the same Ref/Test/Gap schema as CVAR/GCVAR, but `AggregationLevel` is deal-grained. When there is no dedicated deal column, the tool derives:

```text
/LegalEntity:.../TRD:<DEAL_ID>
                       ^^^^^^^
```

into canonical `DealId`.

Because CVAR/GCVAR aggregation levels and backtesting `TRD:` aggregation levels are **not the same grain**, the default early filter uses impacted `LegalEntity` values rather than exact upstream `AggregationLevel` strings.

## Core rule

Do not globally materialize or send the huge backtesting CSV to the LLM. Filter early using upstream evidence, aggregate by deal, then keep only material deal contributors.

Default materiality is strict `abs(gap) > 10,000`, with 90% absolute-impact coverage per metric. MTF00 and EEPE contributions are ranked independently. For native-currency MTF00, coverage/concentration is also separated by currency; EUR and USD deal gaps are never added into a fake common total.

## Run

```powershell
skillhub run backtesting-drilldown -- `
  --input <backtesting-comparison.csv> `
  --evidence <cvar-analysis/summary.json> `
  --output <backtesting-analysis>
```

The same command works with GCVAR evidence.

After deal ranking, the tool performs a **selected-deal diagnostic pass** over only the retained deals and only useful Ref/Test/Result/Gap/Ratio columns. This surfaces maturity/RWA/currency/cash-flow clues without materializing the whole backtesting file.

Optional policy override:

```powershell
--coverage 0.8
```

If a future schema exposes an explicit deal field:

```powershell
--deal-column TradeInternalId
```

## Outputs

- `backtesting_summary.json`;
- `deal_impacts.csv`;
- `backtesting_patterns.json`;
- `agent_context.md`;
- `run_manifest.json`.

## Reasoning contract

The agent should use this output to answer:

- Which Legal Entities from CVAR/GCVAR remain impacted at deal level?
- Which deals explain 80/90% of the material movement?
- Is the effect concentrated in one/few deals or distributed (including how many deals explain 50/80/90/95%)?
- Are positive and negative effects offsetting inside a deal?
- Which deal IDs should be carried into root-cause / PR investigation?
