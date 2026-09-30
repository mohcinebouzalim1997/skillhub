# Changelog

## 0.2.0 — 2026-09-29

- Added named-release mode with automatic previous sibling inference for refs such as `release/26.10`.
- Added generic ref/commit range mode and merge-date window mode.
- Added best-effort direct-commit detection for date investigations when a base branch is provided.
- Added one-command `investigate.py` orchestration.
- Replaced default full-diff retrieval with smart per-file patch selection and explicit diff plans.
- Added optional first-bad-date ranking signal and richer risk-sensitive ranking heuristics.

## 0.1.0

- Initial good-ref → bad-ref commit/PR mapping, candidate ranking and on-demand full diff retrieval.
