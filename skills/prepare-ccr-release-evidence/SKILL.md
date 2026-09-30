---
name: prepare-ccr-release-evidence
description: >
  Orchestrate the deterministic data-reduction part of CCR release validation: reduce CVAR and GCVAR compare CSVs, drill only impacted Legal Entities into huge backtesting CSVs, build one compact LLM handoff, and optionally prefetch reusable release-PR forensic candidates.
---

# Prepare CCR Release Evidence

Use this skill when the user wants to validate one CCR candidate release against production and has the CVAR/GCVAR compare-job CSV files.

## Why it exists

The specialized CVAR/GCVAR agents should never receive raw multi-GB CSV contents. This tool runs the deterministic skills first and creates a tiny workflow handoff.

## Input model

Give **local file paths**, not pasted CSV content:

- CVAR compare CSV;
- CVAR backtesting compare CSV (recommended);
- GCVAR compare CSV;
- GCVAR backtesting compare CSV (recommended);
- production ref, e.g. `release/26.9`;
- candidate ref, e.g. `release/26.10`;
- repository `OWNER/REPO` only if PR forensics should be prefetched.

At least one of CVAR/GCVAR must be supplied.

## Run

```powershell
skillhub run prepare-ccr-release-evidence -- `
  --cvar "<CVAR.csv>" `
  --cvar-backtesting "<CVAR_BACKTESTING.csv>" `
  --gcvar "<GCVAR.csv>" `
  --gcvar-backtesting "<GCVAR_BACKTESTING.csv>" `
  --prod-ref release/26.9 `
  --candidate-ref release/26.10 `
  --coverage 0.90 `
  --output "<WORK>"
```

Optionally add:

```powershell
--repo OWNER/REPO --with-prs
```

This uses `release-pr-forensics` only as a reusable downstream capability. It remains independent of CCR.

## Outputs

- `cvar/summary.json` and optional `cvar-backtesting/backtesting_summary.json`;
- `gcvar/summary.json` and optional `gcvar-backtesting/backtesting_summary.json`;
- `workflow_manifest.json`;
- `pr_forensics_hints.json`;
- `workflow_context.md` — the preferred LLM input;
- optional `pr-forensics/` candidate PR artifacts.

## Agent contract

The CCR Release Validation agents should read `workflow_context.md` first and then open structured JSON only when more detail is required. Never place the raw source CSVs into LLM context.
