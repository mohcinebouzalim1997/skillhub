from __future__ import annotations
import importlib.util, shutil, subprocess, sys
from .installer import default_personal_skill_dir

def run_doctor()->dict:
    result={"python":{"ok":sys.version_info>=(3,10),"value":sys.version.split()[0]},"gh":{"ok":shutil.which("gh") is not None,"value":shutil.which("gh")},"copilot":{"ok":shutil.which("copilot") is not None,"value":shutil.which("copilot")},"personal_skill_dir":{"ok":True,"value":str(default_personal_skill_dir())},"polars":{"ok":importlib.util.find_spec("polars") is not None,"value":"installed" if importlib.util.find_spec("polars") is not None else "optional fast CSV backend not installed"}}
    if result["gh"]["ok"]:
        p=subprocess.run(["gh","auth","status"],capture_output=True,text=True,check=False); result["gh_auth"]={"ok":p.returncode==0,"value":(p.stdout+p.stderr).strip()[:1000]}
    else: result["gh_auth"]={"ok":False,"value":"GitHub CLI not found"}
    return result
