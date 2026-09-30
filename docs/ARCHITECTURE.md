# Architecture

The canonical detailed explanation is the [Project Guide](project/PROJECT-GUIDE.md).

At a high level:

```text
skills = reusable atomic capabilities
agents = specialized AI workers
workflows = multi-agent jobs
packs = skill bundles
stacks = skills + agents + setup
```

The primary prepared workflow is **CCR Release Validation**, with independent CVAR and GCVAR validator agents followed by synthesis. `release-pr-forensics` is a reusable skill that any agent may call when code-change evidence is needed.

All large-data validation follows the rule:

```text
raw huge data → deterministic reduction → evidence contract → LLM reasoning
```
