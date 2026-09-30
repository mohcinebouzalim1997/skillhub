---
name: investigate-metric-jump
description: >
  Orchestrate an evidence-based investigation of an unexpected quantitative metric jump by combining
  deterministic before/after result analysis with release PR forensics. Use for EEPE, EPE, CVA, PFE,
  PnL, price, latency or other regression metrics when you have a good/bad result and a good/bad code ref.
argument-hint: "[metric] [before.csv] [after.csv] [repo] [good-ref] [bad-ref]"
---

# Goal

Connect **what changed in results** with **what changed in code** while keeping correlation, relevance and causality separate.

This is an orchestration skill. It depends on two reusable skills:

- `/compare-result-snapshots`
- `/release-pr-forensics`

# Investigation sequence

## Phase A — Establish the data signature

Use `/compare-result-snapshots` first.

Extract facts such as:

- metric magnitude and direction;
- first affected date if represented in keys;
- affected counterparties/trades/books/paths/windows;
- concentration vs broad movement;
- rows added/removed;
- metrics that did **not** move.

The “not affected” dimensions are often as valuable as the affected ones.

## Phase B — Establish the code-change universe

Use `/release-pr-forensics` with the exact known-good and known-bad refs.

Build the compact index before reading any full diff.

## Phase C — Rank using the data signature

Translate the observed data signature into search terms and path hints.

Examples:

- “first passage, window 1, MTF, date boundary”;
- “numeraire, exposure aggregation, EEPE”;
- “calendar, fixing, overnight, compounding, NaN”.

Rank release candidates, then inspect only the strongest mechanistic candidates.

## Phase D — Correlate evidence

Optionally create a compact investigation brief:

```bash
python scripts/build_investigation_brief.py \
  --comparison metric-analysis/comparison.json \
  --candidates release-analysis/candidates.json \
  --metric EEPE \
  --output investigation-brief.md
```

## Phase E — Design the smallest discriminating experiment

Prefer experiments that change exactly one condition:

- replay one affected path;
- compare old/new formula or boundary predicate;
- toggle one config/default;
- revert/cherry-pick one PR in an isolated branch;
- add a unit test at the first divergence;
- run git bisect when the interval remains large.

# Quant reasoning guardrails

- A PR touching “EEPE” by name is not automatically more causal than a low-level change in exposure, discounting, dates, collateral or scenario generation.
- A jump beginning on one simulation date often points to a date/state boundary, but this is a hypothesis until demonstrated.
- A one-path or one-window signature argues against broad market/calibration explanations only when the data confirms other paths/windows are stable.
- Preserve the distinction between model, market data, numerical method, implementation, configuration and aggregation layers.

# Output format

Return:

1. **Observed signature** — only facts from data.
2. **Change universe** — release size and candidate set.
3. **Candidate mechanisms** — PR/change → plausible mechanism → matching observations.
4. **Contradicting evidence** — facts each hypothesis fails to explain.
5. **Next experiment** — cheapest/highest-information test.
6. **Confidence language** — candidate / supported / strongly supported / demonstrated; never “culprit” without causal evidence.
