from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from skillhub.utils import SkillHubError, load_yaml


def builtin_profile_path(profile: str) -> Path:
    candidate = Path(profile)
    if candidate.exists():
        return candidate.resolve()
    name = profile.removesuffix(".yaml")
    here = Path(__file__).resolve().parents[1] / "profiles" / "ccr" / f"{name}.yaml"
    if not here.exists():
        raise SkillHubError(f"Unknown profile '{profile}'. Expected a YAML path or built-in CCR profile.")
    return here


def load_profile(profile: str) -> dict[str, Any]:
    data = deepcopy(load_yaml(builtin_profile_path(profile)))
    if not isinstance(data, dict):
        raise SkillHubError(f"Profile {profile} must be a YAML mapping")

    # CCR data profiles can inherit one centrally maintained materiality policy so that CVAR,
    # GCVAR and backtesting cannot silently drift to different business thresholds/coverage.
    policy_name = data.get("materiality_profile")
    if policy_name:
        policy_path = builtin_profile_path(str(policy_name))
        policy = deepcopy(load_yaml(policy_path))
        raw_defaults = policy.get("metrics") or {}
        if not isinstance(raw_defaults, dict):
            raise SkillHubError(f"Materiality profile {policy_name} must declare metrics as a mapping")
        merged_metrics = []
        for metric in data.get("metrics") or []:
            if not isinstance(metric, dict) or not metric.get("name"):
                continue
            defaults = raw_defaults.get(str(metric["name"])) or {}
            merged_metrics.append({**deepcopy(defaults), **metric})
        data["metrics"] = merged_metrics
        data["materiality_policy_id"] = policy.get("id", str(policy_name))
        data["threshold_operator"] = policy.get("threshold_operator", "gt")
        data["default_coverage_target"] = policy.get("default_coverage_target")
    return data


def _metric_alias_index(profile: dict[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for row in profile.get("metrics") or []:
        if not isinstance(row, dict) or not row.get("name"):
            continue
        for alias in [row["name"], *(row.get("aliases") or [])]:
            index[str(alias).strip().lower()] = row
    return index


def apply_metric_threshold_overrides(profile: dict[str, Any], overrides: list[str] | None) -> dict[str, Any]:
    """Apply threshold overrides by canonical metric name *or* any declared CSV alias."""
    if not overrides:
        return profile
    metrics = _metric_alias_index(profile)
    for raw in overrides:
        if "=" not in raw:
            raise SkillHubError(f"Invalid threshold '{raw}'. Use METRIC=VALUE")
        name, value = raw.split("=", 1)
        metric = metrics.get(name.strip().lower())
        if metric is None:
            known = sorted({str(row.get("name")) for row in profile.get("metrics") or [] if isinstance(row, dict) and row.get("name")})
            raise SkillHubError(f"Threshold override references unknown metric '{name}'. Known metrics: {known}")
        metric["absolute_threshold"] = float(value)
    return profile


def apply_metric_coverage_override(profile: dict[str, Any], coverage: float | None) -> dict[str, Any]:
    if coverage is None:
        return profile
    coverage = float(coverage)
    if not 0 < coverage <= 1:
        raise SkillHubError("Coverage must be > 0 and <= 1, e.g. 0.9 for 90%.")
    for row in profile.get("metrics") or []:
        if isinstance(row, dict) and row.get("name"):
            row["coverage_target"] = coverage
    return profile
