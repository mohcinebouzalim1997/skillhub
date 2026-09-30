# Getting started

Install SkillHub once from its standalone repository:

```powershell
.\scripts\bootstrap.ps1
skillhub doctor
skillhub validate
```

For high-throughput large CSV analysis:

```powershell
pip install -e ".[fastcsv]"
```

Open the local marketplace:

```powershell
skillhub marketplace --open
```

To prepare the current CCR release-validation capability set:

```powershell
skillhub install-stack ccr-release-validation --check-deps
```

This installs the reusable CSV/backtesting/PR skills plus the specialized CVAR, GCVAR and synthesis agents. Your product repositories remain untouched.

Read the [Project Guide](../project/PROJECT-GUIDE.md) before extending the CCR workflow.
