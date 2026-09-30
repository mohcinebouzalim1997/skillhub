# Add a skill

SkillHub supports both engineers and people who do not want to touch Git locally.

## No-code contribution

Use **New issue → Propose a Skill** in GitHub. The issue form asks for:

- capability name;
- when it should be used;
- required inputs;
- procedure;
- expected output;
- category and owner;
- whether it executes an existing script or command.

The scaffold workflow can turn an approved issue into a draft skill change for review.

## Engineer workflow

Create a validated skeleton:

```powershell
skillhub new analyze-collateral-dispute \
  --description "Investigate disagreements in collateral calculations" \
  --category xva \
  --owner "XVA Quant"
```

Then implement the procedure and tests:

```powershell
skillhub validate
pytest
skillhub build-site
```

## Quality bar

A production skill should have:

- a specific trigger/description;
- clear inputs and output contract;
- deterministic scripts for deterministic work;
- minimal permissions;
- an explicit owner;
- tests for executable behavior;
- references only when they materially improve reasoning;
- no secrets or production credentials;
- evidence-oriented language rather than unsupported causal conclusions.
