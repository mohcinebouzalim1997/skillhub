# Engineering review — CCR release validation data plane

Date: 30 September 2026

This review covers the implementation after calibration against the supplied CVAR/GCVAR and backtesting screenshots.

## Result

The deterministic data plane is suitable for **company-machine pilot use**. It is deliberately separated from LLM reasoning: raw CSVs are local tool inputs, compact JSON/Markdown evidence is the agent input.

The workflow should not yet be labelled fully production-approved until the Polars fast path is benchmarked on representative real files and one historical known regression is replayed blind.

## Correctness controls reviewed

- strict materiality is `abs(gap) > 10,000`; exactly 10,000 is not material;
- positive and negative movement are both retained;
- selection uses absolute material movement, not net movement;
- cancellation/net-vs-gross is reported so opposite signs cannot hide a large gross change;
- `EepeInEur Gap` is treated as globally EUR-denominated;
- `Mtf00 Gap` is native-currency and coverage/concentration is separated by currency;
- selected contributors report 50/80/90/95% coverage counts;
- backtesting does not exact-join master-level CVAR/GCVAR aggregation IDs to deal-level aggregation strings;
- backtesting extracts `DealId` from `/TRD:<DEAL_ID>` and filters first by impacted Legal Entity;
- percentage-formatted ratio values are parsed defensively;
- missing configured metrics produce warnings/errors rather than fabricated values;
- candidate caps and selection caps produce warnings when requested coverage cannot be reached.

## Performance controls reviewed

### First pass

The Polars path uses lazy CSV scans, projected columns and streaming collection. The Python fallback is bounded-memory and keeps only top candidate heaps.

### Second pass

Full diagnostic columns are read only for rows already selected as material. Backtesting diagnostics are read only for selected deals.

### Context size

Raw CSV content is never embedded in `agent_context.md` or `workflow_context.md`.

### Current benchmark in the sandbox

The streaming fallback processed a synthetic 500,000-row / ~40 MiB file in about 3.1 seconds (~13 MiB/s) on this environment. This is not a production SLA and the preferred Polars path must be benchmarked on the company workstation.

## Investigation quality controls

The reducer supplies the agent with:

- largest material impacts;
- Legal Entity and selected AggregationLevel evidence;
- aggregation path shapes such as `LegalEntity>Master`;
- per-currency MTF concentration;
- EEPE concentration;
- top-1/top-3/top-10 shares;
- HHI / effective contributor count;
- contributor counts for 50/80/90/95%;
- cancellation / signed-vs-gross movement;
- Ref/Test change patterns;
- Result flag failures;
- MTF/EEPE/RWA gap and ratio diagnostics;
- deal-level backtesting contributors;
- PR-forensics retrieval hints.

The synthesis agent is instructed to label PRs as candidates until a discriminating rerun or reproduction establishes causality.

## Security / operational review

- no shell interpolation is required for CSV tools;
- PR forensics reuses authenticated `gh` read access;
- the static GitHub Pages marketplace cannot read workstation files;
- local install/update actions use the loopback SkillHub bridge;
- SkillHub remains outside product repositories;
- tools write only to explicit output workspaces.

## Known limitations / next verification

1. Polars is not installed in the current sandbox, so the Polars-specific automated test remains skipped here. CI/company-machine testing should execute it.
2. Exact CSV header text and sanitized rows would make stronger golden fixtures than screenshots.
3. Very large real files may require tuning candidate caps, Polars CSV options or optional Parquet/IPC caching after measurement.
4. Automated `PASS/WARNING/FAIL` is intentionally not implemented until the team defines release governance rules.
5. `.xlsx` is intentionally not the primary high-performance input; use the comparison CSV produced by the job.

## Recommended pilot

Run a known historical release regression without telling the agent the known culprit. Freeze the generated evidence, hypotheses and candidate PR list, then compare with the actual root cause. This is the most informative acceptance test for the full workflow.
