from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys

from .installer import default_personal_skill_dir


def _module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def run_doctor() -> dict:
    result = {
        "python": {"ok": sys.version_info >= (3, 10), "value": sys.version.split()[0]},
        "openpyxl": {
            "ok": _module("openpyxl"),
            "value": "installed" if _module("openpyxl") else "required for XLSX CCR workbooks",
        },
        "polars": {
            "ok": _module("polars"),
            "value": "installed" if _module("polars") else "recommended fast normalized-table backend; install .[ccr]",
        },
        "gh": {"ok": shutil.which("gh") is not None, "value": shutil.which("gh")},
        "copilot": {"ok": shutil.which("copilot") is not None, "value": shutil.which("copilot")},
        "personal_skill_dir": {"ok": True, "value": str(default_personal_skill_dir())},
    }
    if result["gh"]["ok"]:
        p = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True, check=False)
        result["gh_auth"] = {"ok": p.returncode == 0, "value": (p.stdout + p.stderr).strip()[:1000]}
    else:
        result["gh_auth"] = {"ok": False, "value": "GitHub CLI not found"}
    return result
