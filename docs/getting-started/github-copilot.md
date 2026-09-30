# GitHub Copilot

SkillHub installs skills and agents personally, so the same capabilities can be used while working inside any product repository.

```powershell
skillhub install-stack ccr-release-validation --check-deps
```

Example reusable PR skill:

```text
Use /release-pr-forensics.
Repository: OWNER/REPO
Release: release/26.10
Symptom: EEPE jumped in MTF.
```

Or run it deterministically:

```powershell
skillhub run release-pr-forensics -- --repo OWNER/REPO --release release/26.10 --query "EEPE jump" --output release-analysis
```

For CCR release validation, select the relevant installed CVAR/GCVAR agent or use the declarative `ccr-release-validation` workflow as the orchestration blueprint.
