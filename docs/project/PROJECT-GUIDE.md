# Quant SkillHub — Project Guide

This document is the **single conceptual guide** to the project. Read it when you want to understand what SkillHub is, how its pieces fit together, and how the CCR Release Validation work should evolve.

---

## 1. What SkillHub is

Quant SkillHub is a standalone internal capability registry for AI-assisted Quant and engineering work.

It is intentionally **separate from product repositories** such as SmartXVA, Hig, pricing engines, or support tools.

The hub provides:

- a private GitHub repository as the source of truth;
- a MkDocs Material / GitHub Pages marketplace for discovery;
- reusable skills that can include Markdown, Python, PowerShell, batch files and references;
- personal installation into GitHub Copilot without modifying product repos;
- workflows and agents that compose skills into larger jobs;
- deterministic tools that reduce large data before an LLM reasons over it;
- compact exports for Microsoft Copilot when only file attachment is available.

The guiding principle is:

> **LLMs reason. Deterministic tools retrieve, calculate, filter and compress.**

---

## 2. The vocabulary

The project deliberately distinguishes the following concepts.

### Skill / tool

A **skill** is one reusable capability. It may be pure instructions or executable.

Examples:

- `release-pr-forensics` — retrieve release/commit/date changes, PR metadata, labels, changed files and selective diffs;
- `analyze-large-result-diff` — reduce a huge CVAR/GCVAR comparison CSV into compact evidence;
- `backtesting-drilldown` — filter a much larger backtesting CSV using dimensions found upstream, then rank deal contributors.

A skill can be reused by many agents and workflows.

**Important:** `release-pr-forensics` is a reusable skill. There is no dedicated “PR Forensics Agent” in the architecture.

### Agent

An **agent** is a specialized AI worker with a mission, operating rules and access to skills.

Current prepared CCR agents:

- `ccr-cvar-release-validator`;
- `ccr-gcvar-release-validator`;
- `ccr-release-validation-synthesizer`.

An agent can decide which reusable skill to call and how to interpret the resulting evidence.

### Workflow

A **workflow** describes a larger job involving multiple agents and skills.

The main prepared workflow is:

`ccr-release-validation`

Its current shape is:

```text
Candidate release validation
        │
        ├───────────────┐
        ▼               ▼
CVAR validator     GCVAR validator
        │               │
        └───────┬───────┘
                ▼
       synthesis agent
                │
                ├─ if material unexplained impact exists
                ▼
       release-pr-forensics skill
                │
                ▼
       candidate mechanisms / tests
                │
                ▼
        validation report
```

CVAR and GCVAR validation can eventually run in parallel because they produce independent evidence contracts.

### Pack

A **pack** is an installable group of skills.

### Stack

A **stack** installs a coherent working setup: skills + agents + dependencies/config references.

For example:

```powershell
skillhub install-stack ccr-release-validation --check-deps
```

### Evidence

**Evidence** is the stable machine-readable contract between deterministic tools and agents.

Agents should consume evidence instead of depending directly on CSV parsing implementation details.

The canonical schema is:

`schemas/evidence.schema.json`

This is strategically important: Polars can later be replaced by DuckDB, Arrow, C++ or a remote service without redesigning the agents.

---

## 3. Repository anatomy

```text
quant-skillhub/
│
├── skills/                     reusable atomic capabilities
│   ├── release-pr-forensics/
│   ├── analyze-large-result-diff/
│   ├── backtesting-drilldown/
│   ├── compare-result-snapshots/
│   └── investigate-metric-jump/
│
├── agents/                     specialized AI workers
│   ├── ccr-cvar-release-validator.agent.md
│   ├── ccr-gcvar-release-validator.agent.md
│   └── ccr-release-validation-synthesizer.agent.md
│
├── workflows/                  multi-agent jobs
│   └── ccr-release-validation.yaml
│
├── packs/                      installable skill bundles
├── stacks/                     complete setups: skills + agents
├── collections/                human browsing / marketplace grouping
│
├── skillhub/
│   ├── runtime/                reusable deterministic infrastructure
│   │   ├── csv_engine.py
│   │   ├── evidence.py
│   │   ├── profiling.py
│   │   ├── artifacts.py
│   │   ├── cache.py
│   │   └── logging.py
│   └── profiles/ccr/           domain configuration
│       ├── cvar.yaml
│       ├── gcvar.yaml
│       └── backtesting.yaml
│
├── schemas/
│   └── evidence.schema.json
│
├── docs/                       MkDocs marketplace + documentation
├── benchmarks/                 reproducible performance harnesses
├── tests/
└── registry/registry.json      generated marketplace index
```

---

## 4. Using the UI

There are two UI modes.

### GitHub Pages mode

The MkDocs site is static and read-only. It is good for:

- search;
- browsing skills;
- workflows;
- agents;
- packs/stacks;
- documentation;
- copying install commands.

### Local marketplace mode

Run:

```powershell
skillhub marketplace --open
```

The same marketplace gets a loopback-only local bridge and can show real machine state such as:

- Installed;
- Update available;
- Install / update / uninstall;
- pack/stack installation.

A static Pages site cannot inspect `~/.copilot/skills`, so SkillHub never pretends otherwise.

---

## 5. Personal Copilot model

Product repositories remain untouched.

Skills install under the personal Copilot area:

```text
~/.copilot/skills/
```

Agents install under:

```text
~/.copilot/agents/
```

You can therefore work in SmartXVA, Hig, another pricer, a Python analysis repo, etc., while using the same personal capabilities.

---

# Part II — Release / PR forensics

## 6. `release-pr-forensics` is reusable infrastructure

The skill supports three investigation scopes.

### Named release

Example:

```powershell
skillhub run release-pr-forensics -- `
  --repo OWNER/REPO `
  --release release/26.10 `
  --query "EEPE jump" `
  --output release-analysis
```

Our release naming convention does **not** zero-pad single-digit releases.

Correct:

```text
release/26.8
release/26.9
release/26.10
```

Incorrect for this project convention:

```text
release/26.08
release/26.09
```

Therefore `release/26.10` can infer `release/26.9` as the previous numeric sibling.

### Two refs or commits

```powershell
skillhub run release-pr-forensics -- `
  --repo OWNER/REPO `
  --base GOOD_SHA_OR_REF `
  --head BAD_SHA_OR_REF `
  --query "unexpected exposure jump" `
  --output release-analysis
```

### Date window

```powershell
skillhub run release-pr-forensics -- `
  --repo OWNER/REPO `
  --from-date 2026-09-15 `
  --to-date 2026-09-22 `
  --base-branch main `
  --query "unexpected exposure jump" `
  --output release-analysis
```

The release tool preserves direct commits that cannot be mapped to a PR.

## 7. Diff strategy

Fetching every full diff from a large release is intentionally **not** the default.

The skill uses progressive disclosure:

```text
all changes
   ↓
PR title/body/labels/files/churn
   ↓
rank relevance to symptom
   ↓
select top candidates
   ↓
per-file patches
   ↓
select informative source/config files
   ↓
full PR diff only when necessary
```

This is critical for small model context windows and for investigation quality.

---

# Part III — CCR large-data evidence

## 8. The problem

A release compare job can produce very large CVAR/GCVAR CSVs, and backtesting outputs can be significantly larger.

The LLM should never receive those raw files.

The desired pipeline is:

```text
Huge CVAR / GCVAR CSV
        │
        ▼
fast deterministic reduction
        │
        ├─ mtf00Gap
        ├─ EepeInEurGap
        └─ keys / dimensions
        │
        ▼
material rows only
        │
        ▼
pattern enrichment
        │
        ▼
small evidence JSON + Markdown
        │
        ▼
LLM / validator agent
        │
        ▼
impacted Legal Entity / aggregation
        │
        ▼
Huge backtesting CSV
        │
        ▼
EARLY FILTER using upstream dimensions
        │
        ▼
deal-level contributors
        │
        ▼
second small evidence artifact
```

## 9. `analyze-large-result-diff`

The generic skill uses CCR profiles instead of duplicated CVAR/GCVAR code.

CVAR:

```powershell
skillhub run analyze-large-result-diff -- `
  --profile cvar `
  --input <cvar.csv> `
  --output <out> `
  --threshold EepeInEurGap=100000 `
  --threshold mtf00Gap=0.1
```

GCVAR:

```powershell
skillhub run analyze-large-result-diff -- `
  --profile gcvar `
  --input <gcvar.csv> `
  --output <out>
```

### First pass

Only necessary columns are projected:

- configured gap metrics;
- available identity columns;
- configured dimensions.

Material selection uses:

- explicit absolute thresholds when provided;
- otherwise top-|gap| selection per metric.

Both positive and negative impacts are preserved.

### Second pass

Only the selected rows are enriched with more columns to identify patterns.

### Outputs

```text
summary.json
material_impacts.csv
patterns.json
agent_context.md
run_manifest.json
```

The raw CSV is never copied into the LLM context artifact.

## 10. Fast and fallback engines

The preferred backend is **Polars**.

Install the fast extra:

```powershell
pip install -e ".[fastcsv]"
```

SkillHub then uses lazy/streaming Polars paths where available.

If Polars is unavailable, the tool remains functional using a bounded-memory Python streaming implementation. This is useful on locked-down workstations, but Polars is the recommended production path for very large CCR files.

Benchmark helper:

```powershell
python benchmarks/benchmark_large_csv.py --rows 1000000 --backend auto
```

CI should verify correctness, not enforce workstation-specific throughput numbers.

---

## 11. Backtesting drilldown

The tool consumes upstream evidence:

```powershell
skillhub run backtesting-drilldown -- `
  --input <backtesting.csv> `
  --evidence <cvar-output/summary.json> `
  --output <backtesting-output>
```

It maps impacted Legal Entity / aggregation dimensions into the backtesting schema and filters as early as possible.

It then returns only top deal-level impacts and concentration statistics.

Example desired evidence:

```text
Legal Entity X is impacted.
23 deals survive the upstream filters.
Top 3 deals explain 83% of the selected absolute movement.
```

---

## 12. Evidence contract

The common evidence contract includes:

```json
{
  "schema_version": "1.0",
  "evidence_type": "large-result-diff",
  "source": {},
  "summary": {},
  "material_impacts": [],
  "patterns": [],
  "impacted_dimensions": {},
  "timings": [],
  "warnings": []
}
```

Agents should depend on this contract rather than on Polars/Pandas/CSV details.

---

# Part IV — CCR Release Validation workflow

## 13. Current prepared workflow

The central specification is:

`workflows/ccr-release-validation.yaml`

### Stage 1: CVAR validator

`ccr-cvar-release-validator`

Expected behavior:

1. reduce CVAR compare output;
2. identify material `mtf00Gap` / `EepeInEurGap` impacts;
3. find patterns;
4. use impacted dimensions to drill backtesting;
5. return compact CVAR evidence.

### Stage 2: GCVAR validator

`ccr-gcvar-release-validator`

Same architecture, GCVAR profile/configuration.

### Stage 3: Synthesis

`ccr-release-validation-synthesizer`

It receives only compact validator evidence.

If the impact is material and unexplained, it can call the generic:

`release-pr-forensics`

Then it correlates code changes with data evidence and proposes discriminating experiments.

---

## 14. What is production-ready vs prepared

### Working / implemented now

- SkillHub registry/CLI/marketplace structure;
- personal skill and agent installation;
- GitHub Pages source generation;
- release/commit/date PR retrieval architecture;
- `release/26.10` → `release/26.9` sibling convention;
- selective PR diff strategy;
- generic large CSV material-impact reduction;
- CVAR/GCVAR profile separation;
- evidence schema;
- backtesting evidence-driven filtering/drilldown;
- timing instrumentation;
- Polars fast path design + working streaming fallback;
- workflow/agent topology;
- synthetic end-to-end tests.

### Calibrated from the real compare screenshots, but still needs company-machine sign-off

The screenshots and business rules supplied on 30 September 2026 are now encoded:

- CVAR and GCVAR share the same compare schema family;
- primary release gaps are `Mtf00 Gap` and `EepeInEur Gap`;
- strict materiality is `abs(gap) > 10,000`;
- default impact coverage is 90% and is configurable (for example 80%);
- MTF00 is native-currency and Pareto coverage is separated by currency;
- backtesting `AggregationLevel` contains `/TRD:<DEAL_ID>`;
- backtesting is filtered first by impacted Legal Entity and then reduced to deal contributors;
- Ref/Test, Result, RWA and Ratio columns are diagnostic clues rather than independent materiality triggers.

Production approval still needs empirical validation, not more architecture guessing:

- a copied exact CSV header and a small sanitized row fixture to lock column spellings/types;
- one or more representative real-size files to benchmark the Polars path on the company workstation;
- one historical known regression for a blind root-cause replay;
- the final release verdict policy (`PASS`/`WARNING`/`FAIL`) if automated verdicts are desired;
- confirmation of any exceptional currencies or aggregation conventions not visible in the supplied examples.

This distinction is deliberate: the data plane is usable today, while release governance and real-scale performance require local evidence.

---

# Part V — How to finish the real CCR validator

## 15. What to provide next

To turn the calibrated validator into a company-approved golden implementation, the highest-value review inputs are the following. The tool no longer depends on these to run; they are for verification and golden tests.

### A. One CVAR compare CSV

Ideally a real file from a known release comparison, or at least:

- header;
- 20–100 representative rows;
- explanation of important columns;
- a known large impact example;
- confirmation that MTF00 is interpreted in the row currency and EEPE-in-EUR in EUR;
- one or two material rows whose human interpretation is known.

### B. One GCVAR compare CSV

Same information.

### C. One backtesting compare CSV

Most important details:

- header and sample rows;
- exact Deal ID column;
- Legal Entity columns;
- aggregation-level columns;
- which metric columns explain CVAR/GCVAR movement;
- how a CVAR/GCVAR row maps into backtesting rows.

### D. One historical release case

The best test is a release where the culprit is already known.

Provide:

- production release, e.g. `release/26.9`;
- candidate/bad release, e.g. `release/26.10`;
- CVAR/GCVAR compare outputs;
- backtesting output;
- the PR or code change eventually found responsible;
- the human reasoning used at the time.

We can then test whether the workflow discovers the same evidence without leaking the answer to it.

### E. Release decision rules

Examples:

- what is an automatic pass;
- what creates a warning;
- what blocks the release;
- whether CVAR and GCVAR must both pass;
- acceptable false positives;
- maximum expected runtime.

With those inputs, the generic infrastructure can be mapped to actual production semantics instead of guessing.

---

## 16. Recommended next implementation sequence

1. Lock real schemas and aliases from sanitized samples.
2. Encode materiality policy in versioned profile YAML.
3. Add golden tests from historical releases.
4. Finalize CVAR agent prompts/output contract.
5. Finalize GCVAR agent prompts/output contract.
6. Finalize synthesis/pass-warn-fail policy.
7. Benchmark against realistic file sizes on the company workstation.
8. Tune Polars projection/filter behavior.
9. Connect PR forensics using actual company GitHub authentication/repo conventions.
10. Only then label the workflow `approved`.

---

## 17. Security / operational rules

- Product repositories do not receive SkillHub files.
- Raw huge CSVs stay local and out of LLM context.
- Skills declare permissions.
- `release-pr-forensics` requires read-only GitHub access.
- External dependencies such as `gh` are checked, not silently installed.
- Tool output should be deterministic and auditable.
- A PR ranking is relevance evidence, not causal proof.

---

## 18. The architecture in one picture

```text
                 QUANT SKILLHUB
                       │
           marketplace / registry
                       │
       ┌───────────────┼────────────────┐
       │               │                │
     skills          agents          workflows
       │               │                │
       │               └──────┬─────────┘
       │                      │
       ▼                      ▼
deterministic tools      CCR Release Validation
       │                      │
       │          ┌───────────┴───────────┐
       │          ▼                       ▼
       │    CVAR validator          GCVAR validator
       │          │                       │
       │          └───────────┬───────────┘
       │                      ▼
       │                synthesis agent
       │                      │
       └──────────────► release-pr-forensics
                              │
                              ▼
                    evidence / experiment
                              │
                              ▼
                    release validation report
```

That is the intended direction: a library of small reusable capabilities beneath specialized agents, composed into auditable Quant workflows.

---

# Current CCR release-validation operating model (30 Sep 2026)

The project now contains a one-command deterministic preparation layer for the CCR workflow:

```text
prepare-ccr-release-evidence
```

This is a **skill/tool**, not an agent. It orchestrates the fast data reducers and creates the compact workspace consumed by the specialized agents.

The hierarchy is now:

```text
CCR Release Validation                    WORKFLOW
│
├── prepare-ccr-release-evidence          deterministic workflow-prep skill
│   ├── analyze-large-result-diff         reusable large-CSV skill
│   └── backtesting-drilldown             reusable deal drilldown skill
│
├── ccr-cvar-release-validator            AGENT
├── ccr-gcvar-release-validator           AGENT
└── ccr-release-validation-synthesizer    AGENT
      └── release-pr-forensics            reusable skill/tool
```

`release-pr-forensics` stays generic and can be reused by any future engineering/quant agent.

The real compare-file screenshots established two important implementation rules:

1. `Mtf00 Gap` is native-currency. The strict 10k threshold is applied row-by-row, and Pareto coverage is computed **per currency** when multiple currencies are present. We do not fabricate a single EUR+USD concentration number.
2. Backtesting `AggregationLevel` contains `/TRD:<DEAL_ID>`, so upstream master-level aggregation strings are not exact-joined. We filter first by impacted Legal Entity and derive the deal ID from `TRD:`.

The reducer also calculates top-1/top-3/top-10 concentration, HHI/effective contributor count, cancellation, threshold capture and selected coverage. Secondary RWA/ratio/Ref-Test columns are used as explanation clues only after material rows/deals have been selected.

For the exact commands, artifact tree and current real-schema contract, read [CCR Release Validation — Real Data Workflow](CCR-RELEASE-VALIDATION.md).
