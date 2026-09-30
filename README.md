# Quant SkillHub

**Quant SkillHub is an internal Play Store for reusable AI capabilities used by Quant and engineering teams.** It centralizes skills, executable tools, agents, workflows, packs, stacks and knowledge without adding SkillHub files to production repositories.

The flagship prepared workflow is now **CCR Release Validation**: specialized CVAR and GCVAR validator agents reduce huge comparison CSVs into compact deterministic evidence, drill only impacted dimensions into backtesting data, and reuse the generic `release-pr-forensics` skill when a release impact requires code-change investigation.

> `release-pr-forensics` is a reusable skill/tool — not a dedicated agent.

## Start here

The detailed architecture, terminology, CCR flow and production-completion checklist live in:

**[`docs/project/PROJECT-GUIDE.md`](docs/project/PROJECT-GUIDE.md)**

For the exact operational commands, use **[`docs/project/CCR-RELEASE-VALIDATION-RUNBOOK.md`](docs/project/CCR-RELEASE-VALIDATION-RUNBOOK.md)**.

## Setup

```powershell
.\scripts\bootstrap.ps1
skillhub doctor
skillhub validate
```

For the fastest huge-CSV analysis path:

```powershell
pip install -e ".[fastcsv]"
```

## Open the marketplace

Static documentation / GitHub Pages:

```powershell
skillhub serve-site
```

Local Play-Store control mode with Installed / Update status:

```powershell
skillhub marketplace --open
```

## Install the CCR release-validation terrain

```powershell
skillhub install-stack ccr-release-validation --check-deps
```

This installs these reusable skills:

- `prepare-ccr-release-evidence`
- `analyze-large-result-diff`
- `backtesting-drilldown`
- `release-pr-forensics`

and these specialized agents:

- `ccr-cvar-release-validator`
- `ccr-gcvar-release-validator`
- `ccr-release-validation-synthesizer`

The declarative multi-agent workflow is `workflows/ccr-release-validation.yaml`.


## Fastest way to prepare one CCR release today

Give the tools **file paths**, not pasted raw CSV content:

```powershell
skillhub run prepare-ccr-release-evidence -- `
  --cvar "C:\jobs\cvar-compare.csv" `
  --cvar-backtesting "C:\jobs\cvar-backtesting.csv" `
  --gcvar "C:\jobs\gcvar-compare.csv" `
  --gcvar-backtesting "C:\jobs\gcvar-backtesting.csv" `
  --prod-ref release/26.9 `
  --candidate-ref release/26.10 `
  --coverage 0.90 `
  --output "C:\work\ccr-26.10"
```

Then give Copilot the generated `workflow_context.md` (or simply tell the installed CCR agents to use that workspace). Add `--repo OWNER/REPO --with-prs` when `gh auth status` is healthy and you want candidate PRs prefetched.

`Mtf00 Gap` is treated as native-currency: materiality is 10k in the row currency, and Pareto coverage is calculated independently by currency rather than adding EUR and USD amounts. `EepeInEur Gap` remains globally EUR-denominated.

## Release naming convention

Single-digit release components are **not zero padded**:

```text
release/26.8
release/26.9
release/26.10
```

The PR-forensics skill can therefore infer `release/26.9` as the previous sibling of `release/26.10` when both refs exist.

## Huge CSV rule

The LLM never reads the raw CVAR/GCVAR/backtesting CSV.

```text
huge CSV → deterministic reduction → compact evidence → agent reasoning
```

CVAR example:

```powershell
skillhub run analyze-large-result-diff -- `
  --profile cvar `
  --input cvar-compare.csv `
  --coverage 0.90 `
  --output cvar-evidence
```

Then backtesting:

```powershell
skillhub run backtesting-drilldown -- `
  --input backtesting-compare.csv `
  --evidence cvar-evidence/summary.json `
  --output cvar-backtesting
```

## PR forensics

Named release:

```powershell
skillhub run release-pr-forensics -- `
  --repo OWNER/REPO `
  --release release/26.10 `
  --query "EEPE jump in MTF" `
  --output release-analysis
```

Two refs/commits and date-window modes are also supported. Full diffs are fetched selectively rather than dumping the entire release into model context.

## Validation

```powershell
python -m pytest -q
skillhub validate
skillhub generate-site
```

## Current status

The platform infrastructure, screenshot-calibrated CVAR/GCVAR schema, targeted TRD backtesting drilldown and one-command evidence preparation path are implemented. The data plane is usable today. **Production sign-off still needs a sanitized real CSV sample, one historical known regression and your final release verdict policy** so we can golden-test exact parsing, throughput and decision rules.

Read the [Project Guide](docs/project/PROJECT-GUIDE.md) for exactly what to provide next.
