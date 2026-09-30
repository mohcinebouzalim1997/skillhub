# CCR / XVA signal map

Use this as a hypothesis generator, not as a diagnosis table.

| Observed signature | Layers worth checking |
|---|---|
| First divergence on a specific future date | calendars, fixings, exercise/break dates, first-passage/state transitions, cashflow schedule |
| Only one MTF window | window construction, boundary logic, state reset, indexing |
| Small subset of paths | path state, stochastic factor domain, interpolation/extrapolation, numerical edge case |
| NaN/Inf appears suddenly | invalid domain, division by small number, log/exp overflow, compounding convention, missing market data |
| Broad EEPE movement | exposure aggregation, discounting/numeraire, collateral, scenario generation, trade population |
| Counterparty-specific | netting set, CSA/collateral, trade population, legal entity mapping |
| All metrics stable except one | metric-specific aggregation/normalization/reporting before blaming upstream pricing |

Always test whether the signature is explained by a lower-level upstream change before focusing on the metric's final aggregation code.
