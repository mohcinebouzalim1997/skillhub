param(
  [switch]$SkipSite
)
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root
if (-not (Test-Path ".venv")) { python -m venv .venv }
$Py = Join-Path $Root ".venv\Scripts\python.exe"
$SkillHub = Join-Path $Root ".venv\Scripts\skillhub.exe"
& $Py -m pip install --upgrade pip
if ($SkipSite) { & $Py -m pip install -e "." } else { & $Py -m pip install -e ".[dev]" }
& $SkillHub configure --hub $Root
& $SkillHub validate
Write-Host "SkillHub ready." -ForegroundColor Green
Write-Host "Activate this shell with: .\.venv\Scripts\Activate.ps1"
Write-Host "Then run: skillhub doctor"
Write-Host "Play Store UI: skillhub marketplace --open"
