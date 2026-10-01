# Quant SkillHub

**Quant SkillHub is an internal Play Store for reusable AI capabilities used by Quant and engineering teams.** It centralizes skills, executable tools, agents, workflows, packs and stacks without adding SkillHub files to production repositories.

The flagship workflow is **CCR Release Validation**.

It now understands the real workbook model:

```text
CcrMetrics.xlsx
CcrMetrics_Gcvar.xlsx
Backtesting result workbooks
ErrorByTrade.xlsx
```

with the three compare sheets:

```text
Details
Non Ref
Non Test
```

The system reduces these large workbooks deterministically and gives GitHub Copilot only compact evidence.

> `release-pr-forensics` remains a reusable skill/tool, not a dedicated CCR agent.

## Read first

- [Project Guide](docs/project/PROJECT-GUIDE.md)
- [CCR Release Validation design](docs/project/CCR-RELEASE-VALIDATION.md)
- [CCR operator runbook](docs/project/CCR-RELEASE-VALIDATION-RUNBOOK.md)

## Setup

```powershell
.\scripts\bootstrap.ps1
skillhub doctor
skillhub validate
```

For the recommended large-file path:

```powershell
pip install -e ".[ccr]"
```

This keeps the XLSX streaming layer and enables Polars for fast scans of the normalized tables.

## Marketplace

Static/MkDocs mode:

```powershell
skillhub serve-site
```

Local Play-Store control mode:

```powershell
skillhub marketplace --open
```

## Install CCR Release Validation

```powershell
skillhub install-stack ccr-release-validation --check-deps
```

Reusable skills include:

```text
prepare-ccr-release-evidence
analyze-large-result-diff
backtesting-drilldown
analyze-ccr-errors
release-pr-forensics
```

Agents:

```text
ccr-release-validator                 # recommended entry point today
ccr-cvar-release-validator            # specialized CVAR reasoning
ccr-gcvar-release-validator           # specialized GCVAR reasoning
ccr-release-validation-synthesizer    # root-cause / code synthesis
```

The coordinator can start from local workbook paths, run the deterministic preparation command through Copilot's terminal, and then reason only over the compact workspace. The specialized agents remain independently usable and are future delegation targets when the enterprise agent platform supports multi-agent orchestration.

## Full workflow today

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
  --repo OWNER/REPO `
  --with-prs `
  --output "C:\work\ccr-release-26.10"
```

The first file Copilot should read is:

```text
workflow_context.md
```

not the raw Excel files.

## Investigation logic

```text
CVAR MTF00
  -> backtesting deals
  -> deal-family pattern
  -> errors
  -> CVAR EEPE
  -> MTF00/EEPE overlap

GCVAR
  -> first compare result signature with CVAR
  -> skip redundant deep work when clearly mirrored
  -> otherwise full MTF00/EEPE/backtesting/error analysis

Synthesis
  -> data hypotheses
  -> PR forensics
  -> selective diffs
  -> discriminating test
  -> expected_dev_change / suspected_bug / inconclusive
```

Deal family convention:

```text
no explicit prefix -> Equity DPS
ELI-               -> Equity
other prefix       -> FIC
```

Materiality:

```text
abs(Mtf00 Gap) > 10,000 in row currency
abs(EepeInEur Gap) > 10,000 EUR
```

Default Pareto coverage is 90% of absolute material movement.

## Release naming

Correct:

```text
release/26.9
release/26.10
```

Not:

```text
release/26.09
```

## Validation

```powershell
python -m pytest -q
skillhub validate
skillhub generate-site
```

The repository contains synthetic XLSX regression tests for three-sheet result workbooks, backtesting deal extraction, ErrorByTrade asymmetry, CVAR→GCVAR reuse and the full preparation workflow. The remaining critical validation is a blind replay on one real historical release with a known eventual root cause and real workstation performance measurements.
