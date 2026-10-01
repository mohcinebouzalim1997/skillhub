# Engineering review — 1 Oct 2026

## Scope

Review of the CCR Release Validation implementation after switching from assumed CSV inputs to the real three-sheet XLSX compare workbooks and adding ErrorByTrade evidence.

## What is now structurally correct

### XLSX is the first-class input

The core tools accept `.xlsx` directly. Workbooks are streamed with `openpyxl` in read-only mode and normalized into a local cached table before heavy scans.

### Three-sheet compare semantics are explicit

`Details`, `Non Ref`, and `Non Test` are merged into one normalized logical table. Side-only rows receive signed synthetic gaps when needed, so additions/removals are not silently excluded from materiality.

### MTF00 is currency-aware

MTF00 concentration is not fabricated across EUR/USD native amounts. Coverage is computed by currency group and selected rows are unioned.

### Backtesting is filtered before deal analysis

The backtesting drilldown consumes impacted Legal Entities from upstream evidence and only then aggregates by `TRD:` deal identifier.

### ErrorByTrade is separate reusable infrastructure

The reusable `analyze-ccr-errors` skill correlates impacted Legal Entities/masters/deals with introduced, removed or changed errors. One scan now preserves **separate MTF00 and EEPE linkage**, so the workflow does not need to reread the large error workbook merely to distinguish the metric explanations. Error logic is not embedded into the agents.

### CVAR is the primary branch

The workflow investigates CVAR MTF00 first, then CVAR EEPE. GCVAR performs a cheap signature comparison with CVAR before deciding whether an expensive deep drilldown is necessary.

### PR forensics remains generic

GitHub retrieval/diff logic remains reusable outside CCR.

### One-agent UX does not collapse the architecture

The new `ccr-release-validator` coordinator is the recommended GitHub Copilot entry point today. It runs deterministic preparation from local workbook paths and then follows the workflow contract. CVAR, GCVAR and synthesis agents remain separate specialist definitions so the architecture is ready for explicit multi-agent delegation later.

## Performance review

The pipeline is bounded-memory on the Python fallback and can use Polars for normalized-table scans.

The largest unavoidable cost is first-time XLSX parsing. A synthetic sandbox benchmark with 52,000 data rows across the three sheets measured approximately:

```text
first run including XLSX normalization: ~7.6 s
repeat run using normalized cache:       ~1.0 s
```

This is not a production SLA. Real workstation numbers must be collected on the actual files.

The design intentionally prefers memory-safe XLSX streaming over loading a whole worksheet through a Rust/Excel reader into Python memory. If real workbooks make openpyxl normalization too slow, the `workbook.py` boundary is the correct place to replace the reader with a faster streaming implementation without changing agents or evidence contracts.

## Correctness review

Automated coverage now includes:

- CSV backward compatibility;
- three-sheet XLSX result workbooks;
- `Non Ref` Test-only gap derivation;
- `Non Test` Ref-only signed gap derivation;
- backtesting `TRD:` deal extraction;
- Equity DPS / Equity / FIC classification;
- multi-currency MTF00 coverage;
- ErrorByTrade side asymmetry and per-metric MTF00/EEPE linkage;
- full XLSX CVAR -> backtesting -> errors workflow;
- GCVAR same-signature reuse gate;
- release naming `release/26.9` -> `release/26.10` in existing PR tests.

## Important epistemic safeguards

The implementation intentionally does not equate:

```text
large PR relevance score = culprit
error on impacted deal = cause
MTF00 overlap with EEPE = proof that MTF00 caused EEPE
GCVAR/CVAR signature similarity = mathematical proof of one root cause
```

Agents are instructed to preserve these distinctions.

## Remaining validation before production trust

The key missing evidence is not more architecture. It is a blind replay on real company data.

Use one historical release with a known eventual root cause and compare the workflow's frozen result against the known answer.

Also capture real timings for:

```text
CcrMetrics.xlsx normalization
CVAR backtesting normalization + scan
ErrorByTrade scan
CcrMetrics_Gcvar.xlsx precheck
full end-to-end wall time
```

If XLSX normalization dominates total runtime, optimize the workbook reader next. If normalized-table scanning dominates, Polars/query-plan tuning is the next target.

## Recommendation

The repository is now suitable for a controlled company-machine pilot. Do not call it production-proven until the blind historical replay and real-size performance run are completed.
