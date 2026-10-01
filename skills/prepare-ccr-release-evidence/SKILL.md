---
name: prepare-ccr-release-evidence
description: Orchestrate the deterministic CCR release-validation data plane from CVAR/GCVAR result XLSX workbooks, deal-level backtesting workbooks and ErrorByTrade workbooks; investigate CVAR MTF00 then EEPE, reuse CVAR evidence for mirrored GCVAR issues, and optionally prefetch reusable PR-forensics candidates while keeping raw workbooks out of LLM context.
---

# Prepare CCR Release Evidence

This is the **one-command deterministic preparation skill** for the CCR Release Validation workflow.

It is not the final decision-making agent. It prepares a small evidence workspace that the CVAR agent, GCVAR agent and synthesis/root-cause agent can consume safely and quickly.

## Inputs

Give local filesystem paths, not pasted workbook content:

- `CcrMetrics.xlsx` — CVAR result comparison;
- CVAR backtesting result workbook;
- CVAR `ErrorByTrade.xlsx`;
- CVAR backtesting `ErrorByTrade.xlsx`;
- `CcrMetrics_Gcvar.xlsx` — GCVAR result comparison;
- GCVAR backtesting result workbook;
- GCVAR `ErrorByTrade.xlsx`;
- GCVAR backtesting `ErrorByTrade.xlsx`;
- production ref, e.g. `release/26.9`;
- candidate ref, e.g. `release/26.10`;
- optional `OWNER/REPO` when reusable PR forensics should be prefetched.

At least one CVAR/GCVAR result workbook is required. For a full release validation, provide all matching result/backtesting/error workbooks available to the job.

All CCR compare workbooks use:

- `Details` = present in Ref and Test;
- `Non Ref` = present only in Test/candidate;
- `Non Test` = present only in Ref/production.

## Investigation sequence encoded by the workflow

### CVAR

1. Reduce result workbook and identify material **MTF00** contributors.
2. Drill impacted Legal Entities into backtesting to identify the explanatory deals and deal-family pattern.
3. Correlate result/backtesting impacts with one-sided or changed `ErrorByTrade` evidence.
4. Analyze **EEPE** second.
5. Quantify whether EEPE shares the MTF00 row/deal signature.
6. Preserve the caveat that other unobserved MTFs may still drive EEPE.

### GCVAR

7. Reduce GCVAR result workbook cheaply.
8. Compare its compact signature with CVAR first.
9. If the same issue is strongly mirrored, reuse the CVAR root-cause path and skip redundant GCVAR backtesting/error scans by default.
10. If different/uncertain, perform the full GCVAR MTF00 → deals/errors → EEPE investigation.

### Code attribution

11. Build data/error/deal-family hypotheses before searching code.
12. Optionally call the generic `release-pr-forensics` skill between production and candidate refs.
13. Use selective diffs and a discriminating test before calling a PR causal.

## Full run

```powershell
skillhub run prepare-ccr-release-evidence -- `
  --cvar "C:\jobs\CcrMetrics.xlsx" `
  --cvar-backtesting "C:\jobs\CvarBacktesting.xlsx" `
  --cvar-errors "C:\jobs\CvarErrorByTrade.xlsx" `
  --cvar-backtesting-errors "C:\jobs\CvarBacktestingErrorByTrade.xlsx" `
  --gcvar "C:\jobs\CcrMetrics_Gcvar.xlsx" `
  --gcvar-backtesting "C:\jobs\GcvarBacktesting.xlsx" `
  --gcvar-errors "C:\jobs\GcvarErrorByTrade.xlsx" `
  --gcvar-backtesting-errors "C:\jobs\GcvarBacktestingErrorByTrade.xlsx" `
  --prod-ref release/26.9 `
  --candidate-ref release/26.10 `
  --coverage 0.90 `
  --output "C:\work\ccr-release-26.10"
```

Add generic GitHub release forensics:

```powershell
--repo OWNER/REPO --with-prs --pr-top 12 --inspect-top 3
```

Force or suppress independent GCVAR deep analysis when needed:

```powershell
--gcvar-deep always
# or
--gcvar-deep never
```

Default is `--gcvar-deep auto`.

## Workspace outputs

The exact branches present depend on supplied inputs and the GCVAR reuse gate. Typical outputs include:

```text
<WORK>/
  cvar/summary.json
  cvar/agent_context.md
  cvar-backtesting/backtesting_summary.json
  cvar-errors/error_summary.json
  cvar-backtesting-errors/error_summary.json
  gcvar/summary.json
  gcvar-backtesting/...            # only when deep analysis is needed
  gcvar-errors/...                 # only when deep analysis is needed
  pr-forensics/...                 # only with --with-prs
  pr_forensics_hints.json
  root_cause_routing.json
  workflow_manifest.json
  workflow_context.md              # preferred first LLM input
```

## Agent contract

The GitHub Copilot workflow should read `workflow_context.md` first, then open compact JSON only when necessary.

It should report material root-cause clusters using:

- **Observed** — deterministic facts from results/backtesting/errors;
- **Pattern** — concentration/correlation across LE, deals, deal families, sheets or errors;
- **Hypothesis** — proposed mechanism;
- **Candidate PR** — code change matching the mechanism;
- **Confirmed cause** — mechanism plus discriminating test/reproduction or equivalent strong evidence;
- **Unresolved** — missing evidence.

Final issue classification is:

- `expected_dev_change` — intended code behavior plausibly and consistently explains the impact;
- `suspected_bug` — evidence indicates unintended/incorrect behavior;
- `inconclusive` — insufficient evidence.

A highly ranked PR is never automatically a culprit.
