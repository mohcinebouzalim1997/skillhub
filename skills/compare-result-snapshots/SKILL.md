---
name: compare-result-snapshots
description: >
  Compare two CSV result snapshots deterministically, identify changed aggregate metrics, missing or
  new keys, and the largest row-level movers. Use for regression outputs, risk metrics, benchmarks,
  prices, latency, PnL or any before/after tabular result before asking the model to explain causes.
argument-hint: "[before.csv] [after.csv] [keys] [metrics]"
---

# Goal

Turn two result snapshots into a compact **fact layer** describing what actually changed.

Use Python for arithmetic and ranking. Use the language model afterward for interpretation.

# Workflow

## 1. Compare

If rows have stable identifiers, pass them as keys:

```bash
python scripts/compare_results.py \
  --before before.csv \
  --after after.csv \
  --keys counterparty,date \
  --metrics EEPE,EPE,PFE95 \
  --top 20 \
  --output metric-analysis
```

If `--metrics` is omitted, the script auto-detects common numeric columns. If `--keys` is omitted, it still compares numeric column aggregates but cannot attribute changes to individual rows.

## 2. Read compact artifacts

Read:

- `metric-analysis/comparison-summary.md` first;
- `metric-analysis/comparison.json` for structured facts;
- only inspect raw CSV rows if the summary requires clarification.

# Interpretation rules

- Preserve units; do not compare percentages and notionals as if they were homogeneous.
- A large relative change from a near-zero base can be misleading; inspect the absolute delta too.
- Missing/new keys can explain aggregate changes even when surviving rows are stable.
- Do not infer a code root cause from this skill alone.

# Output

State:

1. largest aggregate metric changes;
2. first/most material affected keys when keys are available;
3. rows added/removed;
4. whether the movement is broad or concentrated;
5. which facts should be passed to `/release-pr-forensics` or another investigation skill.
