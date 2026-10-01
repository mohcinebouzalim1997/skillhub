# CCR Release Validation — current design

This is the current executable design for validating a candidate CCR release against production.

The system is optimized around one rule:

> **Excel workbooks are deterministic-tool inputs. Compact evidence is LLM input.**

GitHub Copilot should never be asked to read the full `CcrMetrics*.xlsx`, backtesting workbook, or `ErrorByTrade.xlsx` when SkillHub has already reduced them.

## Release convention

Use the real release naming convention:

```text
release/26.9
release/26.10
```

Do not rewrite `26.9` as `26.09`.

## Files in the workflow

CVAR result comparison:

```text
CcrMetrics.xlsx
```

GCVAR result comparison:

```text
CcrMetrics_Gcvar.xlsx
```

CVAR and GCVAR backtesting result comparisons use the same result schema at a deal-grained aggregation level.

Each result comparison workbook has exactly three semantic sheets:

```text
Details   = aggregation exists in both Ref and Test
Non Ref   = aggregation exists only in Test/candidate
Non Test  = aggregation exists only in Ref/production
```

Each result/backtesting area can also have an `ErrorByTrade.xlsx` with the same three-sheet compare convention.

## Structural rows are not ignored

A row on `Non Ref` or `Non Test` may be the most important release change.

SkillHub normalizes all three sheets into one internal cached table and derives signed gaps when a side-only row does not already contain an explicit gap:

```text
Non Ref  => Test-only contribution => +Test value
Non Test => Ref-only contribution  => -Ref value
```

The internal table adds:

```text
WorkbookSheet
PresenceState       matched | test_only | ref_only
IsStructuralChange TRUE | FALSE
```

These fields are available to the pattern detector and the agents.

## Materiality

The confirmed business rule is strict:

```text
abs(gap) > 10,000
```

Exactly 10,000 is not material.

Primary metrics:

```text
Mtf00 Gap
EepeInEur Gap
```

MTF00 materiality is interpreted in the row currency. EUR and USD MTF amounts are never summed together to construct a fake common-unit concentration statistic.

EEPE-in-EUR is already EUR-normalized, so it is analyzed globally.

After thresholding, SkillHub keeps the largest material contributors required to explain 90% of absolute material movement by default. The target is configurable, for example `--coverage 0.8`.

## Investigation order

The workflow is intentionally sequential rather than “analyze everything at once”.

```text
CVAR
  |
  +-- MTF00 impact
  |     |
  |     +-- Legal Entity / aggregation patterns
  |     +-- backtesting deal attribution
  |     +-- deal-family pattern
  |     +-- ErrorByTrade asymmetry
  |
  +-- EEPE impact
        |
        +-- Legal Entity / aggregation patterns
        +-- backtesting deal attribution
        +-- ErrorByTrade asymmetry
        +-- MTF00-overlap assessment

GCVAR
  |
  +-- cheap result-level signature check versus CVAR
  |
  +-- if mirrored: reuse CVAR root-cause path
  |
  +-- if different/uncertain: full GCVAR MTF00 then EEPE investigation

Synthesis
  |
  +-- data hypotheses
  +-- error explanation
  +-- release-pr-forensics
  +-- selective PR diffs
  +-- discriminating experiment
  +-- expected_dev_change / suspected_bug / inconclusive
```

## Why MTF00 is investigated before EEPE

MTF00 can directly influence EEPE, so the workflow first establishes whether the EEPE movement occurs on the same selected rows/deals as the MTF00 movement.

SkillHub reports a routing classification:

```text
strong_mtf00_overlap
partial_mtf00_overlap
weak_or_no_mtf00_overlap
```

This is not a causal verdict.

A weak MTF00 overlap does **not** prove that EEPE is unrelated to MTF, because other MTFs are not visible in this compare workbook and may still drive EEPE. Non-MTF model/data changes are also possible.

## Backtesting deal attribution

Backtesting has the same compare columns, but `AggregationLevel` is deal-grained and normally includes:

```text
/TRD:<DEAL_ID>
```

The drilldown first filters the huge backtesting workbook by impacted `LegalEntity`, then derives `DealId` from the `TRD:` segment and aggregates material movement by deal.

Deal-family convention supplied by the CCR team:

```text
no explicit prefix  => Equity DPS
ELI-                 => Equity
other prefix         => FIC
```

Examples:

```text
123456   => Equity DPS
ELI-123  => Equity
IRD-123  => FIC
TQE-123  => FIC
```

The report includes deal concentration and how many deals are required to explain 50%, 80%, 90% and 95% of absolute movement.

## ErrorByTrade analysis

The error-forensics skill is reusable for result-level and backtesting errors.

Typical visible columns include:

```text
GroupingCriterionId
NettingSetId
ErrorType
AnalysisIndex
TradeId
Message (Ref)
Message (Test)
Message (Result)
```

SkillHub limits the error investigation to already-impacted Legal Entities/deals and classifies errors as:

```text
introduced_in_test
removed_in_test
changed_between_ref_and_test
same_or_unresolved
```

It also clusters useful categories such as:

```text
dead_trade
unpriced_netting_set
mtm_failed
missing_schedule
missing_rate_index
missing_market_data
strike_conversion
```

An asymmetric error on an impacted LE/deal is a strong explanation candidate, not proof of causality.

## GCVAR optimization

GCVAR is not automatically given the same expensive treatment as CVAR.

After the GCVAR result workbook is reduced, SkillHub compares its signature with CVAR using:

- impacted Legal Entity overlap,
- impacted aggregation overlap,
- metric direction/signature.

When similarity is high, the default `--gcvar-deep auto` mode skips GCVAR backtesting/error scans and records that the CVAR root-cause path is being reused. Use `--gcvar-deep always` for independent confirmation.

## PR forensics

`release-pr-forensics` remains a reusable skill/tool, not a dedicated CCR agent.

The CCR synthesis agent invokes it only after data/error patterns exist.

It can retrieve PRs for:

- a named release,
- two refs/commits/tags,
- a date window.

For release validation the normal range is:

```text
release/26.9 -> release/26.10
```

Retrieval policy:

```text
all candidate PR metadata
    -> titles, bodies, labels, files, churn
    -> deterministic relevance ranking
    -> selective per-file patches for top candidates
    -> full diff only when needed
```

A high-ranked PR is a **Candidate PR**, not a confirmed culprit.

## Final classification

Each material root-cause cluster should end as one of:

```text
expected_dev_change
suspected_bug
inconclusive
```

`expected_dev_change` requires a coherent link between documented/intended code behavior and the observed data effect, without important contradictions.

If the evidence is insufficient, use `inconclusive` rather than inventing certainty.

## Performance architecture

`.xlsx` is a ZIP/XML format, so random scanning is expensive.

SkillHub therefore performs an explicit normalization layer:

```text
XLSX
  -> openpyxl read-only streaming
  -> one cached normalized CSV per workbook
  -> Polars lazy/streaming fast path when installed
  -> bounded-memory Python streaming fallback otherwise
```

The normalized cache is local inside the tool output workspace and is never sent to the LLM.

The first Excel parse is the expensive step. Repeated work against the same output/cache avoids reparsing unchanged workbooks.

Install the fast CCR environment with:

```powershell
pip install -e ".[ccr]"
```

This keeps `openpyxl` as the workbook reader and enables Polars for the large normalized-table scans.

## Evidence contract

Deterministic tools emit JSON/Markdown artifacts rather than prose-only answers.

The stable contract allows the underlying engine to change later without changing the agents.

The workflow produces, among others:

```text
workflow_context.md
workflow_manifest.json
root_cause_routing.json
pr_forensics_hints.json

cvar/summary.json
cvar/agent_context.md
cvar-backtesting/backtesting_summary.json
cvar-errors/error_summary.json
cvar-backtesting-errors/error_summary.json

GCVAR equivalents when deep investigation runs
```

`workflow_context.md` is the preferred first file for GitHub Copilot.
