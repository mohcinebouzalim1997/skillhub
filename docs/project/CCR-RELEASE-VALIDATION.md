# CCR Release Validation — Real Data Workflow

This document explains the **current executable CCR release-validation design** after calibration from the CVAR/GCVAR and backtesting compare-file screenshots supplied on 30 September 2026.

The core design rule is simple:

> **Huge CSVs are tool inputs. Small evidence artifacts are agent inputs.**

The LLM should never read millions of raw compare rows.

---

## 1. The job we want to solve

For a release candidate such as:

```text
production: release/26.9
candidate:  release/26.10
```

we want the system to answer:

1. What changed materially in CVAR?
2. What changed materially in GCVAR?
3. Which Legal Entities / aggregation rows explain most of the movement?
4. Which backtesting deals explain those impacts?
5. Are there patterns in Ref/Test fields around the impacted rows?
6. Are CVAR and GCVAR telling the same story or different stories?
7. Which PRs in the release are plausible candidates for the observed impact?
8. What evidence supports each candidate?
9. What smallest experiment would confirm or reject the candidate cause?

The desired final report is not just "red/green". It should contain **impact + patterns + explanation/hypotheses + candidate PRs + next tests**.

---

## 2. Architecture

```text
                       CCR RELEASE VALIDATION WORKFLOW

          ┌──────────────────────┴──────────────────────┐
          ▼                                             ▼
  CVAR Validator Agent                         GCVAR Validator Agent
          │                                             │
          │ analyze-large-result-diff                  │ same engine/profile=gcvar
          ▼                                             ▼
  compact CVAR evidence                        compact GCVAR evidence
          │                                             │
          │ backtesting-drilldown                      │ backtesting-drilldown
          ▼                                             ▼
  deal-level CVAR evidence                     deal-level GCVAR evidence
          └──────────────────────┬──────────────────────┘
                                 ▼
                    Release Validation Synthesizer
                                 │
                    data explanation / hypotheses
                                 │
                    if code evidence is required
                                 ▼
                     release-pr-forensics SKILL
                                 │
                     candidate PRs / selective diffs
                                 │
                                 ▼
                    discriminating experiments
                                 │
                                 ▼
                     final investigation report
```

`release-pr-forensics` is deliberately a **reusable skill/tool**, not an agent. Other future agents can reuse it.

---

## 3. Confirmed compare-file shape

CVAR and GCVAR currently share the same structure.

Important columns visible in the supplied compare outputs include:

```text
LegalEntity
AggregationLevel

EepeError (Ref)
EepeRatio (Ref)
EffectiveMaturity (Ref)
RiskWeightedExposureFactor (Ref)
...
EepeError (Test)
EepeRatio (Test)
EffectiveMaturity (Test)
RiskWeightedExposureFactor (Test)

Mtf00 (Ref)
CashFlowType (Ref)
Currency (Ref)
Eepe (Ref)
EepeInEur (Ref)
Rwa (Ref)

Mtf00 (Test)
CashFlowType (Test)
Currency (Test)
Eepe (Test)
EepeInEur (Test)
Rwa (Test)

Mtf00 Gap
Abs(Mtf00 Gap)
Mtf00 Ratio
CashFlowType (Result)
Currency (Result)
Eepe Gap
Abs(Eepe Gap)
Eepe Ratio
EepeInEur Gap
Abs(EepeInEur Gap)
EepeInEur Ratio
Rwa Gap
Abs(Rwa Gap)
Rwa Ratio
```

The analyzer is intentionally alias-aware, so compact forms such as `Mtf00Gap` and `EepeInEurGap` still work.

Evidence always uses stable canonical names:

```text
Mtf00Gap
EepeInEurGap
```

regardless of cosmetic CSV header spacing.

---

## 4. Materiality and Pareto coverage

Confirmed business rule:

```text
A gap is material when abs(gap) > 10,000.
```

The inequality is **strict**. Exactly `10,000` is not a material gap.

This applies to the two primary metrics:

- `Mtf00Gap` — threshold 10,000 in the compare-file/native currency;
- `EepeInEurGap` — threshold 10,000 EUR.

Thresholding alone can still leave hundreds or thousands of rows. The second rule is therefore a Pareto-style coverage target:

```text
keep the largest material rows until they explain 90%
of absolute material movement for that metric
```

The target is configurable:

```powershell
--coverage 0.8
```

for 80%, or:

```powershell
--coverage 0.9
```

for 90%.

Coverage is calculated **independently per metric**. MTF00 and EEPE are never added together as if they had common units.

The central policy is stored in:

```text
skillhub/profiles/ccr/materiality.yaml
```

so CVAR, GCVAR and backtesting cannot silently drift to different thresholds.

---

## 5. CVAR/GCVAR reduction

Command:

```powershell
skillhub run analyze-large-result-diff -- `
  --profile cvar `
  --input "C:\path\cvar-compare.csv" `
  --output "C:\work\validation\cvar"
```

GCVAR uses:

```powershell
--profile gcvar
```

### First scan

The tool reads only:

- identity columns such as `AggregationLevel`;
- business dimensions such as `LegalEntity`;
- the two material gap columns.

It calculates, per metric:

- valid/invalid value count;
- positive and negative count;
- signed total;
- absolute total;
- count above strict materiality;
- absolute material movement;
- percentage of all movement captured by the 10k threshold;
- minimum number of largest rows required to hit the configured coverage target.

Candidate retention is bounded, so memory does not grow with the whole CSV.

### Second scan

Only selected material rows are enriched with the other compare columns.

This enables pattern diagnostics without exposing the entire CSV to the LLM.

---

## 6. Smart pattern diagnostics

The analyzer now detects several classes of evidence.

### Business concentration

For dimensions such as `LegalEntity`, it measures both:

- row share;
- share of absolute selected movement.

This matters because a Legal Entity represented by only three rows can still explain 70% of the release impact.

### Ref/Test field changes

The tool automatically pairs fields such as:

```text
EffectiveMaturity (Ref)
EffectiveMaturity (Test)
```

and reports patterns like:

```text
EffectiveMaturity changed in 92% of selected material rows.
RiskWeightedExposureFactor changed in 88%.
Currency did not change.
CashFlowType did not change.
```

For numeric pairs it also reports mean/median/max absolute `Test - Ref` deltas.

These are **clues**, not root-cause conclusions.

### Compare-result flags

Columns ending in `(Result)` are summarized when they contain non-TRUE / mismatching values.

### MTF00 ↔ EEPE relationship

On the selected material rows the analyzer reports:

- rows containing both metrics;
- rows above both 10k thresholds;
- same-sign percentage;
- Pearson correlation when meaningful.

This can help distinguish a coupled exposure/maturity change from a metric-specific effect.

### Distributed sub-threshold tail

The evidence records:

```text
threshold_capture_pct_of_all_abs_movement
subthreshold_abs_sum
```

Therefore the agent can detect a release where no small row is individually material but thousands of sub-10k movements collectively explain a large absolute tail.

---

## 7. Backtesting semantics

The backtesting compare has essentially the same metric columns, but its `AggregationLevel` is more deal-grained.

The supplied data shows the convention:

```text
.../TRD:<DEAL_ID>
```

When there is no dedicated `DealId` field, SkillHub derives:

```text
DealId = substring captured after TRD:
```

using the configured regex.

### Important join rule

CVAR/GCVAR aggregation levels and backtesting aggregation levels are **not assumed equal**.

Therefore the default drilldown does **not** try to exact-match upstream `AggregationLevel` strings.

Instead it:

1. takes impacted `LegalEntity` values from CVAR/GCVAR evidence;
2. filters the huge backtesting file to those Legal Entities first;
3. extracts/uses DealId;
4. aggregates gap contributions by deal;
5. applies the same strict 10k materiality policy;
6. retains deals required to explain the configured 80/90% absolute movement.

This is both safer and much faster than globally analyzing the full backtesting file.

---

## 8. Backtesting command

After CVAR reduction:

```powershell
skillhub run backtesting-drilldown -- `
  --input "C:\path\cvar-backtesting-compare.csv" `
  --evidence "C:\work\validation\cvar\summary.json" `
  --output "C:\work\validation\cvar-backtesting"
```

The upstream `summary.json` tells the tool which Legal Entities matter.

The same command works for GCVAR using its evidence.

Backtesting outputs include:

```text
backtesting_summary.json
deal_impacts.csv
backtesting_patterns.json
agent_context.md
run_manifest.json
```

Useful deal metrics include:

- selected deal contribution;
- top-1/top-3/top-10 concentration;
- coverage achieved;
- count of material deals;
- sub-threshold tail;
- within-deal cancellation (`gross abs` vs net movement).

---

## 9. What the LLM actually sees

The agent reads something like:

```text
CVAR
----
Mtf00Gap: 43 material rows, 8 selected, 91.4% material coverage
EepeInEurGap: 21 material rows, 5 selected, 92.8% material coverage

LegalEntity X explains 68% of selected EEPE absolute movement.
EffectiveMaturity changed on 7/8 selected MTF rows.
Currency comparison flags are clean.

Backtesting
-----------
LegalEntity X -> 31 material deals
Top 3 deals explain 82% of material EEPE movement.
DEAL_ABC is the largest contributor.
```

It does **not** receive the raw 5 GB CSV.

---

## 10. Files passed at each stage

### CVAR Validator Agent

Human gives the agent paths to:

```text
CVAR compare CSV
CVAR backtesting compare CSV
```

The first tool receives the CVAR CSV.

The second tool receives:

```text
backtesting CSV
+
CVAR summary.json
```

The LLM receives only the generated compact evidence.

### GCVAR Validator Agent

Same pattern with the GCVAR files.

### Synthesis Agent

The synthesizer should receive only:

```text
cvar/summary.json
cvar-backtesting/backtesting_summary.json
gcvar/summary.json
gcvar-backtesting/backtesting_summary.json
production release
candidate release
repository name
```

It does not need the raw CSVs.

### PR Forensics

The reusable PR skill receives:

```text
repository
production/candidate release refs
query describing observed data pattern
optional path hints
```

For example:

```text
repo: OWNER/CCR
base: release/26.9
head: release/26.10
query: "MTF00 and EEPE impact concentrated on LegalEntity X; EffectiveMaturity changed on impacted rows"
```

It first retrieves metadata/files for all changes, then selectively retrieves patches/full diffs only for relevant candidates.

---

## 11. How to use it today with GitHub Copilot

Install the stack once:

```powershell
skillhub install-stack ccr-release-validation --check-deps
```

For large production files, install the fast CSV backend:

```powershell
pip install -e ".[fastcsv]"
```

### Option A — use a specialized Copilot agent

Select the installed `ccr-cvar-release-validator` agent and give it **file paths**:

```text
Validate CVAR for release/26.10 against release/26.9.

CVAR compare:
C:\validation\CVAR.csv

CVAR backtesting compare:
C:\validation\CVAR_Backtesting.csv

Work directory:
C:\validation\out\cvar

Use the default 10k threshold and 90% coverage.
Do not read the raw CSV into model context; execute the SkillHub tools and reason only from their generated compact evidence.
```

Repeat with `ccr-gcvar-release-validator`.

Then use `ccr-release-validation-synthesizer` and give it the **generated evidence paths**, not the CSV paths.

### Option B — deterministic commands first

This is the most reliable workflow on any workstation today, even if Copilot custom-agent orchestration is limited:

```powershell
skillhub run analyze-large-result-diff -- --profile cvar --input CVAR.csv --output out/cvar
skillhub run backtesting-drilldown -- --input CVAR_Backtesting.csv --evidence out/cvar/summary.json --output out/cvar-backtesting

skillhub run analyze-large-result-diff -- --profile gcvar --input GCVAR.csv --output out/gcvar
skillhub run backtesting-drilldown -- --input GCVAR_Backtesting.csv --evidence out/gcvar/summary.json --output out/gcvar-backtesting
```

Then give the four compact evidence artifacts to the synthesizer agent.

---

## 12. Root-cause / PR stage

After data reduction, the synthesizer should formulate data hypotheses before looking at code.

Example:

```text
Observed:
- EEPE and MTF00 both move on the same Legal Entity.
- EffectiveMaturity changes on 94% of material rows.
- Three deals explain 80% of backtesting movement.

Hypothesis:
- candidate release changed maturity/first-passage treatment for a specific deal family.
```

Only then call `release-pr-forensics`.

The PR skill supports:

- release → release;
- arbitrary ref/commit → ref/commit;
- date range.

It retrieves metadata/labels/files for the whole scope but full diffs only progressively for candidates.

The final agent report must use epistemic labels:

```text
Observed
Pattern
Hypothesis
Candidate PR
Confirmed cause
```

A PR is not called "culprit" until a discriminating experiment supports causality.

---

## 13. Performance model

Preferred engine:

```text
Polars lazy scan
  ↓
column projection
  ↓
strict threshold predicate
  ↓
bounded top candidates
  ↓
coverage selection
  ↓
selective row enrichment
```

Fallback:

```text
Python csv.reader
bounded metric heaps
```

The fallback is useful on locked-down machines but is not the preferred path for very large files.

The backtesting fallback necessarily aggregates matched deals in memory; for large production backtesting, **Polars is strongly recommended**.

Every tool writes stage timings so throughput can be measured on the company workstation.

---

## 14. What is still worth validating with a real CSV

The screenshots established the important structure and business policy. To remove the remaining uncertainty, the best next input is a **small sanitized text extract** from the real generated CSVs:

- exact header line;
- 20–100 representative rows;
- at least one >10k MTF00 gap;
- at least one >10k EEPE-in-EUR gap;
- at least one backtesting `TRD:` aggregation row.

This is mainly to verify exact spelling/encoding/delimiter and real data edge cases, not to redesign the architecture.

The highest-value validation after that is a known historical bad release where the real culprit PR is known. Run the workflow blind and check whether that PR appears in the evidence-backed shortlist.

---

# 11. Calibrated schema and analysis policy from the real compare screenshots

The 30 September 2026 screenshots confirm that CVAR and GCVAR use the same compare layout, and that backtesting keeps the same comparison metrics while changing the aggregation grain to `TRD:<deal>`.

The observed compare schema is approximately:

```text
LegalEntity
AggregationLevel

EepeError (Ref)                    EepeError (Test)
EepeRatio (Ref)                    EepeRatio (Test)
EffectiveMaturity (Ref)            EffectiveMaturity (Test)
RiskWeightedExposureFactor (Ref)   RiskWeightedExposureFactor (Test)
Mtf00 (Ref)                        Mtf00 (Test)
CashFlowType (Ref)                 CashFlowType (Test)
Currency (Ref)                     Currency (Test)
Eepe (Ref)                         Eepe (Test)
EepeInEur (Ref)                    EepeInEur (Test)
Rwa (Ref)                          Rwa (Test)

Mtf00 Gap
Abs(Mtf00 Gap)
Mtf00 Ratio
CashFlowType (Result)
Currency (Result)
Eepe Gap
Abs(Eepe Gap)
Eepe Ratio
EepeInEur Gap
Abs(EepeInEur Gap)
EepeInEur Ratio
Rwa Gap
Abs(Rwa Gap)
Rwa Ratio
```

The two **primary release-impact metrics** remain:

```text
Mtf00 Gap
EepeInEur Gap
```

The other Gap/Ratio/Ref/Test columns are explanation signals. They do not independently make a row material unless release policy later says otherwise.

## MTF00 is multi-currency

This is important. `Mtf00 Gap` is expressed in the row currency. The screenshots contain both EUR and USD rows.

Therefore SkillHub now uses:

```text
material MTF00 row: abs(Mtf00 Gap) > 10,000 in that row currency
```

but does **not** add native EUR and USD MTF00 amounts together to calculate Pareto concentration.

Instead the 80/90% selection is performed independently by currency:

```text
EUR MTF00 material movement -> 90% coverage
USD MTF00 material movement -> 90% coverage
... other currencies -> own coverage bucket
```

The selected rows are then unioned.

`EepeInEur Gap` is already EUR-normalized, therefore its Pareto coverage is global.

This avoids a subtle but serious analytical error: a cross-currency `top 90%` computed by directly summing native amounts is not economically meaningful.

## New concentration diagnostics

For each material metric/currency bucket the reducer now calculates:

- top-1 contribution share;
- top-3 contribution share;
- top-10 contribution share;
- HHI of contributor weights;
- effective contributor count (`1 / HHI`);
- signed vs gross movement;
- cancellation percentage;
- material-row percentage;
- threshold capture percentage;
- selected Pareto coverage.

These answer different questions:

```text
"One monster row caused this"       -> high top-1 / low effective contributor count
"A handful of rows dominate"       -> high top-3
"Broad systematic movement"        -> high effective contributor count
"Positive/negative effects offset" -> high cancellation percentage
"10k rule misses a large tail"     -> low threshold-capture percentage
```

## Secondary explanation diagnostics

On selected material rows only, SkillHub now summarizes:

- `Mtf00 Ratio`;
- `Eepe Gap` / `Eepe Ratio`;
- `EepeInEur Ratio`;
- `Rwa Gap` / `Rwa Ratio`;
- `EffectiveMaturity (Ref/Test)`;
- `RiskWeightedExposureFactor (Ref/Test)`;
- `EepeError (Ref/Test)`;
- `EepeRatio (Ref/Test)`;
- `CashFlowType (Result)`;
- `Currency (Result)`.

The intent is not to create more release thresholds. It is to help the agent form mechanisms such as:

```text
Observed:
large MTF00 movement + EffectiveMaturity changed systematically

Hypothesis:
a maturity / first-passage / break-clause code path may have changed
```

rather than just reporting numbers.

# 12. Backtesting is a targeted second-stage investigation

For CVAR/GCVAR, `AggregationLevel` is typically master/aggregation-grained.

In backtesting the screenshots show deal-grained values containing:

```text
.../TRD:<DEAL_ID>
```

SkillHub therefore:

1. takes impacted `LegalEntity` values from upstream CVAR/GCVAR evidence;
2. scans backtesting with that filter as early as possible;
3. extracts `DealId` from the `TRD:` segment;
4. aggregates each primary gap by deal;
5. applies the same strict 10k materiality;
6. keeps the deals needed for 80/90% coverage;
7. performs a **second narrow diagnostic pass only on those selected deals**;
8. summarizes Ref/Test changes, result-flag failures and RWA/ratio diagnostics for those deals.

This is intentionally two-pass. Keeping diagnostic state for every deal during the first pass would destroy bounded-memory behavior on the largest files.

# 13. The easiest way to use the full data plane today

Instead of manually invoking four tools, use the workflow-preparation skill once:

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

The output contains:

```text
ccr-26.10/
├── cvar/
│   ├── summary.json
│   ├── material_impacts.csv
│   └── agent_context.md
├── cvar-backtesting/
│   ├── backtesting_summary.json
│   ├── deal_impacts.csv
│   └── agent_context.md
├── gcvar/
├── gcvar-backtesting/
├── workflow_manifest.json
├── pr_forensics_hints.json
└── workflow_context.md        <- preferred first LLM input
```

If GitHub CLI is authenticated and repository/ref details are known, the same call can prefetch PR candidates:

```powershell
--repo OWNER/REPO --with-prs
```

That does **not** turn PR forensics into a CCR-specific component. The workflow simply composes the reusable `release-pr-forensics` skill.

# 14. How the multi-agent workflow is used today

Full autonomous agent-to-agent handoff depends on the Copilot environment enabled by the company. The deterministic workflow is usable now even without that feature.

Today the practical sequence is:

```text
1. Human gives local paths to the four CSVs once.
2. prepare-ccr-release-evidence creates the compact workspace.
3. CVAR validator reads cvar/summary.json + cvar-backtesting evidence.
4. GCVAR validator reads its own compact evidence.
5. Synthesis agent reads workflow_context.md and branch JSON when needed.
6. Synthesis agent invokes release-pr-forensics if code attribution is required.
7. Agent returns observed impacts, patterns, hypotheses, candidate PRs and the next confirming experiment.
```

The human should **not** attach the giant raw CSVs to Copilot chat. Give the agent their local file paths so the executable skills can process them.

# 15. What is still needed for production sign-off

The screenshots are enough to calibrate the architecture and column conventions, but they are not enough to prove all edge cases or real throughput.

The highest-value review inputs are now:

1. the exact CSV header line copied as text;
2. 30–100 sanitized real rows containing both ordinary and material impacts;
3. a small sanitized matching backtesting sample;
4. one historical release regression with a known eventual root cause/PR;
5. actual file size / row count / typical runtime constraints;
6. the final business rule for release verdict (`PASS`, `WARNING`, `FAIL` or equivalent).

With those, the next validation step is a blind historical replay: hide the known culprit, run the complete workflow, freeze its candidate list/hypotheses, then reveal the real root cause.

# 16. Current calibrated investigation policy

The live default is now intentionally **impact-first** rather than row-count-first:

```text
1. Reject rows at or below the strict 10k materiality threshold.
2. Sort remaining movement by absolute contribution.
3. Select the smallest contributor set required for the requested coverage (90% default, 80% optional).
4. Report contributor counts needed for 50/80/90/95% of material movement.
5. Diagnose concentration and cancellation before asking the LLM to explain anything.
6. Drill only impacted Legal Entities into backtesting, then only selected deals into diagnostic columns.
```

This gives the agent both "what is large?" and "is this one bad row, a handful of deals, or a broad systematic movement?" without exposing the raw files.

Ratio diagnostics tolerate Excel/CSV percentage formatting such as `0.25%` and parenthesized negatives such as `(0.50%)`.

For operational commands, read [CCR Release Validation — operator runbook](CCR-RELEASE-VALIDATION-RUNBOOK.md).
