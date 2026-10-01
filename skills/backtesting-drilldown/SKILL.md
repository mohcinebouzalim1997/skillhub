---
name: backtesting-drilldown
description: Use compact CVAR/GCVAR evidence to filter a much larger three-sheet CCR backtesting workbook by impacted Legal Entity, derive TRD deal IDs, rank the deals explaining material MTF00/EEPE movement, classify deal families, and return only compact deal-level evidence.
---

# Backtesting Drilldown

Use this skill **after** `analyze-large-result-diff` has identified material CVAR/GCVAR impacts.

## Workbook contract

Backtesting result workbooks use the same three-sheet comparison semantics:

- `Details` — present in both Ref and Test;
- `Non Ref` — Test/candidate only;
- `Non Test` — Ref/production only.

The compare columns are broadly the same as CVAR/GCVAR, but `AggregationLevel` is more deal-grained and typically contains:

```text
/LegalEntity:<LE>/.../TRD:<DEAL_ID>/...
```

The tool derives canonical `DealId` from the `TRD:` segment when no explicit deal column exists.

## Performance rule

Do **not** analyze the whole backtesting workbook semantically. The upstream CVAR/GCVAR evidence already tells us which Legal Entities matter.

The tool therefore:

1. normalizes/caches the workbook once;
2. filters rows to impacted Legal Entities as early as possible;
3. aggregates material gaps by deal;
4. keeps only deals required to explain the configured coverage;
5. performs a second enrichment pass only for selected deals.

The raw workbook never enters LLM context.

## Deal families

The current CCR convention is encoded directly:

- no explicit alphabetic prefix => `equity_dps`;
- `ELI-...` => `equity`;
- any other explicit prefix (`IRD-`, `TQE-`, etc.) => `fic`.

The output reports both individual deals and family concentration, which helps distinguish one-off trade effects from systematic product-family effects.

## Materiality

- strict `abs(Mtf00 Gap) > 10,000` in native currency;
- strict `abs(EepeInEur Gap) > 10,000 EUR`;
- 90% absolute-impact coverage by default;
- MTF00 contribution/coverage remains separated by currency.

## Run

```powershell
skillhub run backtesting-drilldown -- `
  --input "C:\jobs\Backtesting.xlsx" `
  --evidence "C:\work\release\cvar\summary.json" `
  --coverage 0.90 `
  --output "C:\work\release\cvar-backtesting"
```

The same command works with GCVAR evidence.

If the schema exposes an explicit deal field:

```powershell
--deal-column TradeInternalId
```

## Outputs

- `backtesting_summary.json` — compact deal evidence;
- `deal_impacts.csv` — selected material deal contributors only;
- `backtesting_patterns.json` — concentration, family and selected-deal diagnostics;
- `agent_context.md` — compact LLM handoff;
- `run_manifest.json` — source/cache/timing metadata.

## Reasoning contract

Use the output to answer:

- Which impacted Legal Entities survive at deal level?
- Which deals explain 50/80/90/95% of movement?
- Is the movement concentrated or distributed?
- Are the same deals/families driving both MTF00 and EEPE?
- Are positive/negative contributions cancelling?
- Do selected deals share Ref/Test changes such as effective maturity, RWA factor, currency or cash-flow behavior?
- Which exact deals/netting sets should be checked against `ErrorByTrade.xlsx` and later code/PR changes?

Deal concentration is evidence about mechanism, not proof of code causality.
