---
name: analyze-ccr-errors
description: Correlate selected CVAR/GCVAR or backtesting impacts with three-sheet ErrorByTrade XLSX asymmetries, quantify links separately for MTF00 and EEPE scopes, classify error/deal patterns, and return compact evidence without exposing the raw workbook to the LLM.
---

# Analyze CCR Errors

Use this skill after material result or deal-level evidence exists.

It inspects the matching `ErrorByTrade.xlsx` and limits attention to impacted Legal Entities, masters/netting sets and deals from the upstream compact evidence.

The workbook has the same semantic sheets:

- `Details` — error records present in Ref and Test; differing messages / failed `Message (Result)` are treated as changed errors;
- `Non Ref` — error present only in Test/candidate (`introduced_in_test`);
- `Non Test` — error present only in Ref/production (`removed_in_test`).

The analyzer extracts Legal Entity / master / trade identifiers from `NettingSetId` and explicit trade fields, classifies deals as Equity DPS / Equity / FIC, groups common error mechanisms, and reports **metric-specific linkage for `Mtf00Gap` and `EepeInEurGap`** where the upstream evidence exposes those scopes.

This is evidence of a possible explanation, not automatic causality: an error may be correlated with an impacted netting set without being the economic cause of the metric change.

Never paste the raw error workbook into Copilot.

```powershell
skillhub run analyze-ccr-errors -- `
  --input "C:\jobs\ErrorByTrade.xlsx" `
  --evidence "C:\work\release\cvar\summary.json" `
  --output "C:\work\release\cvar-errors"
```

For backtesting, pass `backtesting_summary.json` instead; this enables deal-level error linkage.

## Outputs

- `error_summary.json` — global and per-metric error linkage;
- `relevant_errors.csv` — capped, relevant error details only;
- `agent_context.md` — compact LLM context;
- `run_manifest.json` — input/timing metadata.
