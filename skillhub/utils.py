from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from pathlib import Path
from typing import Any

import yaml


class SkillHubError(RuntimeError):
    """Domain error surfaced by the CLI without a traceback."""


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SkillHubError(f"Missing file: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise SkillHubError(f"Expected a YAML mapping in {path}")
    return data


def dump_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def estimate_tokens(text: str) -> int:
    """Dependency-free context estimate; this is intentionally labelled approximate in the UI."""
    return 0 if not text else max(1, (len(text) + 3) // 4)


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def copytree_atomic(src: Path, dst: Path, force: bool = False) -> None:
    if dst.exists():
        if not force:
            raise SkillHubError(f"Destination already exists: {dst}. Use --force to replace it.")
        shutil.rmtree(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(dst.name + ".skillhub-tmp")
    if tmp.exists():
        shutil.rmtree(tmp)
    shutil.copytree(src, tmp)
    os.replace(tmp, dst)


def _is_hub_root(path: Path) -> bool:
    return (path / "skillhub.config.yaml").exists() and (path / "skills").is_dir()


def user_config_path() -> Path:
    return Path.home() / ".skillhub" / "config.json"


def configure_hub_root(path: Path) -> Path:
    path = path.expanduser().resolve()
    if not _is_hub_root(path):
        raise SkillHubError(f"Not a SkillHub repository: {path}")
    config = user_config_path()
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(json.dumps({"hub_root": str(path)}, indent=2) + "\n", encoding="utf-8")
    return config


def find_repo_root(start: Path | None = None) -> Path:
    start = (start or Path.cwd()).resolve()
    for candidate in [start, *start.parents]:
        if _is_hub_root(candidate):
            return candidate

    env_root = os.environ.get("SKILLHUB_ROOT")
    if env_root and _is_hub_root(Path(env_root).expanduser().resolve()):
        return Path(env_root).expanduser().resolve()

    config = user_config_path()
    if config.exists():
        try:
            configured = Path(json.loads(config.read_text(encoding="utf-8"))["hub_root"]).expanduser().resolve()
            if _is_hub_root(configured):
                return configured
        except (KeyError, json.JSONDecodeError, OSError):
            pass

    # Editable installs from the central clone need no explicit configuration.
    package_root = Path(__file__).resolve().parents[1]
    if _is_hub_root(package_root):
        return package_root

    raise SkillHubError(
        "Could not locate the central SkillHub repository. Use --root, set SKILLHUB_ROOT, "
        "or run: skillhub configure --hub <path-to-quant-skillhub>."
    )


def parse_frontmatter(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise SkillHubError(f"{path} must start with YAML frontmatter delimited by ---")
    end = text.find("\n---\n", 4)
    if end == -1:
        raise SkillHubError(f"{path} frontmatter is not closed with ---")
    meta = yaml.safe_load(text[4:end]) or {}
    if not isinstance(meta, dict):
        raise SkillHubError(f"{path} frontmatter must be a mapping")
    return meta, text[end + 5:]
