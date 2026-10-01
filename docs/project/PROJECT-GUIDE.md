# Quant SkillHub — Project Guide

This is the authoritative conceptual guide to Quant SkillHub. It explains the platform, its vocabulary, how GitHub Copilot uses it, and the current CCR Release Validation implementation.

---

# 1. What SkillHub is

Quant SkillHub is a standalone internal marketplace and runtime for reusable AI capabilities.

It is intentionally **separate from product repositories** such as SmartXVA, Hig, pricing engines and support tools.

The central repository provides:

- a GitHub source of truth;
- a MkDocs Material / GitHub Pages marketplace;
- reusable skills containing instructions, Python, PowerShell, batch files and references;
- personal installation into GitHub Copilot without modifying product repositories;
- workflows and specialized agents;
- deterministic data-processing tools that compress large inputs before an LLM reasons over them;
- compact Markdown exports for environments such as Microsoft Copilot where file attachment is easier than executable skills.

The core engineering principle is:

> **LLMs reason. Deterministic tools retrieve, calculate, filter and compress.**

---

# 2. Vocabulary

## Skill / tool

A **skill** is one reusable capability.

Examples:

```text
release-pr-forensics
analyze-large-result-diff
backtesting-drilldown
analyze-ccr-errors
```

A skill may contain `SKILL.md`, executable scripts, references, examples and tests.

`release-pr-forensics` is deliberately a reusable skill/tool. It is not owned by the CCR workflow and can later be reused by production-support, pricing, model-validation or other agents.

## Agent

An **agent** is an AI worker with a mission, reasoning rules and access to skills.

Current CCR agents:

```text
ccr-release-validator                 # today-facing coordinator
ccr-cvar-release-validator            # CVAR specialist
ccr-gcvar-release-validator           # GCVAR specialist
ccr-release-validation-synthesizer    # root-cause/code specialist
```

Today, GitHub Copilot can use the coordinator as the single user-facing entry point: it executes the deterministic preparation skill from local workbook paths, then reasons over the compact workspace. The specialist agents encode the workflow roles and can also be invoked independently; future enterprise agent tooling can delegate between them explicitly.

## Workflow

A **workflow** is a larger job composed from agents and skills.

Current workflow:

```text
ccr-release-validation
```

## Pack

A **pack** is an installable bundle of skills.

## Stack

A **stack** installs the full working setup: skills + agents + dependency references + workflow linkage.

Example:

```powershell
skillhub install-stack ccr-release-validation --check-deps
```

## Evidence

**Evidence** is the stable machine-readable boundary between deterministic tools and agents.

The LLM should consume small JSON/Markdown evidence rather than implement parsing/calculation itself.

This matters strategically because the underlying engine can later move from Python/Polars to DuckDB, Arrow, C++, Spark or a remote service without redesigning the agents.

---

# 3. Repository structure

```text
quant-skillhub/
|
+-- skills/
|   +-- release-pr-forensics/
|   +-- analyze-large-result-diff/
|   +-- backtesting-drilldown/
|   +-- analyze-ccr-errors/
|   +-- prepare-ccr-release-evidence/
|   +-- compare-result-snapshots/
|   +-- investigate-metric-jump/
|
+-- agents/
|   +-- ccr-release-validator.agent.md
|   +-- ccr-cvar-release-validator.agent.md
|   +-- ccr-gcvar-release-validator.agent.md
|   +-- ccr-release-validation-synthesizer.agent.md
|
+-- workflows/
|   +-- ccr-release-validation.yaml
|
+-- skillhub/
|   +-- runtime/
|   |   +-- csv_engine.py
|   |   +-- workbook.py
|   |   +-- ccr.py
|   |   +-- diagnostics.py
|   |   +-- evidence.py
|   |   +-- profiling.py
|   |   +-- artifacts.py
|   |   +-- cache.py
|   +-- profiles/ccr/
|       +-- materiality.yaml
|       +-- cvar.yaml
|       +-- gcvar.yaml
|       +-- backtesting.yaml
|
+-- schemas/
|   +-- evidence.schema.json
|
+-- packs/
+-- stacks/
+-- collections/
+-- docs/
+-- tests/
+-- benchmarks/
+-- registry/
```

---

# 4. GitHub Copilot model

SkillHub does not put AI files into SmartXVA/Hig/etc.

Personal skills are installed under the user's Copilot area and can be used from any repository.

Conceptually:

```text
Quant SkillHub repo
      |
      +-- install personal skills/agents
      |
      v
~/.copilot/skills
~/.copilot/agents
      |
      v
open SmartXVA / Hig / any repo
      |
      v
GitHub Copilot can use installed capabilities
```

The product repository remains clean.

---

# 5. Marketplace UI

GitHub Pages is the static read-only marketplace for discovery.

The UI exposes:

```text
Home
Marketplace
Skills
Workflows
Agents
Packs
Stacks
Collections
Documentation
```

The local control-center mode is:

```powershell
skillhub marketplace --open
```

A static Pages site cannot inspect local `~/.copilot/skills`; the local bridge is what enables real Installed / Update / Uninstall state.

---

# 6. Reusable PR forensics

`release-pr-forensics` can investigate changes using:

```text
named release
arbitrary base/head refs
commit range
date range
```

For CCR release validation the normal range is:

```text
release/26.9 -> release/26.10
```

The naming convention is not zero-padded.

The skill retrieves cheap information broadly and expensive information selectively:

```text
commits in range
  -> associated PRs
  -> title/body/labels/files/churn
  -> relevance ranking
  -> per-file patches for top candidates
  -> full diff only if needed
```

The objective is not to dump every diff into Copilot.

---

# 7. CCR Release Validation workflow

The workflow currently consists of three agents and reusable deterministic skills.

```text
                 CCR RELEASE VALIDATION
                          |
                          v
               CVAR Validator Agent
                          |
                  MTF00 -> EEPE
                          |
          deals + errors + patterns
                          |
                          v
            GCVAR Validator Agent
                          |
        "same issue already in CVAR?"
                 /                 \
               yes                 no
                |                   |
          reuse evidence      full deep dive
                 \                 /
                          |
                          v
         Release Validation Synthesizer
                          |
              release-pr-forensics
                          |
               selective code diffs
                          |
             discriminating experiment
                          |
    expected_dev_change / suspected_bug / inconclusive
```

The PR skill is shared infrastructure; the CCR agents do not duplicate GitHub retrieval logic.

---

# 8. Real workbook contract

CVAR result comparison:

```text
CcrMetrics.xlsx
```

GCVAR result comparison:

```text
CcrMetrics_Gcvar.xlsx
```

Backtesting result workbooks share the same result-column family but have a deal-grained `AggregationLevel`.

Result comparison workbooks have exactly three semantic sheets:

```text
Details
Non Ref
Non Test
```

Semantics:

```text
Details   -> present in Ref and Test
Non Ref   -> absent from Ref, present in Test/candidate
Non Test  -> present in Ref, absent from Test/candidate
```

This matters because an addition/removal can be more important than a changed matched row.

Error workbooks (`ErrorByTrade.xlsx`) use the same three-sheet comparison convention.

---

# 9. XLSX performance layer

The previous prototype assumed CSV. The current implementation is workbook-aware.

`.xlsx` files are streamed with `openpyxl` in read-only mode and normalized once into a local cached CSV table.

```text
XLSX workbook
   |
   +-- Details
   +-- Non Ref
   +-- Non Test
   |
   v
normalized cached table
   |
   +-- WorkbookSheet
   +-- PresenceState
   +-- IsStructuralChange
   +-- derived side-only gaps
   |
   v
Polars fast path (when installed)
   or
bounded-memory Python streaming fallback
```

The cache exists only in the analysis workspace and is never embedded into LLM context.

The fast environment is:

```powershell
pip install -e ".[ccr]"
```

`openpyxl` is a required dependency. Polars is the recommended large-table scan engine.

---

# 10. Side-only rows and signed gaps

For `Details`, the compare workbook normally already contains explicit gap columns.

For `Non Ref` and `Non Test`, explicit gaps may be absent. SkillHub derives comparable signed contributions:

```text
Non Ref  -> +Test value
Non Test -> -Ref value
```

This applies to the primary metrics when necessary:

```text
Mtf00 Gap
EepeInEur Gap
```

The normalized table includes `PresenceState`, allowing agents to distinguish a model-value movement from a structural addition/removal.

---

# 11. Materiality and coverage

The confirmed rule is:

```text
abs(gap) > 10,000
```

Exactly 10,000 is not material.

Primary metrics:

```text
Mtf00Gap
EepeInEurGap
```

After materiality, the tool retains the largest contributors until the configured coverage of absolute material movement is reached.

Default:

```text
90%
```

Configurable example:

```text
80%
```

The analyzer additionally reports:

```text
contributors required for 50 / 80 / 90 / 95%
top-1 / top-3 / top-10 concentration
positive vs negative movement
net vs gross movement
cancellation
HHI / effective contributor count
threshold capture of total absolute movement
```

This distinguishes one giant localized regression from a broad systemic movement.

---

# 12. MTF00 currency semantics

MTF00 is a native-currency quantity.

Therefore:

```text
900,000 USD + 80,000 EUR
```

must not become a fake `980,000` common-unit statistic.

SkillHub computes MTF00 materiality/coverage separately by row currency, then unions the selected contributors.

EEPE-in-EUR is already EUR-normalized and can be analyzed globally.

---

# 13. CVAR investigation order

The CVAR agent always investigates **MTF00 first**.

## MTF00

It determines:

- material impact size;
- structural vs matched rows;
- Legal Entity/master concentration;
- diagnostic Ref/Test changes;
- deal-level backtesting contributors;
- deal-family mix;
- result-level and deal-level error asymmetries.

## EEPE

Then it performs the same impact/deal/error analysis for EEPE-in-EUR.

Finally it asks:

```text
How much of selected EEPE movement occurs on the same rows/deals as selected MTF00 movement?
```

Routing labels:

```text
strong_mtf00_overlap
partial_mtf00_overlap
weak_or_no_mtf00_overlap
```

These labels guide reasoning but are not causal claims.

Critically, other MTFs are not visible in the compare file, so EEPE can still be MTF-driven even with weak MTF00 overlap.

---

# 14. Backtesting deal attribution

Backtesting is filtered first by impacted Legal Entity.

Its aggregation level normally contains:

```text
/TRD:<DEAL_ID>
```

SkillHub derives `DealId` and aggregates MTF00/EEPE movement per deal.

Confirmed deal family convention:

```text
no prefix -> equity_dps
ELI-      -> equity
other     -> fic
```

This pattern becomes part of the compact agent evidence.

A useful output can therefore say:

```text
90% of CVAR MTF00 movement is explained by 6 deals.
78% of selected absolute movement is FIC.
The top 2 IRD-* deals explain 55%.
```

---

# 15. ErrorByTrade forensics

`analyze-ccr-errors` is a reusable deterministic skill.

Typical columns:

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

It scans only errors relevant to impacted Legal Entities/deals and classifies side asymmetry:

```text
introduced_in_test
removed_in_test
changed_between_ref_and_test
same_or_unresolved
```

It also classifies common error families such as dead trade, failed MTM, missing schedule, unmanaged rate index, missing market data and unpriced netting set.

This answers questions like:

```text
Are the top impacted deals missing/pricing-failing only in Test?
Did an error disappear on one side, creating a large release gap?
Are all top FIC contributors affected by the same pricing error family?
```

An error correlation is evidence, not automatic proof.

---

# 16. GCVAR optimization

GCVAR is checked after CVAR.

The first GCVAR stage is deliberately cheap: reduce its result workbook and compare its signature with CVAR using Legal Entity overlap, aggregation overlap and metric direction.

When similarity is high:

```text
same_issue_likely = true
```

then the default workflow skips the GCVAR backtesting/error deep dive and reuses the CVAR explanation path.

This behavior is controlled by:

```text
--gcvar-deep auto     # default
--gcvar-deep always   # force independent deep validation
--gcvar-deep never
```

The gate is an optimization, not a mathematical proof that both branches have identical causes.

---

# 17. Root-cause synthesis and PRs

The synthesis agent should establish data hypotheses before reading code.

Useful search evidence can include:

```text
MTF00 / EEPE
EffectiveMaturity
RiskWeightedExposureFactor
CashFlowType/Currency result flags
error categories
Legal Entities
deal families
specific impacted deals
```

Then `release-pr-forensics` searches the exact release range and ranks relevant PRs.

The agent correlates the observed mechanism with selective code patches.

It should propose the smallest discriminating test, for example:

```text
rerun one impacted deal with old/new boundary condition
rerun one LE after restoring an old configuration
compare one pricing path with/without a new mapping
```

Only after such evidence should a PR become a **Confirmed cause**.

---

# 18. Final classification

Each material issue should end with one of:

```text
expected_dev_change
suspected_bug
inconclusive
```

Expected dev change means the code intent and the observed impact line up coherently and there is no important contradiction.

If the agent is unsure, `inconclusive` is the correct output.

---

# 19. One-command workflow today

The current deterministic data plane can be run with one command:

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
  --repo OWNER/REPO `
  --with-prs `
  --coverage 0.90 `
  --output "C:\work\ccr-release-26.10"
```

The first file Copilot should read is:

```text
workflow_context.md
```

not the Excel files.

## Use the coordinator directly in GitHub Copilot

After installing the stack, select/invoke the `ccr-release-validator` agent and give it the local workbook paths, production/candidate refs and repository. It should run `prepare-ccr-release-evidence` itself through the terminal (with your approval), then read `workflow_context.md`.

This gives a one-agent UX today without collapsing the architecture: the deterministic tools and specialist-agent contracts remain separate underneath.


---

# 20. Generated artifacts

A typical workspace contains:

```text
ccr-release-26.10/
|
+-- workflow_context.md
+-- workflow_manifest.json
+-- root_cause_routing.json
+-- pr_forensics_hints.json
|
+-- cvar/
|   +-- summary.json
|   +-- agent_context.md
|   +-- material_impacts.csv
|   +-- patterns.json
|   +-- _cache/
|
+-- cvar-backtesting/
|   +-- backtesting_summary.json
|   +-- agent_context.md
|   +-- deal_impacts.csv
|
+-- cvar-errors/
|   +-- error_summary.json
|   +-- agent_context.md
|   +-- relevant_errors.csv
|
+-- cvar-backtesting-errors/
|
+-- gcvar/
+-- gcvar-backtesting/           # only when deep path runs
+-- gcvar-errors/                # only when deep path runs
|
+-- pr-forensics/                # when --with-prs is enabled
```

The `_cache` files are local processing artifacts, not LLM context.

---

# 21. Current limitations / company-machine validation

The implementation has synthetic XLSX regression tests, but the actual confidential Excel files have not been copied into this environment.

Therefore the next production validation should confirm:

- exact headers and value types on the real workbooks;
- workbook size and normalization runtime;
- Polars throughput on the normalized backtesting table;
- the exact behavior of `Non Ref` / `Non Test` on real generated files;
- deal-prefix edge cases;
- one historical known regression where the true PR/root cause is already known.

The best acceptance test is a blind replay: hide the known culprit, run the workflow, freeze its output, then reveal the historical cause and compare.

---

# 22. How to extend SkillHub safely

When adding a new capability:

1. keep retrieval/computation deterministic where possible;
2. output compact structured evidence;
3. make the skill reusable rather than embedding it inside one agent;
4. keep business thresholds/configuration in profiles;
5. add synthetic regression tests;
6. add the capability to marketplace metadata;
7. update this guide when the conceptual model changes.

That is how SkillHub stays an internal capability platform instead of becoming a folder of clever prompts.
