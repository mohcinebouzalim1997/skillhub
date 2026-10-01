# CCR Release Validation — operator runbook

This is the practical procedure to run the current workflow today on a company workstation.

## 1. One-time installation

From the SkillHub repository:

```powershell
.\scripts\bootstrap.ps1
```

For large production files, install the fast CCR extra:

```powershell
pip install -e ".[ccr]"
```

Check the environment:

```powershell
skillhub doctor
skillhub validate
```

Install the complete personal Copilot stack:

```powershell
skillhub install-stack ccr-release-validation --check-deps
```

If PR forensics is required:

```powershell
gh auth status
```

## 2. Inputs for a full release validation

Give **paths**, not file contents.

CVAR branch:

```text
CcrMetrics.xlsx
CVAR backtesting result workbook
CVAR ErrorByTrade.xlsx
CVAR backtesting ErrorByTrade.xlsx
```

GCVAR branch:

```text
CcrMetrics_Gcvar.xlsx
GCVAR backtesting result workbook
GCVAR ErrorByTrade.xlsx
GCVAR backtesting ErrorByTrade.xlsx
```

Release metadata:

```text
production: release/26.9
candidate:  release/26.10
repository: OWNER/REPO   # only needed for PR forensics
```

Each result/error workbook must expose the compare sheets:

```text
Details
Non Ref
Non Test
```

## 3. Preferred full command

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

If you want data analysis first and PRs later, remove:

```text
--repo OWNER/REPO
--with-prs
```

If GCVAR must be independently drilled even when it mirrors CVAR:

```text
--gcvar-deep always
```

Default is:

```text
--gcvar-deep auto
```

## 4. What the command does

### CVAR

```text
CcrMetrics.xlsx
   -> normalize Details + Non Ref + Non Test
   -> MTF00 material impact
   -> Legal Entity / aggregation patterns
   -> backtesting deals
   -> deal families
   -> result/backtesting errors
   -> EEPE material impact
   -> MTF00↔EEPE routing relationship
```

### GCVAR

```text
CcrMetrics_Gcvar.xlsx
   -> cheap result signature
   -> compare with CVAR
       -> same issue: reuse CVAR root-cause path
       -> different/uncertain: full GCVAR backtesting + errors
```

### Root cause

```text
compact data/error evidence
   -> PR metadata in release range
   -> selective diff inspection
   -> mechanism hypothesis
   -> discriminating experiment
   -> expected_dev_change / suspected_bug / inconclusive
```

## 5. What GitHub Copilot should read

Start with only:

```text
C:\work\ccr-release-26.10\workflow_context.md
```

Then let Copilot open structured artifacts only when it needs more evidence.

Do not attach the raw XLSX files to the Copilot conversation.

Suggested prompt after deterministic preparation:

```text
Use the ccr-release-validator agent.

Production is release/26.9 and candidate is release/26.10.
The deterministic SkillHub workspace is:
C:\work\ccr-release-26.10

Read workflow_context.md first and validate the release.
Do MTF00 before EEPE, use the ErrorByTrade metric linkage, reuse CVAR root-cause evidence for mirrored GCVAR issues, and inspect PR diffs only after the data mechanism is established.
Classify each material root-cause cluster as expected_dev_change, suspected_bug or inconclusive, with supporting/contradicting evidence and the smallest next discriminating test.
Never read the raw XLSX files into model context and never call a PR causal only because it ranks highly.
```

You can also skip the manual preparation command and start directly with the coordinator agent. Give it the eight workbook paths plus production/candidate refs and repository; it is instructed to run `prepare-ccr-release-evidence` through the terminal first and then reason over the generated workspace. This is the recommended one-agent UX today when Copilot terminal execution is enabled.

## 6. Run each deterministic tool manually

### CVAR result workbook

```powershell
skillhub run analyze-large-result-diff -- `
  --profile cvar `
  --input "C:\jobs\CcrMetrics.xlsx" `
  --coverage 0.90 `
  --output "C:\work\test\cvar"
```

Read:

```text
cvar\agent_context.md
cvar\summary.json
```

### CVAR backtesting workbook

```powershell
skillhub run backtesting-drilldown -- `
  --input "C:\jobs\CvarBacktesting.xlsx" `
  --evidence "C:\work\test\cvar\summary.json" `
  --coverage 0.90 `
  --output "C:\work\test\cvar-backtesting"
```

Read:

```text
cvar-backtesting\agent_context.md
cvar-backtesting\backtesting_summary.json
```

### CVAR result errors

```powershell
skillhub run analyze-ccr-errors -- `
  --input "C:\jobs\CvarErrorByTrade.xlsx" `
  --evidence "C:\work\test\cvar\summary.json" `
  --output "C:\work\test\cvar-errors"
```

### CVAR backtesting errors

```powershell
skillhub run analyze-ccr-errors -- `
  --input "C:\jobs\CvarBacktestingErrorByTrade.xlsx" `
  --evidence "C:\work\test\cvar-backtesting\backtesting_summary.json" `
  --output "C:\work\test\cvar-backtesting-errors"
```

Use the same tools with `--profile gcvar` for GCVAR result analysis.

## 7. Full test procedure on a known historical release

Choose one historical release where the eventual cause is already known to the team.

Do **not** tell Copilot the known culprit at first.

Run the full command and record:

```text
CVAR workbook size / rows
CVAR backtesting size / rows
GCVAR workbook size / rows
GCVAR backtesting size / rows
Error workbook sizes
wall-clock runtime
```

Then ask Copilot for the final report and freeze its candidate PR/root-cause answer.

Only afterward reveal the known historical cause and compare:

```text
Was the material impact found?
Were the correct LE/deals found?
Was the relevant error asymmetry found?
Did the actual PR appear in the shortlist?
Did the proposed mechanism match reality?
Was the final expected/bug/inconclusive classification sensible?
```

This blind replay is the best acceptance test for the workflow.

## 8. Troubleshooting

If Excel processing is slow:

```powershell
pip install -e ".[ccr]"
skillhub doctor
```

Confirm Polars is installed. The first XLSX normalization is still an Excel parse; subsequent scans use the cached normalized table.

If a workbook does not contain all three sheets, the tool fails explicitly instead of silently dropping structural differences.

If GitHub access fails:

```powershell
gh auth status
```

The data workflow can still run without PR forensics.
