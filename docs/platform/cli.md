# CLI reference

Common commands:

```powershell
skillhub doctor
skillhub list
skillhub workflows
skillhub agents
skillhub stacks
skillhub status
skillhub marketplace --open
skillhub validate
```

Install the CCR Release Validation terrain:

```powershell
skillhub install-stack ccr-release-validation --check-deps
```

Run CVAR workbook reduction:

```powershell
skillhub run analyze-large-result-diff -- --profile cvar --input CcrMetrics.xlsx --output evidence --coverage 0.90
```

Run backtesting workbook drilldown:

```powershell
skillhub run backtesting-drilldown -- --input Backtesting.xlsx --evidence evidence/summary.json --output bt --coverage 0.90
```

Run ErrorByTrade correlation:

```powershell
skillhub run analyze-ccr-errors -- --input ErrorByTrade.xlsx --evidence evidence/summary.json --output errors
```

Run PR forensics for a named release:

```powershell
skillhub run release-pr-forensics -- --repo OWNER/REPO --release release/26.10 --query "EEPE jump" --output release-analysis
```

For our naming convention, a previous sibling may be `release/26.9`.

Inspect dependencies, including recommended acceleration packages:

```powershell
skillhub deps analyze-large-result-diff
```
