# Contributing to Quant SkillHub

SkillHub has several first-class object types. Keep them conceptually separate.

- **Skill**: one reusable capability/tool. Put it under `skills/<id>/` with `SKILL.md` + `skillhub.yaml`.
- **Agent**: one specialized AI worker. Put it under `agents/`.
- **Workflow**: a multi-agent job/orchestration blueprint. Put it under `workflows/`.
- **Pack**: a bundle of related skills.
- **Stack**: skills + agents + setup for a complete job.
- **Collection**: marketplace organization only.

## Add a skill

Start with:

```powershell
skillhub new my-skill --description "..." --category engineering --owner my-team
```

For executable skills:

1. keep deterministic work in `scripts/`;
2. expose named entrypoints in `skillhub.yaml`;
3. return structured artifacts where possible;
4. add tests/examples/references;
5. declare required and recommended dependencies separately;
6. never embed credentials or production secrets.

## Add an agent

Agents should compose existing skills whenever possible rather than duplicating scripts. State the mission, boundaries, skills used, and what evidence the agent expects.

## Add a workflow

A workflow should identify:

- required/optional inputs;
- participating agents;
- reusable skills;
- execution stages;
- artifacts passed between stages;
- what is parallel vs sequential;
- current readiness/status.

## Large data rule

Do not put huge raw CSVs into LLM context. Create a deterministic reduction skill and pass a stable evidence artifact to the agent.

## Before opening a PR

```powershell
python -m pytest -q
skillhub validate
skillhub build-registry
skillhub generate-site
python -m compileall -q skillhub skills tests benchmarks
```

If MkDocs dependencies are available, also run:

```powershell
skillhub build-site
```

See [`docs/project/PROJECT-GUIDE.md`](docs/project/PROJECT-GUIDE.md) for the complete architecture.
