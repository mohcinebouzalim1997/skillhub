# CCR release-validation synthetic demo

This tiny dataset demonstrates the intended reduction flow without exposing company data.

```powershell
skillhub run analyze-large-result-diff -- --profile cvar --input examples/ccr-release-validation/cvar_compare.csv --output demo-cvar --threshold EepeInEurGap=1000000 --threshold mtf00Gap=0.5

skillhub run backtesting-drilldown -- --input examples/ccr-release-validation/backtesting_compare.csv --evidence demo-cvar/summary.json --output demo-backtesting
```

The `LE_BETA` backtesting row is deliberately very large but should be filtered out because the upstream material CVAR evidence points to `LE_ALPHA / CSA`.
