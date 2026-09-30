# Microsoft Copilot

When Microsoft Copilot cannot execute the local skill package, use SkillHub as a **context compiler**.

## Export the skill

```powershell
skillhub export release-pr-forensics \
  --budget 6000 \
  --output release-pr-forensics-context.md
```

Attach the generated `.md` file to Microsoft Copilot together with the relevant task inputs.

## Why export instead of copying the folder?

The exporter spends the context budget on:

- the canonical procedure;
- relevant references;
- high-value examples when available.

Implementation code is excluded by default. Add it only when the model genuinely needs to inspect the implementation:

```powershell
skillhub export release-pr-forensics \
  --budget 12000 \
  --include-code \
  --output release-pr-forensics-full-context.md
```

!!! tip
    The same canonical skill therefore serves two modes: **full executable use in GitHub Copilot** and **compact reasoning context in Microsoft Copilot**.
