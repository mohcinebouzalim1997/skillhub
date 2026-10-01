# Getting started

Install SkillHub once from its standalone repository:

```powershell
.\scripts\bootstrap.ps1
skillhub doctor
skillhub validate
```

For high-throughput CCR workbook analysis (fast scans after one-time XLSX normalization/cache):

```powershell
pip install -e ".[ccr]"
```

Open the local marketplace:

```powershell
skillhub marketplace --open
```

To prepare the current CCR release-validation capability set:

```powershell
skillhub install-stack ccr-release-validation --check-deps
```

This installs the reusable workbook/backtesting/error/PR skills plus the top-level CCR coordinator and specialized CVAR, GCVAR and synthesis agents. Your product repositories remain untouched.

Read the [Project Guide](../project/PROJECT-GUIDE.md) before extending the CCR workflow.
