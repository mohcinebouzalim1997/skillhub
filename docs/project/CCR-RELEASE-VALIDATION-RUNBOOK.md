# CCR Release Validation — operator runbook

This page is the shortest path from **four huge compare CSVs** to a small evidence package that GitHub Copilot can reason over.

## What you give the system

For a full release validation, provide **file paths**, not the CSV contents:

```text
CVAR compare CSV
CVAR backtesting compare CSV
GCVAR compare CSV
GCVAR backtesting compare CSV
production ref     e.g. release/26.9
candidate ref      e.g. release/26.10
repository         optional, for PR forensics
```

The LLM must never read the raw huge files. Python tools read them locally and emit compact evidence.

## Preferred: one command

```powershell
skillhub run prepare-ccr-release-evidence -- `
  --cvar "C:\jobs\cvar-compare.csv" `
  --cvar-backtesting "C:\jobs\cvar-backtesting.csv" `
  --gcvar "C:\jobs\gcvar-compare.csv" `
  --gcvar-backtesting "C:\jobs\gcvar-backtesting.csv" `
  --prod-ref release/26.9 `
  --candidate-ref release/26.10 `
  --coverage 0.90 `
  --output "C:\work\ccr-26.10"
```

For an 80% investigation instead:

```text
--coverage 0.80
```

The strict materiality rule remains `abs(gap) > 10,000`.

### Include GitHub PR candidates

When `gh auth status` is healthy and you know the repository:

```powershell
skillhub run prepare-ccr-release-evidence -- `
  --cvar "C:\jobs\cvar-compare.csv" `
  --cvar-backtesting "C:\jobs\cvar-backtesting.csv" `
  --gcvar "C:\jobs\gcvar-compare.csv" `
  --gcvar-backtesting "C:\jobs\gcvar-backtesting.csv" `
  --prod-ref release/26.9 `
  --candidate-ref release/26.10 `
  --repo OWNER/REPO `
  --with-prs `
  --coverage 0.90 `
  --output "C:\work\ccr-26.10"
```

PR ranking is a **candidate list**, not proof of causality. The agent should inspect selective patches and propose a discriminating test before calling a PR a confirmed cause.

## What the data tools do

### CVAR / GCVAR compare reducer

Input:

```text
one CVAR or GCVAR comparison CSV
```

Command when used directly:

```powershell
skillhub run analyze-large-result-diff -- `
  --profile cvar `
  --input "C:\jobs\cvar-compare.csv" `
  --coverage 0.90 `
  --output "C:\work\ccr-26.10\cvar"
```

Use `--profile gcvar` for GCVAR.

Primary materiality metrics:

```text
Mtf00 Gap       strict |gap| > 10,000 in the row currency
EepeInEur Gap   strict |gap| > 10,000 EUR
```

`Mtf00 Gap` is multi-currency. EUR and USD native amounts are **not summed together** for Pareto concentration. The tool performs coverage separately per currency and unions the selected rows.

After thresholding, the reducer retains the largest contributors required to explain the requested absolute material movement. It also reports how many contributors are needed for 50%, 80%, 90% and 95%.

The reducer then performs a second pass only for selected rows and looks for explanation clues in:

- Legal Entity and aggregation concentration;
- positive vs negative movement and cancellation;
- Effective Maturity Ref/Test changes;
- Risk Weighted Exposure Factor Ref/Test changes;
- EEPE error/ratio changes;
- MTF/EEPE/RWA gap and ratio columns;
- CashFlowType and Currency result flags;
- MTF00 ↔ EEPE co-movement.

Main outputs:

```text
summary.json          structured agent evidence
agent_context.md      compact first LLM input
material_impacts.csv  selected impacts only
patterns.json         deterministic patterns
run_manifest.json     audit/timing metadata
```

### Backtesting drilldown

Input:

```text
backtesting compare CSV
upstream CVAR/GCVAR summary.json
```

Example:

```powershell
skillhub run backtesting-drilldown -- `
  --input "C:\jobs\cvar-backtesting.csv" `
  --evidence "C:\work\ccr-26.10\cvar\summary.json" `
  --coverage 0.90 `
  --output "C:\work\ccr-26.10\cvar-backtesting"
```

The backtesting file is filtered first by impacted Legal Entity. `AggregationLevel` is deal-grained, so SkillHub extracts the deal identifier after `TRD:` instead of exact-matching the master-level CVAR/GCVAR aggregation string.

The tool then ranks deal contributions and performs a second narrow diagnostic pass only on selected deals.

Main outputs:

```text
backtesting_summary.json
agent_context.md
deal_impacts.csv
backtesting_patterns.json
```

## What you give GitHub Copilot after the tools run

Prefer this tiny file first:

```text
C:\work\ccr-26.10\workflow_context.md
```

Do **not** attach the raw CSVs to the chat.

A practical request is:

```text
Use the CCR release-validation workflow.
Production is release/26.9 and candidate is release/26.10.
The deterministic workspace is C:\work\ccr-26.10.

Read workflow_context.md first and open branch summary JSON only when more detail is needed.
Explain:
1. the material CVAR and GCVAR impacts,
2. concentration / cancellation / Legal Entity / deal patterns,
3. the most plausible data mechanisms,
4. candidate PRs relevant to those mechanisms,
5. the smallest experiment needed to confirm or reject each candidate cause.

Do not read the raw huge CSVs into model context and do not call a PR causal from ranking alone.
```

If your Copilot environment supports installed custom agents, install the complete stack:

```powershell
skillhub install-stack ccr-release-validation --check-deps
```

Then use the `ccr-release-validation-synthesizer` agent. CVAR and GCVAR validator agents are available when you want branch-specific analysis.

## Static UI vs local marketplace

GitHub Pages is the read-only marketplace. It cannot see local files or installed skills.

For local install/update controls:

```powershell
skillhub marketplace --open
```

## Current evidence contract

The deterministic tools own numerical truth. Agents consume compact structured evidence rather than implementing CSV logic themselves.

This separation means the processing engine can later move from Polars to DuckDB/C++/distributed compute without changing the agents.

## What still needs company-machine validation

Before calling the workflow fully production-approved, run it against:

1. one real large CVAR + matching backtesting pair;
2. one real large GCVAR + matching backtesting pair;
3. one historical release with a known eventual culprit;
4. representative multi-GB sizes to benchmark the Polars fast path;
5. the final human release verdict policy (PASS/WARNING/FAIL, if desired).

The screenshots established the column family and deal convention; a copied header line and sanitized rows remain useful as a golden regression fixture.
